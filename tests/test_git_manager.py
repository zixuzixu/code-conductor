"""Tests for GitManager — worktree, branch, and merge operations."""

import pytest

from conductor.managers.git_manager import GitManager, _run_git


@pytest.fixture
async def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    await _run_git(["init"], cwd=repo)
    await _run_git(["config", "user.email", "test@test.com"], cwd=repo)
    await _run_git(["config", "user.name", "Test"], cwd=repo)
    # Initial commit (git worktree needs at least one commit)
    (repo / "README.md").write_text("# Test Repo\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "init"], cwd=repo)
    return repo


@pytest.fixture
async def manager(git_repo):
    return GitManager(git_repo)


async def test_get_current_branch(manager):
    branch = await manager.get_current_branch()
    assert branch in ("main", "master")


async def test_branch_exists(manager, git_repo):
    current = await manager.get_current_branch()
    assert await manager.branch_exists(current) is True
    assert await manager.branch_exists("nonexistent-branch") is False


async def test_create_and_remove_worktree(manager):
    worktree_path = await manager.create_worktree("code-conductor/task-test-001")
    assert worktree_path.exists()
    assert (worktree_path / "README.md").exists()

    # Verify branch was created
    assert await manager.branch_exists("code-conductor/task-test-001") is True

    # List worktrees should show 2 (main + new)
    worktrees = await manager.list_worktrees()
    assert len(worktrees) == 2

    # Remove worktree
    await manager.remove_worktree(worktree_path, delete_branch=True)
    assert not worktree_path.exists()
    assert await manager.branch_exists("code-conductor/task-test-001") is False


async def test_commit_in_worktree(manager):
    worktree_path = await manager.create_worktree("code-conductor/task-commit-test")

    # Add a file in the worktree
    (worktree_path / "new_file.py").write_text("print('hello')\n")

    commit_hash = await manager.commit_in_worktree(worktree_path, "test commit")
    assert len(commit_hash) == 40  # full SHA

    # Cleanup
    await manager.remove_worktree(worktree_path)


async def test_has_changes(manager, git_repo):
    assert await manager.has_changes(git_repo) is False

    (git_repo / "dirty.txt").write_text("change")
    assert await manager.has_changes(git_repo) is True


async def test_merge_branch(manager, git_repo):
    base_branch = await manager.get_current_branch()

    # Create a worktree with a new branch, add a commit
    wt = await manager.create_worktree("code-conductor/task-merge-test")
    (wt / "feature.py").write_text("# feature\n")
    await _run_git(["add", "."], cwd=wt)
    await _run_git(["commit", "-m", "add feature"], cwd=wt)

    # Remove worktree first (can't merge while worktree is active on that branch)
    await manager.remove_worktree(wt, delete_branch=False)

    # Merge
    commit = await manager.merge_branch("code-conductor/task-merge-test", base_branch)
    assert len(commit) == 40

    # File should exist on base branch now
    assert (git_repo / "feature.py").exists()

    # Cleanup branch
    await _run_git(["branch", "-D", "code-conductor/task-merge-test"], cwd=git_repo)
