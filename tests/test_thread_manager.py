"""Tests for ThreadManager — Thread lifecycle with git worktrees."""

import pytest

from conductor.core.constants import ThreadStatus
from conductor.core.models import Session, Task
from conductor.managers.git_manager import GitManager, _run_git
from conductor.managers.thread_manager import ThreadManager


@pytest.fixture
async def git_repo(tmp_path):
    """Create a temporary git repo with initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    await _run_git(["init"], cwd=repo)
    await _run_git(["config", "user.email", "test@test.com"], cwd=repo)
    await _run_git(["config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("# Test\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "init"], cwd=repo)
    return repo


@pytest.fixture
async def thread_mgr(git_repo):
    git = GitManager(git_repo)
    return ThreadManager(git)


@pytest.fixture
def session(git_repo):
    return Session(name="test-session", repo_path=str(git_repo))


@pytest.fixture
def task():
    return Task(title="Add user auth", description="Implement JWT-based authentication")


async def test_create_thread(thread_mgr, session, task):
    thread = await thread_mgr.create_thread(session, task)

    assert thread.status == ThreadStatus.SETTING_UP
    assert thread.branch_name is not None
    assert thread.branch_name.startswith("code-conductor/task-")
    assert thread.worktree_path is not None
    assert thread.task_id == task.id
    assert thread.session_id == session.id

    # Worktree should exist
    from pathlib import Path

    assert Path(thread.worktree_path).exists()

    # Cleanup
    await thread_mgr.cleanup_thread(thread, success=False)


async def test_setup_thread(thread_mgr, session, task):
    thread = await thread_mgr.create_thread(session, task)
    thread = await thread_mgr.setup_thread(thread, session, task)

    assert thread.status == ThreadStatus.RUNNING

    from pathlib import Path

    wt = Path(thread.worktree_path)
    claude_md = wt / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "Add user auth" in content
    assert "JWT-based authentication" in content

    # Cleanup
    await thread_mgr.cleanup_thread(thread, success=True)


async def test_cleanup_thread_success(thread_mgr, session, task):
    thread = await thread_mgr.create_thread(session, task)
    thread = await thread_mgr.setup_thread(thread, session, task)

    thread = await thread_mgr.cleanup_thread(
        thread,
        success=True,
        exit_code=0,
        summary="Auth implemented successfully",
    )

    assert thread.status == ThreadStatus.COMPLETED
    assert thread.exit_code == 0
    assert thread.summary == "Auth implemented successfully"

    from pathlib import Path

    assert not Path(thread.worktree_path).exists()


async def test_cleanup_thread_failure(thread_mgr, session, task):
    thread = await thread_mgr.create_thread(session, task)
    thread = await thread_mgr.cleanup_thread(
        thread,
        success=False,
        exit_code=1,
        summary="Build failed",
    )

    assert thread.status == ThreadStatus.FAILED
    assert thread.exit_code == 1


async def test_full_lifecycle(thread_mgr, session, task):
    """Test the full Thread lifecycle: create → setup → cleanup."""
    # Create
    thread = await thread_mgr.create_thread(session, task)
    assert thread.status == ThreadStatus.SETTING_UP

    # Setup
    thread = await thread_mgr.setup_thread(thread, session, task)
    assert thread.status == ThreadStatus.RUNNING

    # Simulate work in worktree
    from pathlib import Path

    wt = Path(thread.worktree_path)
    (wt / "auth.py").write_text("# JWT auth module\n")

    # Cleanup
    thread = await thread_mgr.cleanup_thread(
        thread, success=True, exit_code=0, summary="Done"
    )
    assert thread.status == ThreadStatus.COMPLETED
    assert not wt.exists()
