"""Thread lifecycle management — create, setup, run, cleanup.

A Thread represents a single Worker task execution with:
- Isolated git branch (code-conductor/task-{timestamp}-{id})
- Dedicated worktree (<repo>/worktree/<dir_name>/)
- Task-specific CLAUDE.md instructions
"""

import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

import structlog

from conductor.core.constants import THREAD_BRANCH_PREFIX, ThreadStatus
from conductor.core.models import Session, Task, Thread
from conductor.managers.git_manager import GitManager
from conductor.managers.symlink_strategy import cleanup_worktree_links, setup_worktree_links

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Template for CLAUDE.md written into each Worker worktree
CLAUDE_MD_TEMPLATE = """\
# Worker Instructions

## Task
**{task_title}**

{task_description}

## Rules
- Stay within this worktree directory. Do NOT modify files outside.
- Commit your changes when done.
- If you encounter an error 3+ times, stop and report the issue.
- Write clean, tested code. Run existing tests before committing.

## Context
- Session: {session_name}
- Branch: {branch_name}
- Base branch: {base_branch}
- Priority: {priority}
"""


def _make_branch_name(task_id: UUID) -> str:
    """Generate branch name: code-conductor/task-{timestamp}-{short_id}."""
    ts = int(time.time())
    short_id = str(task_id)[:8]
    return f"{THREAD_BRANCH_PREFIX}-{ts}-{short_id}"


class ThreadManager:
    """Manages Thread lifecycle: create worktree, setup symlinks, write CLAUDE.md, cleanup."""

    def __init__(self, git_manager: GitManager):
        self.git = git_manager

    async def create_thread(self, session: Session, task: Task) -> Thread:
        """Create a new Thread with an isolated worktree and branch.

        Steps:
        1. Generate branch name
        2. Create git worktree
        3. Create Thread model
        """
        branch_name = _make_branch_name(task.id)
        worktree_path = await self.git.create_worktree(branch_name)

        thread = Thread(
            session_id=session.id,
            task_id=task.id,
            status=ThreadStatus.SETTING_UP,
            branch_name=branch_name,
            worktree_path=str(worktree_path),
        )

        logger.info(
            "thread_created",
            thread_id=str(thread.id),
            branch=branch_name,
            task=task.title,
        )
        return thread

    async def setup_thread(self, thread: Thread, session: Session, task: Task) -> Thread:
        """Setup worktree: symlinks + CLAUDE.md.

        Transitions: SETTING_UP → RUNNING (ready for Worker).
        """
        worktree = Path(thread.worktree_path)

        # Create symlinks for shared files
        setup_worktree_links(worktree, self.git.repo_path)

        # Write task-specific CLAUDE.md
        claude_md = CLAUDE_MD_TEMPLATE.format(
            task_title=task.title,
            task_description=task.description,
            session_name=session.name,
            branch_name=thread.branch_name,
            base_branch=session.base_branch,
            priority=task.priority.value.upper(),
        )
        (worktree / "CLAUDE.md").write_text(claude_md)

        thread.status = ThreadStatus.RUNNING
        thread.updated_at = datetime.now()

        logger.info("thread_setup_complete", thread_id=str(thread.id))
        return thread

    async def cleanup_thread(
        self,
        thread: Thread,
        *,
        success: bool,
        exit_code: int | None = None,
        summary: str | None = None,
    ) -> Thread:
        """Cleanup after Worker completion.

        Steps:
        1. Update thread status
        2. Remove symlinks (prevent shared file deletion)
        3. Remove worktree + branch

        CRITICAL: Update thread status BEFORE cleanup (§5.1 Step 9).
        """
        # Step 1: Update status first
        thread.status = ThreadStatus.COMPLETED if success else ThreadStatus.FAILED
        thread.exit_code = exit_code
        thread.summary = summary
        thread.updated_at = datetime.now()

        # Step 2: Remove symlinks before worktree removal
        if thread.worktree_path:
            worktree = Path(thread.worktree_path)
            if worktree.exists():
                cleanup_worktree_links(worktree)

                # Step 3: Remove worktree + branch
                try:
                    await self.git.remove_worktree(worktree, delete_branch=True)
                except Exception as e:
                    logger.error("worktree_cleanup_failed", thread_id=str(thread.id), error=str(e))

        logger.info(
            "thread_cleaned_up",
            thread_id=str(thread.id),
            status=thread.status.value,
        )
        return thread

    async def mark_failed(self, thread: Thread, error: str) -> Thread:
        """Mark a thread as failed without full cleanup (e.g., crash recovery)."""
        thread.status = ThreadStatus.FAILED
        thread.summary = f"Error: {error}"
        thread.updated_at = datetime.now()
        return thread
