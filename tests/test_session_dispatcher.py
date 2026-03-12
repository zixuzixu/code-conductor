"""Tests for SessionDispatcher quota handling."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from conductor.core.constants import TaskStatus, ThreadStatus
from conductor.core.models import Session, Task, Thread
from conductor.managers.session_dispatcher import SessionDispatcher
from conductor.managers.worker_runner import WorkerResult


def _make_session(**kw):
    defaults = dict(id=uuid4(), name="test", repo_path="/tmp/repo", base_branch="main", max_workers=2)
    defaults.update(kw)
    return Session(**defaults)


def _make_task(**kw):
    defaults = dict(id=uuid4(), title="test task", description="do something", priority="p1")
    defaults.update(kw)
    return Task(**defaults)


@pytest.fixture()
def dispatcher():
    session = _make_session()
    queue = MagicMock()
    thread_mgr = AsyncMock()
    git = AsyncMock()
    memory = AsyncMock()
    runner = AsyncMock()
    d = SessionDispatcher(session, queue, thread_mgr, git, memory, runner)
    return d


@pytest.mark.asyncio
async def test_quota_retry_succeeds_on_second_attempt(dispatcher):
    """Task succeeds after one quota failure and one successful retry."""
    task = _make_task()
    thread = MagicMock(spec=Thread)
    thread.id = uuid4()
    thread.worktree_path = "/tmp/wt"
    thread.branch_name = "test-branch"
    thread.status = ThreadStatus.RUNNING

    dispatcher.thread_mgr.create_thread.return_value = thread
    dispatcher.thread_mgr.setup_thread.return_value = thread

    # First call: quota error. Second call: success.
    fail_result = WorkerResult(exit_code=1, quota_exhausted=True, errors=["rate limit exceeded"])
    ok_result = WorkerResult(exit_code=0, success=True, quota_exhausted=False)
    dispatcher.worker_runner.run = AsyncMock(side_effect=[fail_result, ok_result])

    dispatcher.git.has_changes = AsyncMock(return_value=False)
    dispatcher.git.merge_branch = AsyncMock(return_value="abc123def")
    dispatcher.git.remove_worktree = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await dispatcher._execute_task(task)

    assert dispatcher.worker_runner.run.call_count == 2


@pytest.mark.asyncio
async def test_quota_retry_exhausted_pauses_dispatch(dispatcher):
    """After max quota retries, dispatcher pauses and task is FAILED."""
    task = _make_task()
    thread = MagicMock(spec=Thread)
    thread.id = uuid4()
    thread.worktree_path = "/tmp/wt"
    thread.status = ThreadStatus.RUNNING

    dispatcher.thread_mgr.create_thread.return_value = thread
    dispatcher.thread_mgr.setup_thread.return_value = thread

    fail_result = WorkerResult(exit_code=1, quota_exhausted=True, errors=["rate limit"])
    dispatcher.worker_runner.run = AsyncMock(return_value=fail_result)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await dispatcher._execute_task(task)

    # After all retries exhausted, dispatch should be paused
    assert dispatcher._paused
    assert task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_resume_dispatch_after_quota_pause(dispatcher):
    """resume_dispatch() clears the paused state."""
    dispatcher._paused = True
    dispatcher._running = True
    dispatcher.resume_dispatch()
    assert not dispatcher._paused
