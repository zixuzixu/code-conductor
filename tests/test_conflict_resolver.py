"""Tests for ConflictResolver — merge conflict detection and resolution."""

import contextlib

import pytest

from conductor.managers.conflict_resolver import ConflictFile, ConflictResolver, ResolveResult
from conductor.managers.git_manager import _run_git


@pytest.fixture
async def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit on main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    await _run_git(["init", "-b", "main"], cwd=repo)
    await _run_git(["config", "user.email", "test@test.com"], cwd=repo)
    await _run_git(["config", "user.name", "Test"], cwd=repo)
    (repo / "shared.py").write_text("line1\nline2\nline3\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "init"], cwd=repo)
    return repo


@pytest.fixture
async def resolver(git_repo):
    return ConflictResolver(git_repo)


# ------------------------------------------------------------------ #
# Helper: create a conflicting branch scenario
# ------------------------------------------------------------------ #

async def _make_conflict(repo, filename="shared.py"):
    """Create conflicting changes on main and a feature branch.

    Returns the feature branch name.
    """
    branch = "feature/conflict"

    # Create feature branch from current HEAD
    await _run_git(["checkout", "-b", branch], cwd=repo)
    (repo / filename).write_text("line1\nfeature_change\nline3\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "feature change"], cwd=repo)

    # Go back to main and make a conflicting change
    await _run_git(["checkout", "main"], cwd=repo)
    (repo / filename).write_text("line1\nmain_change\nline3\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "main change"], cwd=repo)

    return branch


async def _make_clean_merge(repo):
    """Create a feature branch with non-overlapping changes."""
    branch = "feature/clean"
    await _run_git(["checkout", "-b", branch], cwd=repo)
    (repo / "new_file.py").write_text("# new feature\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "add new file"], cwd=repo)
    await _run_git(["checkout", "main"], cwd=repo)
    return branch


# ------------------------------------------------------------------ #
# detect_conflicts
# ------------------------------------------------------------------ #

async def test_detect_conflicts_finds_conflict(resolver, git_repo):
    branch = await _make_conflict(git_repo)
    conflicts = await resolver.detect_conflicts(branch, "main")

    assert len(conflicts) == 1
    assert conflicts[0].path == "shared.py"
    assert conflicts[0].conflict_type == "both_modified"
    assert conflicts[0].ours_content is not None
    assert conflicts[0].theirs_content is not None


async def test_detect_conflicts_clean_merge(resolver, git_repo):
    branch = await _make_clean_merge(git_repo)
    conflicts = await resolver.detect_conflicts(branch, "main")
    assert conflicts == []


async def test_detect_conflicts_restores_branch(resolver, git_repo):
    """After detection the original branch should still be checked out."""
    branch = await _make_conflict(git_repo)
    original = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_repo)

    await resolver.detect_conflicts(branch, "main")

    current = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_repo)
    assert current == original


# ------------------------------------------------------------------ #
# auto_resolve — ours
# ------------------------------------------------------------------ #

async def test_auto_resolve_ours(resolver, git_repo):
    branch = await _make_conflict(git_repo)
    conflicts = await resolver.detect_conflicts(branch, "main")

    # Start a real merge so we can resolve
    await _run_git(["checkout", "main"], cwd=git_repo)
    with contextlib.suppress(Exception):
        await _run_git(["merge", "--no-commit", "--no-ff", branch], cwd=git_repo)

    result = await resolver.auto_resolve(conflicts, "ours")

    assert isinstance(result, ResolveResult)
    assert result.strategy_used == "ours"
    assert "shared.py" in result.resolved
    assert result.unresolved == []

    # Clean up
    await _run_git(["merge", "--abort"], cwd=git_repo)


# ------------------------------------------------------------------ #
# auto_resolve — theirs
# ------------------------------------------------------------------ #

async def test_auto_resolve_theirs(resolver, git_repo):
    branch = await _make_conflict(git_repo)
    conflicts = await resolver.detect_conflicts(branch, "main")

    await _run_git(["checkout", "main"], cwd=git_repo)
    with contextlib.suppress(Exception):
        await _run_git(["merge", "--no-commit", "--no-ff", branch], cwd=git_repo)

    result = await resolver.auto_resolve(conflicts, "theirs")

    assert result.strategy_used == "theirs"
    assert "shared.py" in result.resolved

    await _run_git(["merge", "--abort"], cwd=git_repo)


# ------------------------------------------------------------------ #
# auto_resolve — smart
# ------------------------------------------------------------------ #

async def test_auto_resolve_smart_with_overlap(resolver, git_repo):
    branch = await _make_conflict(git_repo)
    conflicts = await resolver.detect_conflicts(branch, "main")

    await _run_git(["checkout", "main"], cwd=git_repo)
    with contextlib.suppress(Exception):
        await _run_git(["merge", "--no-commit", "--no-ff", branch], cwd=git_repo)

    result = await resolver.auto_resolve(conflicts, "smart")

    assert result.strategy_used == "smart"
    # Overlapping changes should be unresolved
    assert len(result.unresolved) == 1
    assert result.unresolved[0].path == "shared.py"

    await _run_git(["merge", "--abort"], cwd=git_repo)


# ------------------------------------------------------------------ #
# auto_resolve — invalid strategy
# ------------------------------------------------------------------ #

async def test_auto_resolve_invalid_strategy(resolver):
    with pytest.raises(ValueError, match="Unknown strategy"):
        await resolver.auto_resolve([], "invalid")


# ------------------------------------------------------------------ #
# create_resolution_task
# ------------------------------------------------------------------ #

def test_create_resolution_task(resolver):
    conflicts = [
        ConflictFile(path="a.py", conflict_type="both_modified", ours_content="x", theirs_content="y"),
        ConflictFile(path="b.py", conflict_type="added_added", ours_content="x", theirs_content="y"),
    ]
    task = resolver.create_resolution_task(conflicts)

    assert task["title"] == "Resolve merge conflicts"
    assert "a.py" in task["description"]
    assert "b.py" in task["description"]
    assert task["conflict_files"] == ["a.py", "b.py"]
    assert task["priority"] == "high"


# ------------------------------------------------------------------ #
# ConflictFile / ResolveResult dataclasses
# ------------------------------------------------------------------ #

def test_conflict_file_defaults():
    cf = ConflictFile(path="x.py", conflict_type="both_modified")
    assert cf.ours_content is None
    assert cf.theirs_content is None


def test_resolve_result_defaults():
    r = ResolveResult()
    assert r.resolved == []
    assert r.unresolved == []
    assert r.strategy_used == ""
