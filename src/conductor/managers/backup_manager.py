"""Automatic backup management via git tags for safe merge operations."""

import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

from conductor.managers.git_manager import GitError, _run_git

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_TAG_PREFIX = "backup"


class BackupManager:
    """Creates and manages git-tag-based backup points before merge operations."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

    async def create_backup(self, session_id: str) -> str:
        """Create a backup tag at the current HEAD for the given session.

        Returns the tag name (``backup/{session_id}/{timestamp}``).
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        tag_name = f"{_TAG_PREFIX}/{session_id}/{timestamp}"

        await _run_git(["tag", tag_name], cwd=self.repo_path)

        logger.info("backup_created", tag=tag_name, session_id=session_id)
        return tag_name

    async def list_backups(self, session_id: str) -> list[dict]:
        """List all backup tags for a session.

        Returns a list of dicts with keys: ``tag``, ``commit``, ``timestamp``.
        """
        pattern = f"{_TAG_PREFIX}/{session_id}/*"
        try:
            output = await _run_git(["tag", "-l", pattern], cwd=self.repo_path)
        except GitError:
            return []

        if not output:
            return []

        backups: list[dict] = []
        for tag in output.splitlines():
            tag = tag.strip()
            if not tag:
                continue
            commit = await self._tag_commit(tag)
            # Extract timestamp from the last path segment.
            parts = tag.split("/")
            ts_str = parts[-1] if len(parts) >= 3 else ""
            backups.append({"tag": tag, "commit": commit, "timestamp": ts_str})

        return backups

    async def restore_backup(self, tag_name: str) -> bool:
        """Hard-reset the current branch to the commit pointed to by *tag_name*.

        Returns ``True`` on success, ``False`` if the tag doesn't exist.
        """
        try:
            commit = await _run_git(["rev-parse", tag_name], cwd=self.repo_path)
        except GitError:
            logger.warning("restore_backup_tag_not_found", tag=tag_name)
            return False

        await _run_git(["reset", "--hard", commit], cwd=self.repo_path)
        logger.info("backup_restored", tag=tag_name, commit=commit)
        return True

    async def cleanup_old_backups(self, max_age_days: int = 30) -> list[str]:
        """Delete backup tags older than *max_age_days*.

        Returns the list of deleted tag names.
        """
        try:
            output = await _run_git(["tag", "-l", f"{_TAG_PREFIX}/*/*"], cwd=self.repo_path)
        except GitError:
            return []

        if not output:
            return []

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)
        deleted: list[str] = []

        for tag in output.splitlines():
            tag = tag.strip()
            if not tag:
                continue

            parts = tag.split("/")
            if len(parts) < 3:
                continue

            ts_str = parts[-1]
            try:
                tag_time = datetime.strptime(ts_str, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            if tag_time < cutoff:
                with contextlib.suppress(GitError):
                    await _run_git(["tag", "-d", tag], cwd=self.repo_path)
                    deleted.append(tag)
                    logger.info("backup_deleted", tag=tag)

        return deleted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _tag_commit(self, tag: str) -> str:
        """Resolve a tag to its commit SHA."""
        try:
            return await _run_git(["rev-parse", tag], cwd=self.repo_path)
        except GitError:
            return ""
