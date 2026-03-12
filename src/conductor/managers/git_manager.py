"""Git operations manager — worktree, branch, and merge management."""

import asyncio
import contextlib
import re
from pathlib import Path

import structlog

from conductor.core.constants import DEFAULT_WORKTREE_DIR

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Allowed characters in git branch names: alphanumeric, -, _, /, .
# Rejects shell metacharacters, spaces, control chars, .., ~, ^, :, ?, *, [, \
_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]*$")
_DANGEROUS_BRANCH_PATTERNS = ("..", "~", "^", ":", "?", "*", "[", "\\", " ", "@{")


def _validate_branch_name(branch_name: str) -> None:
    """Validate a branch name to prevent command injection and invalid git refs.

    Raises ValueError if the branch name contains dangerous characters.
    """
    if not branch_name or len(branch_name) > 255:
        raise ValueError(f"Invalid branch name length: {len(branch_name) if branch_name else 0}")

    for pattern in _DANGEROUS_BRANCH_PATTERNS:
        if pattern in branch_name:
            raise ValueError(f"Branch name contains forbidden pattern '{pattern}': {branch_name}")

    if not _SAFE_BRANCH_RE.match(branch_name):
        raise ValueError(f"Branch name contains invalid characters: {branch_name}")

    if branch_name.startswith("-"):
        raise ValueError(f"Branch name must not start with '-': {branch_name}")

    if branch_name.endswith(".lock") or branch_name.endswith("/"):
        raise ValueError(f"Branch name has invalid suffix: {branch_name}")


def _validate_path_within(path: Path, parent: Path) -> None:
    """Ensure resolved path is under the expected parent directory.

    Raises ValueError on path traversal attempts.
    """
    resolved = path.resolve()
    parent_resolved = parent.resolve()
    if not str(resolved).startswith(str(parent_resolved) + "/") and resolved != parent_resolved:
        raise ValueError(f"Path escapes allowed directory: {resolved} is not under {parent_resolved}")


class GitError(Exception):
    """Raised when a git command fails."""

    def __init__(self, command: str, returncode: int, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"git command failed (rc={returncode}): {command}\n{stderr}")


async def _run_git(args: list[str], cwd: str | Path | None = None) -> str:
    """Run a git command asynchronously and return stdout.

    Raises GitError on non-zero exit code.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode().strip()
    stderr = stderr_bytes.decode().strip()

    if proc.returncode != 0:
        raise GitError(command=f"git {' '.join(args)}", returncode=proc.returncode, stderr=stderr)

    return stdout


class GitManager:
    """Manages git worktrees, branches, and merge operations for a repository."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()
        self.worktree_base = self.repo_path / DEFAULT_WORKTREE_DIR

    async def get_current_branch(self) -> str:
        return await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo_path)

    async def branch_exists(self, branch_name: str) -> bool:
        _validate_branch_name(branch_name)
        try:
            await _run_git(["rev-parse", "--verify", branch_name], cwd=self.repo_path)
            return True
        except GitError:
            return False

    async def list_worktrees(self) -> list[dict[str, str]]:
        """List all worktrees. Returns list of {path, branch, commit} dicts."""
        output = await _run_git(["worktree", "list", "--porcelain"], cwd=self.repo_path)
        worktrees = []
        current: dict[str, str] = {}
        for line in output.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line.split(" ", 1)[1]}
            elif line.startswith("HEAD "):
                current["commit"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                current["branch"] = line.split(" ", 1)[1].removeprefix("refs/heads/")
            elif line == "bare":
                current["bare"] = "true"
        if current:
            worktrees.append(current)
        return worktrees

    async def create_worktree(self, branch_name: str) -> Path:
        """Create a new worktree with a new branch.

        Branch naming: code-conductor/task-{timestamp}-{id}
        Worktree path: <repo>/worktree/<branch_name>/

        Returns the absolute worktree path.
        """
        _validate_branch_name(branch_name)

        # Sanitize branch name for filesystem (replace / with -)
        dir_name = branch_name.replace("/", "-")
        worktree_path = self.worktree_base / dir_name

        # Ensure worktree path doesn't escape the repo
        _validate_path_within(worktree_path, self.worktree_base)

        self.worktree_base.mkdir(parents=True, exist_ok=True)

        await _run_git(
            ["worktree", "add", "-b", branch_name, str(worktree_path)],
            cwd=self.repo_path,
        )

        logger.info("worktree_created", branch=branch_name, path=str(worktree_path))
        return worktree_path

    async def remove_worktree(self, worktree_path: str | Path, *, delete_branch: bool = True) -> None:
        """Remove a worktree and optionally delete its branch."""
        worktree_path = Path(worktree_path)

        # Ensure worktree path is within expected base directory
        _validate_path_within(worktree_path, self.worktree_base)

        # Get branch name before removal
        branch_name = None
        if delete_branch:
            with contextlib.suppress(GitError):
                branch_name = await _run_git(
                    ["rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=worktree_path,
                )

        # Force remove worktree (handles dirty state)
        await _run_git(["worktree", "remove", "--force", str(worktree_path)], cwd=self.repo_path)

        # Delete the branch
        if delete_branch and branch_name and branch_name != "HEAD":
            try:
                await _run_git(["branch", "-D", branch_name], cwd=self.repo_path)
            except GitError:
                logger.warning("branch_delete_failed", branch=branch_name)

        logger.info("worktree_removed", path=str(worktree_path), branch_deleted=branch_name)

    async def merge_branch(self, source_branch: str, target_branch: str = "main") -> str:
        """Merge source_branch into target_branch.

        Returns the merge commit hash. Raises GitError on conflict.
        """
        _validate_branch_name(source_branch)
        _validate_branch_name(target_branch)

        current = await self.get_current_branch()

        try:
            # Checkout target
            await _run_git(["checkout", target_branch], cwd=self.repo_path)
            # Merge
            await _run_git(["merge", source_branch, "--no-edit"], cwd=self.repo_path)
            commit = await _run_git(["rev-parse", "HEAD"], cwd=self.repo_path)
            logger.info("branch_merged", source=source_branch, target=target_branch, commit=commit)
            return commit
        except GitError:
            # Abort failed merge and restore
            with contextlib.suppress(GitError):
                await _run_git(["merge", "--abort"], cwd=self.repo_path)
            raise
        finally:
            # Restore original branch if different
            if current != target_branch:
                with contextlib.suppress(GitError):
                    await _run_git(["checkout", current], cwd=self.repo_path)

    async def fetch_origin(self) -> None:
        await _run_git(["fetch", "origin"], cwd=self.repo_path)

    async def push(self, branch: str = "main", remote: str = "origin") -> None:
        _validate_branch_name(branch)
        await _run_git(["push", remote, branch], cwd=self.repo_path)

    async def commit_in_worktree(self, worktree_path: str | Path, message: str) -> str:
        """Stage all changes and commit in a worktree. Returns commit hash."""
        wt = str(worktree_path)
        await _run_git(["add", "-A"], cwd=wt)
        await _run_git(["commit", "-m", message], cwd=wt)
        return await _run_git(["rev-parse", "HEAD"], cwd=wt)

    async def has_changes(self, path: str | Path) -> bool:
        """Check if there are uncommitted changes at the given path."""
        try:
            output = await _run_git(["status", "--porcelain"], cwd=path)
            return bool(output)
        except GitError:
            return False
