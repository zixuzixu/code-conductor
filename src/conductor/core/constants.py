"""Path constants and status enumerations for Code Conductor."""

import os
from enum import StrEnum
from pathlib import Path

# --- Path Constants ---

CONDUCTOR_HOME = Path(os.environ.get("CODE_CONDUCTOR_HOME", Path.home() / ".code-conductor"))
CONFIG_FILE = CONDUCTOR_HOME / "config.yaml"
MEMORY_FILE = CONDUCTOR_HOME / "MEMORY.md"
SESSIONS_DIR = CONDUCTOR_HOME / "sessions"
PLANS_DIR = CONDUCTOR_HOME / "plans"
BACKUPS_DIR = CONDUCTOR_HOME / "backups"

DEFAULT_WORKTREE_DIR = "worktree"
THREAD_BRANCH_PREFIX = "code-conductor/task"
CONFLICT_BRANCH_PREFIX = "code-conductor/conflict"


# --- Status Enumerations ---


class SessionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ThreadStatus(StrEnum):
    PENDING = "pending"
    SETTING_UP = "setting_up"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING_QUOTA = "pending_quota"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    PENDING_QUOTA = "pending_quota"


class Priority(StrEnum):
    P0 = "p0"  # Immediate — active conversation
    P1 = "p1"  # Standard — features/bugs
    P2 = "p2"  # Background — refactoring/docs

    @property
    def sort_key(self) -> int:
        return {"p0": 0, "p1": 1, "p2": 2}[self.value]


# --- Worker Constants ---

CLAUDE_CMD = "claude"
CLAUDE_ARGS = ["-p", "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]
WORKER_PROMPT = "干活；干完活退出 (exit)"  # noqa: RUF001

MAX_WORKER_RETRIES = 3
WORKER_THINKING_TIMEOUT_S = 180
WORKER_NO_OUTPUT_TIMEOUT_S = 120
THREAD_POLL_INTERVAL_S = 3
