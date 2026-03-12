"""Tests for QueueManager — priority queue with atomic JSON persistence."""

import pytest

from conductor.core.constants import Priority, TaskStatus
from conductor.core.models import Task
from conductor.managers.queue_manager import QueueManager


@pytest.fixture()
def qm(tmp_path, monkeypatch):
    """QueueManager with sessions dir redirected to tmp."""
    monkeypatch.setattr("conductor.managers.queue_manager.SESSIONS_DIR", tmp_path)
    (tmp_path / "test-session").mkdir()
    return QueueManager()


SESSION_ID_STR = "test-session"


@pytest.fixture()
def session_id():
    from uuid import UUID

    # Use a deterministic UUID for testing
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture()
def qm_with_id(tmp_path, monkeypatch, session_id):
    """QueueManager with a proper UUID-based session dir."""
    monkeypatch.setattr("conductor.managers.queue_manager.SESSIONS_DIR", tmp_path)
    (tmp_path / str(session_id)).mkdir()
    return QueueManager()


def test_push_and_pop(qm_with_id, session_id):
    """Push a task, pop it back."""
    task = Task(title="Fix bug", priority=Priority.P1)
    qm_with_id.push(session_id, task)

    popped = qm_with_id.pop(session_id)
    assert popped is not None
    assert popped.id == task.id
    assert popped.status == TaskStatus.IN_PROGRESS


def test_pop_empty(qm_with_id, session_id):
    """Pop from empty queue returns None."""
    assert qm_with_id.pop(session_id) is None


def test_priority_ordering(qm_with_id, session_id):
    """P0 tasks are popped before P1 before P2."""
    t_p2 = Task(title="Docs", priority=Priority.P2)
    t_p0 = Task(title="Urgent", priority=Priority.P0)
    t_p1 = Task(title="Feature", priority=Priority.P1)

    qm_with_id.push(session_id, t_p2)
    qm_with_id.push(session_id, t_p0)
    qm_with_id.push(session_id, t_p1)

    first = qm_with_id.pop(session_id)
    second = qm_with_id.pop(session_id)
    third = qm_with_id.pop(session_id)

    assert first.id == t_p0.id
    assert second.id == t_p1.id
    assert third.id == t_p2.id


def test_duplicate_push(qm_with_id, session_id):
    """Pushing the same task twice doesn't create duplicates."""
    task = Task(title="Fix bug")
    qm_with_id.push(session_id, task)
    qm_with_id.push(session_id, task)

    all_tasks = qm_with_id.get_all(session_id)
    assert len(all_tasks) == 1


def test_get_queued(qm_with_id, session_id):
    """get_queued only returns QUEUED tasks."""
    t1 = Task(title="Task 1")
    t2 = Task(title="Task 2")
    qm_with_id.push(session_id, t1)
    qm_with_id.push(session_id, t2)

    # Pop one (changes to IN_PROGRESS)
    qm_with_id.pop(session_id)

    queued = qm_with_id.get_queued(session_id)
    assert len(queued) == 1


def test_requeue(qm_with_id, session_id):
    """Requeue increments retry count and sets status to QUEUED."""
    task = Task(title="Flaky task")
    qm_with_id.push(session_id, task)

    popped = qm_with_id.pop(session_id)
    assert popped.retry_count == 0

    qm_with_id.requeue(session_id, popped)

    all_tasks = qm_with_id.get_all(session_id)
    requeued = next(t for t in all_tasks if t.id == task.id)
    assert requeued.status == TaskStatus.QUEUED
    assert requeued.retry_count == 1


def test_update_task(qm_with_id, session_id):
    """update_task persists task changes."""
    task = Task(title="Update me")
    qm_with_id.push(session_id, task)

    task.status = TaskStatus.COMPLETED
    task.error_context = "All good"
    qm_with_id.update_task(session_id, task)

    all_tasks = qm_with_id.get_all(session_id)
    updated = next(t for t in all_tasks if t.id == task.id)
    assert updated.status == TaskStatus.COMPLETED
    assert updated.error_context == "All good"


def test_recover_in_progress(qm_with_id, session_id):
    """Crash recovery: IN_PROGRESS tasks are re-queued."""
    t1 = Task(title="Crashed task")
    t2 = Task(title="Queued task")
    qm_with_id.push(session_id, t1)
    qm_with_id.push(session_id, t2)

    # Simulate crash: pop t1 (now IN_PROGRESS), then "restart"
    qm_with_id.pop(session_id)

    recovered = qm_with_id.recover_in_progress(session_id)
    assert len(recovered) == 1
    assert recovered[0].id == t1.id

    # t1 should now be QUEUED again
    all_tasks = qm_with_id.get_all(session_id)
    t1_recovered = next(t for t in all_tasks if t.id == t1.id)
    assert t1_recovered.status == TaskStatus.QUEUED
    assert "crash" in t1_recovered.error_context.lower()


def test_remove_task(qm_with_id, session_id):
    """Remove a task from the queue."""
    task = Task(title="To remove")
    qm_with_id.push(session_id, task)

    assert qm_with_id.remove_task(session_id, task.id) is True
    assert len(qm_with_id.get_all(session_id)) == 0

    # Removing again returns False
    assert qm_with_id.remove_task(session_id, task.id) is False
