"""Memory and progress management with file locking.

MEMORY.md — Global user preferences and facts (in conductor home).
PROGRESS.md — Lessons learned per task (in main repo, NOT symlinked).
"""

from datetime import datetime
from pathlib import Path

import structlog
from filelock import FileLock

from conductor.core.constants import MEMORY_FILE

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class MemoryManager:
    """Manages MEMORY.md (global prefs) and PROGRESS.md (per-repo lessons)."""

    def __init__(self, memory_path: Path | None = None):
        self.memory_path = memory_path or MEMORY_FILE
        self._memory_lock = FileLock(str(self.memory_path) + ".lock")

    # --- MEMORY.md ---

    def read_memory(self) -> str:
        if not self.memory_path.exists():
            return ""
        with self._memory_lock:
            return self.memory_path.read_text()

    def write_memory(self, content: str) -> None:
        with self._memory_lock:
            self.memory_path.write_text(content)
        logger.info("memory_updated", path=str(self.memory_path))

    def update_memory(self, key: str, value: str) -> None:
        """Add or update a key-value entry in MEMORY.md.

        Entries are stored as `- **key**: value` lines under the Memory heading.
        """
        with self._memory_lock:
            content = self.memory_path.read_text() if self.memory_path.exists() else "# Memory\n\n"
            marker = f"- **{key}**:"
            lines = content.splitlines()
            updated = False
            for i, line in enumerate(lines):
                if line.startswith(marker):
                    lines[i] = f"- **{key}**: {value}"
                    updated = True
                    break
            if not updated:
                lines.append(f"- **{key}**: {value}")
            self.memory_path.write_text("\n".join(lines) + "\n")

    # --- PROGRESS.md ---

    @staticmethod
    def _progress_path(repo_path: str | Path) -> Path:
        resolved = Path(repo_path).resolve()
        # Ensure the repo_path is an absolute directory (not a relative path trick)
        if not resolved.is_absolute():
            raise ValueError(f"repo_path must be absolute: {repo_path}")
        return resolved / "PROGRESS.md"

    def read_progress(self, repo_path: str | Path) -> str:
        path = self._progress_path(repo_path)
        if not path.exists():
            return ""
        return path.read_text()

    async def append_progress(
        self,
        repo_path: str | Path,
        *,
        task_title: str,
        commit_id: str,
        problem: str,
        solution: str,
        prevention: str,
        key_files: list[str],
    ) -> None:
        """Append a lesson learned entry to PROGRESS.md in the main repo.

        Uses `git -C <main_repo>` approach — writes directly to main repo,
        NOT via symlink (§6 requirement).
        """
        path = self._progress_path(repo_path)
        lock = FileLock(str(path) + ".lock")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        entry = f"""
## [{now}] Task: {task_title}
- **Commit**: {commit_id}
- **Problem**: {problem}
- **Solution**: {solution}
- **Prevention**: {prevention}
- **Key Files**: {', '.join(key_files)}
"""

        with lock:
            existing = path.read_text() if path.exists() else "# Progress Log\n"
            path.write_text(existing + entry)

        logger.info("progress_appended", repo=str(repo_path), task=task_title)
