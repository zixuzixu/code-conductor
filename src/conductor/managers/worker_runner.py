"""Worker runner — spawns Claude Code CLI and parses NDJSON output.

Runs Claude Code in non-interactive mode within a worktree, streaming
structured JSON events for monitoring and observability.
"""

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from conductor.core.constants import (
    CLAUDE_ARGS,
    CLAUDE_CMD,
    MAX_WORKER_RETRIES,
    WORKER_NO_OUTPUT_TIMEOUT_S,
    WORKER_PROMPT,
    WORKER_THINKING_TIMEOUT_S,
)

logger = structlog.get_logger()


@dataclass
class WorkerEvent:
    """A single parsed NDJSON event from the Worker."""

    type: str  # thinking, file_write, tool_use, error, complete, etc.
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class WorkerResult:
    """Aggregated result of a Worker execution."""

    exit_code: int
    events: list[WorkerEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    success: bool = False
    killed: bool = False
    kill_reason: str | None = None


class WorkerMonitor:
    """Monitors NDJSON events from a Worker, detecting anomalous signals.

    Signal detection (§8.2):
    - Long thinking with no tool use (>180s)
    - Repeated identical errors (3+)
    - No output at all (>120s)
    - File write to unexpected paths (outside worktree)
    - complete with status: error
    - Test failure after merge
    """

    def __init__(self, worktree_path: Path, thread_id: str):
        self.worktree_path = worktree_path
        self.thread_id = thread_id
        self.last_event_time = time.time()
        self.last_tool_use_time = time.time()
        self.error_counts: dict[str, int] = {}
        self.events: list[WorkerEvent] = []
        self.errors: list[str] = []
        self.files_modified: list[str] = []
        self._should_kill = False
        self._kill_reason: str | None = None

    def process_event(self, event: WorkerEvent) -> None:
        """Process a single NDJSON event and check for anomalies."""
        self.events.append(event)
        self.last_event_time = time.time()

        if event.type == "tool_use":
            self.last_tool_use_time = time.time()

        if event.type == "file_write":
            path = event.data.get("path", "")
            self.files_modified.append(path)
            # Check for path escape
            if path and str(self.worktree_path) not in str(Path(path).resolve()):
                logger.warning(
                    "worker.path_escape",
                    thread_id=self.thread_id,
                    path=path,
                    worktree=str(self.worktree_path),
                )

        if event.type == "error":
            error_msg = event.data.get("message", "unknown error")
            self.errors.append(error_msg)
            self.error_counts[error_msg] = self.error_counts.get(error_msg, 0) + 1
            if self.error_counts[error_msg] >= MAX_WORKER_RETRIES:
                self._should_kill = True
                self._kill_reason = f"Repeated error ({MAX_WORKER_RETRIES}x): {error_msg}"
                logger.error("worker.repeated_errors", thread_id=self.thread_id, error=error_msg)

    def check_timeouts(self) -> None:
        """Check for timeout conditions. Call periodically."""
        now = time.time()

        # No output at all
        if now - self.last_event_time > WORKER_NO_OUTPUT_TIMEOUT_S:
            self._should_kill = True
            self._kill_reason = f"No output for {WORKER_NO_OUTPUT_TIMEOUT_S}s"
            logger.warning("worker.no_output_timeout", thread_id=self.thread_id)

        # Long thinking without tool use
        if now - self.last_tool_use_time > WORKER_THINKING_TIMEOUT_S:
            logger.warning("worker.thinking_timeout", thread_id=self.thread_id)

    @property
    def should_kill(self) -> bool:
        return self._should_kill

    @property
    def kill_reason(self) -> str | None:
        return self._kill_reason


class WorkerRunner:
    """Spawns and manages a Claude Code Worker process.

    Usage:
        runner = WorkerRunner()
        result = await runner.run(worktree_path, thread_id)
    """

    def __init__(self, prompt: str = WORKER_PROMPT):
        self.prompt = prompt

    async def run(
        self,
        worktree_path: Path,
        thread_id: str,
        *,
        on_event: asyncio.Event | None = None,
        event_callback: object | None = None,
    ) -> WorkerResult:
        """Execute Claude Code in the given worktree.

        Args:
            worktree_path: Directory to run Claude Code in.
            thread_id: For logging and monitoring.
            on_event: Optional asyncio.Event, set when process completes.
            event_callback: Optional async callable(WorkerEvent) for real-time streaming.

        Returns:
            WorkerResult with aggregated outcomes.
        """
        monitor = WorkerMonitor(worktree_path, thread_id)

        cmd = [CLAUDE_CMD, *CLAUDE_ARGS, self.prompt]
        logger.info("worker.spawn", thread_id=thread_id, cwd=str(worktree_path))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error("worker.claude_not_found", thread_id=thread_id)
            return WorkerResult(exit_code=-1, errors=["claude CLI not found"])

        # Read NDJSON output line by line
        timeout_check_task = asyncio.create_task(self._timeout_loop(monitor, proc))

        try:
            async for line in proc.stdout:
                decoded = line.decode().strip()
                if not decoded:
                    continue

                event = self._parse_ndjson_line(decoded)
                monitor.process_event(event)

                if event_callback:
                    await event_callback(event)

                if monitor.should_kill:
                    proc.kill()
                    logger.warning("worker.killed", thread_id=thread_id, reason=monitor.kill_reason)
                    break

            await proc.wait()
        finally:
            timeout_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await timeout_check_task

        exit_code = proc.returncode or 0
        success = exit_code == 0 and not monitor.should_kill

        result = WorkerResult(
            exit_code=exit_code,
            events=monitor.events,
            errors=monitor.errors,
            files_modified=monitor.files_modified,
            success=success,
            killed=monitor.should_kill,
            kill_reason=monitor.kill_reason,
        )

        logger.info(
            "worker.finished",
            thread_id=thread_id,
            exit_code=exit_code,
            success=success,
            event_count=len(monitor.events),
            error_count=len(monitor.errors),
        )
        return result

    @staticmethod
    def _parse_ndjson_line(line: str) -> WorkerEvent:
        """Parse a single NDJSON line into a WorkerEvent."""
        try:
            data = json.loads(line)
            event_type = data.pop("type", "unknown")
            return WorkerEvent(type=event_type, data=data)
        except json.JSONDecodeError:
            return WorkerEvent(type="raw", data={"content": line})

    @staticmethod
    async def _timeout_loop(monitor: WorkerMonitor, proc: asyncio.subprocess.Process) -> None:
        """Periodically check for timeout conditions."""
        while proc.returncode is None:
            await asyncio.sleep(10)
            monitor.check_timeouts()
            if monitor.should_kill:
                proc.kill()
                break
