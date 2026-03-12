"""Priority task queue with atomic JSON persistence.

Each session has its own task_queue.json under ~/.code-conductor/sessions/{id}/.
Operations are guarded by file locks for cross-process safety.
"""

import json
from pathlib import Path
from uuid import UUID

import structlog
from filelock import FileLock

from conductor.core.constants import SESSIONS_DIR, TaskStatus
from conductor.core.models import Task

logger = structlog.get_logger()


def _queue_path(session_id: UUID) -> Path:
    return SESSIONS_DIR / str(session_id) / "task_queue.json"


def _lock_path(session_id: UUID) -> Path:
    return SESSIONS_DIR / str(session_id) / "task_queue.lock"


class QueueManager:
    """Priority task queue (P0 > P1 > P2) with atomic JSON persistence.

    All mutations are atomic: read → modify → write-to-tmp → os.replace.
    File locking ensures cross-process safety (multiple dispatchers).
    """

    def _read_tasks(self, session_id: UUID) -> list[Task]:
        path = _queue_path(session_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return [Task(**t) for t in data]

    def _write_tasks(self, session_id: UUID, tasks: list[Task]) -> None:
        path = _queue_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [t.model_dump(mode="json") for t in tasks]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        tmp.replace(path)

    def push(self, session_id: UUID, task: Task) -> Task:
        """Add a task to the session's priority queue.

        Tasks are stored sorted by priority (P0 first) then creation time.
        """
        lock = FileLock(_lock_path(session_id))
        with lock:
            tasks = self._read_tasks(session_id)
            # Avoid duplicates
            if any(t.id == task.id for t in tasks):
                logger.warning("queue.duplicate_push", task_id=str(task.id))
                return task
            tasks.append(task)
            tasks.sort(key=lambda t: (t.priority.sort_key, t.created_at))
            self._write_tasks(session_id, tasks)

        logger.info("queue.push", session_id=str(session_id), task_id=str(task.id), priority=task.priority.value)
        return task

    def pop(self, session_id: UUID) -> Task | None:
        """Atomically pop the highest-priority QUEUED task.

        Returns None if queue is empty or no tasks are QUEUED.
        """
        lock = FileLock(_lock_path(session_id))
        with lock:
            tasks = self._read_tasks(session_id)
            for task in tasks:
                if task.status == TaskStatus.QUEUED:
                    task.status = TaskStatus.IN_PROGRESS
                    self._write_tasks(session_id, tasks)
                    logger.info(
                        "queue.pop", session_id=str(session_id), task_id=str(task.id), priority=task.priority.value
                    )
                    return task
        return None

    def update_task(self, session_id: UUID, task: Task) -> None:
        """Update a task's state in the queue (status, retry_count, error_context, etc.)."""
        lock = FileLock(_lock_path(session_id))
        with lock:
            tasks = self._read_tasks(session_id)
            for i, t in enumerate(tasks):
                if t.id == task.id:
                    tasks[i] = task
                    break
            self._write_tasks(session_id, tasks)

    def requeue(self, session_id: UUID, task: Task) -> None:
        """Re-queue a failed task with incremented retry count."""
        task.status = TaskStatus.QUEUED
        task.retry_count += 1
        self.update_task(session_id, task)
        logger.info("queue.requeue", task_id=str(task.id), retry=task.retry_count)

    def get_all(self, session_id: UUID) -> list[Task]:
        """Get all tasks in the queue (all statuses)."""
        lock = FileLock(_lock_path(session_id))
        with lock:
            return self._read_tasks(session_id)

    def get_queued(self, session_id: UUID) -> list[Task]:
        """Get only QUEUED tasks, sorted by priority."""
        return [t for t in self.get_all(session_id) if t.status == TaskStatus.QUEUED]

    def recover_in_progress(self, session_id: UUID) -> list[Task]:
        """Crash recovery: find IN_PROGRESS tasks and re-queue them.

        Called on startup. Tasks stuck in IN_PROGRESS likely crashed mid-execution.
        """
        lock = FileLock(_lock_path(session_id))
        recovered = []
        with lock:
            tasks = self._read_tasks(session_id)
            for task in tasks:
                if task.status == TaskStatus.IN_PROGRESS:
                    task.status = TaskStatus.QUEUED
                    task.error_context = "Recovered after crash/restart"
                    recovered.append(task)
            if recovered:
                self._write_tasks(session_id, tasks)
                logger.warning("queue.crash_recovery", session_id=str(session_id), count=len(recovered))
        return recovered

    def remove_task(self, session_id: UUID, task_id: UUID) -> bool:
        """Remove a task from the queue entirely."""
        lock = FileLock(_lock_path(session_id))
        with lock:
            tasks = self._read_tasks(session_id)
            original_len = len(tasks)
            tasks = [t for t in tasks if t.id != task_id]
            if len(tasks) < original_len:
                self._write_tasks(session_id, tasks)
                return True
        return False
