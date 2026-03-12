"""Symlink strategy for Worker worktrees (§4.4).

Rules:
- Symlink read-shared or cross-worker coordination files
- Workers writing independently must be isolated
- PROGRESS.md: NO symlink — use `git -C <main_repo>` instead
- CLAUDE.md: Copy per worktree (task-specific)
"""

from pathlib import Path

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Files/dirs to symlink from main repo into worktree
SYMLINK_TARGETS = [
    "task_queue.json",    # shared queue, atomic access via lock
    "dev-task.lock",      # cross-worker coordination
    "node_modules",       # avoid redundant installs
    ".env",               # shared environment config
]

# Directories to create (isolated per worktree)
ISOLATED_DIRS = [
    "data",
]


def setup_worktree_links(worktree_path: Path, repo_path: Path) -> list[Path]:
    """Create symlinks in worktree pointing to main repo shared files.

    Only creates symlinks for files/dirs that exist in the main repo.
    Returns list of created symlinks.
    """
    created = []
    for target_name in SYMLINK_TARGETS:
        source = repo_path / target_name
        link = worktree_path / target_name

        if not source.exists():
            continue

        if link.exists() or link.is_symlink():
            continue

        link.symlink_to(source)
        created.append(link)
        logger.debug("symlink_created", link=str(link), target=str(source))

    # Create isolated directories
    for dir_name in ISOLATED_DIRS:
        isolated = worktree_path / dir_name
        isolated.mkdir(parents=True, exist_ok=True)

    logger.info(
        "worktree_links_setup",
        worktree=str(worktree_path),
        symlinks_created=len(created),
    )
    return created


def cleanup_worktree_links(worktree_path: Path) -> None:
    """Remove symlinks from worktree before deletion.

    This prevents `git worktree remove` from following symlinks
    and deleting shared files.
    """
    for target_name in SYMLINK_TARGETS:
        link = worktree_path / target_name
        if link.is_symlink():
            link.unlink()
            logger.debug("symlink_removed", link=str(link))
