"""Merge conflict detection and resolution for concurrent worker branches."""

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from conductor.managers.git_manager import GitError, _run_git

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


@dataclass
class ConflictFile:
    """Represents a single file with a merge conflict."""

    path: str
    conflict_type: str  # "both_modified", "deleted_modified", "added_added"
    ours_content: str | None = None
    theirs_content: str | None = None


@dataclass
class ResolveResult:
    """Result of an automatic conflict resolution attempt."""

    resolved: list[str] = field(default_factory=list)  # successfully resolved file paths
    unresolved: list[ConflictFile] = field(default_factory=list)  # require manual intervention
    strategy_used: str = ""


# Mapping from git's two-letter status codes (during merge) to our conflict types.
_CONFLICT_TYPE_MAP: dict[str, str] = {
    "UU": "both_modified",
    "UD": "deleted_modified",
    "DU": "deleted_modified",
    "AA": "added_added",
    "AU": "added_added",
    "UA": "added_added",
}


class ConflictResolver:
    """Detects and resolves merge conflicts between worker branches."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect_conflicts(self, branch: str, target: str) -> list[ConflictFile]:
        """Perform a dry-run merge of *branch* into *target* and return conflicting files.

        The working tree is left unchanged — the trial merge happens in the index
        and is always aborted before returning.
        """
        original_branch = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo_path)

        try:
            await _run_git(["checkout", target], cwd=self.repo_path)

            try:
                await _run_git(["merge", "--no-commit", "--no-ff", branch], cwd=self.repo_path)
                # No conflicts — clean merge is possible.
                return []
            except GitError:
                # Merge failed — inspect the index for conflicts.
                return await self._collect_conflicts(branch, target)
            finally:
                # Always abort the in-progress merge so the repo stays clean.
                with contextlib.suppress(GitError):
                    await _run_git(["merge", "--abort"], cwd=self.repo_path)
        finally:
            if original_branch != target:
                with contextlib.suppress(GitError):
                    await _run_git(["checkout", original_branch], cwd=self.repo_path)

    async def auto_resolve(self, conflicts: list[ConflictFile], strategy: str) -> ResolveResult:
        """Attempt to automatically resolve *conflicts* using the given strategy.

        Strategies:
            ours   — keep the target branch version for every file.
            theirs — keep the source branch version for every file.
            smart  — auto-merge non-overlapping hunks; flag overlapping ones for manual work.
        """
        if strategy not in ("ours", "theirs", "smart"):
            raise ValueError(f"Unknown strategy: {strategy!r}. Must be 'ours', 'theirs', or 'smart'.")

        handler = {
            "ours": self._resolve_ours,
            "theirs": self._resolve_theirs,
            "smart": self._resolve_smart,
        }[strategy]

        result = await handler(conflicts)
        result.strategy_used = strategy

        logger.info(
            "auto_resolve_complete",
            strategy=strategy,
            resolved=len(result.resolved),
            unresolved=len(result.unresolved),
        )
        return result

    def create_resolution_task(self, conflicts: list[ConflictFile]) -> dict:
        """Create a task description for a Worker to manually resolve remaining conflicts."""
        file_descriptions = []
        for cf in conflicts:
            file_descriptions.append(f"- `{cf.path}` ({cf.conflict_type})")

        description = (
            "Resolve the following merge conflicts that could not be automatically resolved:\n\n"
            + "\n".join(file_descriptions)
            + "\n\nFor each file, inspect the conflict markers (<<<<<<< / ======= / >>>>>>>), "
            "decide on the correct resolution, remove the markers, and stage the file."
        )

        return {
            "title": "Resolve merge conflicts",
            "description": description,
            "conflict_files": [cf.path for cf in conflicts],
            "priority": "high",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _collect_conflicts(self, branch: str, target: str) -> list[ConflictFile]:
        """Parse ``git status --porcelain`` during a conflicted merge and build ConflictFile list."""
        output = await _run_git(["status", "--porcelain"], cwd=self.repo_path)

        conflicts: list[ConflictFile] = []
        for line in output.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            filepath = line[3:]

            conflict_type = _CONFLICT_TYPE_MAP.get(xy)
            if conflict_type is None:
                continue

            ours_content = await self._safe_show(f"{target}:{filepath}")
            theirs_content = await self._safe_show(f"{branch}:{filepath}")

            conflicts.append(
                ConflictFile(
                    path=filepath,
                    conflict_type=conflict_type,
                    ours_content=ours_content,
                    theirs_content=theirs_content,
                )
            )

        return conflicts

    async def _safe_show(self, ref: str) -> str | None:
        """Return file contents at *ref*, or ``None`` if the ref doesn't exist."""
        try:
            return await _run_git(["show", ref], cwd=self.repo_path)
        except GitError:
            return None

    # -- Strategy implementations ------------------------------------------

    async def _resolve_ours(self, conflicts: list[ConflictFile]) -> ResolveResult:
        result = ResolveResult()
        for cf in conflicts:
            if cf.ours_content is not None:
                filepath = self.repo_path / cf.path
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(cf.ours_content)
                await _run_git(["add", cf.path], cwd=self.repo_path)
                result.resolved.append(cf.path)
            else:
                # File was deleted on our side — keep it deleted.
                with contextlib.suppress(GitError):
                    await _run_git(["rm", cf.path], cwd=self.repo_path)
                result.resolved.append(cf.path)
        return result

    async def _resolve_theirs(self, conflicts: list[ConflictFile]) -> ResolveResult:
        result = ResolveResult()
        for cf in conflicts:
            if cf.theirs_content is not None:
                filepath = self.repo_path / cf.path
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(cf.theirs_content)
                await _run_git(["add", cf.path], cwd=self.repo_path)
                result.resolved.append(cf.path)
            else:
                with contextlib.suppress(GitError):
                    await _run_git(["rm", cf.path], cwd=self.repo_path)
                result.resolved.append(cf.path)
        return result

    async def _resolve_smart(self, conflicts: list[ConflictFile]) -> ResolveResult:
        """Try to merge non-overlapping changes; flag overlapping ones as unresolved."""
        result = ResolveResult()

        for cf in conflicts:
            if cf.conflict_type != "both_modified":
                # For add/add or delete/modified, fall back to "theirs" (the feature branch).
                if cf.theirs_content is not None:
                    filepath = self.repo_path / cf.path
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(cf.theirs_content)
                    await _run_git(["add", cf.path], cwd=self.repo_path)
                    result.resolved.append(cf.path)
                else:
                    result.unresolved.append(cf)
                continue

            # Both modified — check whether git's own merge left conflict markers.
            filepath = self.repo_path / cf.path
            if not filepath.exists():
                result.unresolved.append(cf)
                continue

            content = filepath.read_text()
            if "<<<<<<<" in content:
                # Overlapping changes — cannot auto-resolve.
                result.unresolved.append(cf)
            else:
                # Git managed a clean merge of this file (rare but possible).
                await _run_git(["add", cf.path], cwd=self.repo_path)
                result.resolved.append(cf.path)

        return result
