"""Session dispatcher — background loop that consumes tasks and spawns Workers.

Each active session gets one dispatcher running as an asyncio task.
The dispatcher implements the 9-step Worker lifecycle (§5.1).
"""

import asyncio
from collections.abc import Callable
from typing import Any

import structlog

from conductor.core.constants import MAX_WORKER_RETRIES, TaskStatus, ThreadStatus
from conductor.core.models import Session, Task, Thread
from conductor.managers.git_manager import GitError, GitManager
from conductor.managers.memory_manager import MemoryManager
from conductor.managers.queue_manager import QueueManager
from conductor.managers.thread_manager import ThreadManager
from conductor.managers.worker_runner import WorkerResult, WorkerRunner

logger = structlog.get_logger()


class SessionDispatcher:
    """Orchestrates the Worker lifecycle for a single session.

    The dispatch loop:
    1. Pop task from queue
    2. Create thread (worktree + branch)
    3. Setup (symlinks + CLAUDE.md)
    4. Execute Worker (Claude Code CLI)
    5-8. Commit → Merge → Conflict? → Push
    9. Cleanup (update status, remove worktree, log to PROGRESS.md)

    Concurrency is bounded by session.max_workers.
    """

    def __init__(
        self,
        session: Session,
        queue: QueueManager,
        thread_mgr: ThreadManager,
        git: GitManager,
        memory: MemoryManager,
        worker_runner: WorkerRunner | None = None,
    ) -> None:
        self.session = session
        self.queue = queue
        self.thread_mgr = thread_mgr
        self.git = git
        self.memory = memory
        self.worker_runner = worker_runner or WorkerRunner()
        self._active_threads: dict[str, Thread] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._paused = False
        self._quota_backoff_delays = [30, 60, 120]  # seconds
        self._on_quota_exhausted: Callable[..., Any] | None = None

    def set_quota_callback(self, callback: Callable[..., Any]) -> None:
        """Set a callback to be invoked when quota exhaustion pauses dispatch."""
        self._on_quota_exhausted = callback

    @property
    def active_count(self) -> int:
        return len(self._active_threads)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    def resume_dispatch(self) -> None:
        """Resume dispatching after a quota pause."""
        self._paused = False
        logger.info("dispatcher.resumed", session_id=str(self.session.id))

    def start(self) -> asyncio.Task:
        """Start the dispatch loop as a background asyncio task."""
        if self._task and not self._task.done():
            logger.warning("dispatcher.already_running", session_id=str(self.session.id))
            return self._task
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("dispatcher.started", session_id=str(self.session.id))
        return self._task

    def stop(self) -> None:
        """Signal the dispatch loop to stop after current tasks finish."""
        self._running = False
        logger.info("dispatcher.stopping", session_id=str(self.session.id))

    async def _dispatch_loop(self) -> None:
        """Main dispatch loop — pop tasks and spawn workers within concurrency limits."""
        sid = self.session.id
        try:
            # Crash recovery: re-queue any IN_PROGRESS tasks from previous run
            recovered = self.queue.recover_in_progress(sid)
            if recovered:
                logger.info("dispatcher.recovered_tasks", count=len(recovered))

            while self._running:
                # Check if we have worker slots available
                if self.active_count >= self.session.max_workers:
                    await asyncio.sleep(1)
                    continue

                # Check if paused due to quota exhaustion
                if self._paused:
                    await asyncio.sleep(5)
                    continue

                # Try to pop a task
                task = self.queue.pop(sid)
                if task is None:
                    await asyncio.sleep(2)
                    continue

                # Spawn worker in a separate coroutine (bounded by max_workers)
                worker_task = asyncio.create_task(self._execute_task(task))
                worker_task.add_done_callback(lambda t: t.result() if not t.cancelled() and not t.exception() else None)

        except asyncio.CancelledError:
            logger.info("dispatcher.cancelled", session_id=str(sid))
        except Exception as e:
            logger.error("dispatcher.error", session_id=str(sid), error=str(e))
        finally:
            self._running = False
            logger.info("dispatcher.stopped", session_id=str(sid))

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task through the 9-step lifecycle."""
        sid = self.session.id
        thread: Thread | None = None

        try:
            # Step 1: Task already claimed (popped from queue with IN_PROGRESS status)
            logger.info("worker.lifecycle.start", task_id=str(task.id), title=task.title)

            # Step 2: Create worktree + branch
            thread = await self.thread_mgr.create_thread(self.session, task)
            self._active_threads[str(thread.id)] = thread

            # Step 3: Setup (symlinks + CLAUDE.md)
            thread = await self.thread_mgr.setup_thread(thread, self.session, task)

            # Step 4: Execute Worker (with quota retry)
            result = await self._run_with_quota_retry(thread, task)

            # Steps 5-8: Post-execution (commit, merge, push)
            await self._post_execution(task, thread, result)

        except Exception as e:
            logger.error("worker.lifecycle.error", task_id=str(task.id), error=str(e))
            # Mark task as failed, possibly requeue
            if task.retry_count < MAX_WORKER_RETRIES:
                task.error_context = str(e)
                self.queue.requeue(sid, task)
            else:
                task.status = TaskStatus.FAILED
                task.error_context = str(e)
                self.queue.update_task(sid, task)

            if thread:
                await self.thread_mgr.mark_failed(thread, str(e))

        finally:
            # Step 9: Cleanup
            if thread:
                self._active_threads.pop(str(thread.id), None)
                success = thread.status == ThreadStatus.COMPLETED
                await self.thread_mgr.cleanup_thread(thread, success=success)

    async def _run_with_quota_retry(self, thread: Thread, task: Task) -> WorkerResult:
        """Run Worker with exponential backoff on quota errors."""
        for attempt, delay in enumerate(self._quota_backoff_delays):
            result = await self.worker_runner.run(
                worktree_path=thread.worktree_path,
                thread_id=str(thread.id),
            )

            if not result.quota_exhausted:
                return result

            logger.warning(
                "worker.quota_retry",
                task_id=str(task.id),
                attempt=attempt + 1,
                delay=delay,
            )
            task.status = TaskStatus.PENDING_QUOTA
            self.queue.update_task(self.session.id, task)
            await asyncio.sleep(delay)

        # Final attempt after all backoff delays
        result = await self.worker_runner.run(
            worktree_path=thread.worktree_path,
            thread_id=str(thread.id),
        )

        if result.quota_exhausted:
            self._paused = True
            task.status = TaskStatus.FAILED
            task.error_context = "Quota exhausted after retries"
            self.queue.update_task(self.session.id, task)
            logger.error("dispatcher.quota_paused", session_id=str(self.session.id))

            # Broadcast quota exhaustion event via WebSocket
            if self._on_quota_exhausted:
                try:
                    await self._on_quota_exhausted(self.session.id, task)
                except Exception as e:
                    logger.warning("dispatcher.quota_broadcast_failed", error=str(e))

        return result

    async def _post_execution(self, task: Task, thread: Thread, result: WorkerResult) -> None:
        """Steps 5-8: commit, merge, push after Worker execution."""
        sid = self.session.id

        if not result.success:
            task.status = TaskStatus.FAILED
            task.error_context = "; ".join(result.errors) if result.errors else f"exit_code={result.exit_code}"
            self.queue.update_task(sid, task)
            thread.status = ThreadStatus.FAILED
            thread.exit_code = result.exit_code
            thread.summary = task.error_context
            return

        # Step 5: Check if Worker made changes and committed
        has_changes = await self.git.has_changes(thread.worktree_path)
        if has_changes:
            # Worker should have committed, but commit any remaining changes
            await self.git.commit_in_worktree(
                thread.worktree_path, f"auto-commit: {task.title}"
            )

        # Step 6: Merge into base branch
        try:
            # Must remove worktree before merging (git limitation)
            # So we first record the branch, cleanup worktree, then merge
            branch = thread.branch_name

            # Remove worktree (thread_manager.cleanup will handle this,
            # but we need the branch alive for merge)
            # Actually, we merge after cleanup — ThreadManager removes worktree but
            # we tell it NOT to delete the branch yet
            await self.git.remove_worktree(thread.worktree_path, delete_branch=False)
            thread.worktree_path = None  # Prevent double cleanup

            merge_commit = await self.git.merge_branch(branch, self.session.base_branch)

            # Step 8: Clean up the branch after successful merge
            try:
                from conductor.managers.git_manager import _run_git

                await _run_git(["branch", "-D", branch], cwd=self.git.repo_path)
            except GitError:
                pass

            # Mark task completed
            task.status = TaskStatus.COMPLETED
            self.queue.update_task(sid, task)
            thread.status = ThreadStatus.COMPLETED
            thread.exit_code = result.exit_code
            thread.summary = f"Merged to {self.session.base_branch} ({merge_commit[:8]})"

            logger.info("worker.lifecycle.merged", task_id=str(task.id), commit=merge_commit[:8])

        except GitError as e:
            # Step 7: Merge conflict — mark for resolution
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                logger.warning("worker.merge_conflict", task_id=str(task.id), error=str(e))
                task.status = TaskStatus.FAILED
                task.error_context = f"Merge conflict: {e}"
                self.queue.update_task(sid, task)
                thread.status = ThreadStatus.FAILED
                thread.summary = f"Merge conflict: {e}"
            else:
                raise

        # Step 9 partial: Log to PROGRESS.md if task completed
        if task.status == TaskStatus.COMPLETED and result.files_modified:
            try:
                await self.memory.append_progress(
                    self.git.repo_path,
                    task_title=task.title,
                    commit_id=merge_commit[:8] if task.status == TaskStatus.COMPLETED else "N/A",
                    problem=task.description,
                    solution=f"Completed by Worker (exit code {result.exit_code})",
                    prevention="N/A",
                    key_files=result.files_modified[:10],
                )
            except Exception as e:
                logger.warning("worker.progress_log_failed", error=str(e))
