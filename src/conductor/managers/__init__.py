"""Manager modules for Code Conductor."""

from conductor.managers.backup_manager import BackupManager
from conductor.managers.conflict_resolver import ConflictFile, ConflictResolver, ResolveResult
from conductor.managers.git_manager import GitManager
from conductor.managers.memory_manager import MemoryManager
from conductor.managers.plan_manager import PlanManager
from conductor.managers.queue_manager import QueueManager
from conductor.managers.session_dispatcher import SessionDispatcher
from conductor.managers.session_manager import SessionManager
from conductor.managers.thread_manager import ThreadManager
from conductor.managers.worker_runner import WorkerRunner

__all__ = [
    "BackupManager",
    "ConflictFile",
    "ConflictResolver",
    "GitManager",
    "MemoryManager",
    "PlanManager",
    "QueueManager",
    "ResolveResult",
    "SessionDispatcher",
    "SessionManager",
    "ThreadManager",
    "WorkerRunner",
]
