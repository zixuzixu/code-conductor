"""Tests for BackupManager — git-tag-based backup and restore."""

import pytest

from conductor.managers.backup_manager import BackupManager
from conductor.managers.git_manager import _run_git


@pytest.fixture
async def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    await _run_git(["init", "-b", "main"], cwd=repo)
    await _run_git(["config", "user.email", "test@test.com"], cwd=repo)
    await _run_git(["config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("# Test\n")
    await _run_git(["add", "."], cwd=repo)
    await _run_git(["commit", "-m", "init"], cwd=repo)
    return repo


@pytest.fixture
async def manager(git_repo):
    return BackupManager(git_repo)


# ------------------------------------------------------------------ #
# create_backup
# ------------------------------------------------------------------ #

async def test_create_backup_returns_tag_name(manager):
    tag = await manager.create_backup("sess-001")
    assert tag.startswith("backup/sess-001/")


async def test_create_backup_tag_exists_in_repo(manager, git_repo):
    tag = await manager.create_backup("sess-001")
    output = await _run_git(["tag", "-l", tag], cwd=git_repo)
    assert output.strip() == tag


# ------------------------------------------------------------------ #
# list_backups
# ------------------------------------------------------------------ #

async def test_list_backups_empty(manager):
    backups = await manager.list_backups("nonexistent")
    assert backups == []


async def test_list_backups_returns_created(manager):
    await manager.create_backup("sess-002")
    await manager.create_backup("sess-002")

    backups = await manager.list_backups("sess-002")
    assert len(backups) >= 2
    for b in backups:
        assert "tag" in b
        assert "commit" in b
        assert "timestamp" in b
        assert b["tag"].startswith("backup/sess-002/")


async def test_list_backups_isolates_sessions(manager):
    await manager.create_backup("sess-A")
    await manager.create_backup("sess-B")

    a_backups = await manager.list_backups("sess-A")
    b_backups = await manager.list_backups("sess-B")
    assert len(a_backups) == 1
    assert len(b_backups) == 1
    assert a_backups[0]["tag"] != b_backups[0]["tag"]


# ------------------------------------------------------------------ #
# restore_backup
# ------------------------------------------------------------------ #

async def test_restore_backup_success(manager, git_repo):
    tag = await manager.create_backup("sess-003")

    # Make a new commit after the backup
    (git_repo / "extra.txt").write_text("after backup\n")
    await _run_git(["add", "."], cwd=git_repo)
    await _run_git(["commit", "-m", "post-backup"], cwd=git_repo)

    assert (git_repo / "extra.txt").exists()

    result = await manager.restore_backup(tag)
    assert result is True

    # extra.txt should be gone after restoring
    assert not (git_repo / "extra.txt").exists()


async def test_restore_backup_nonexistent_tag(manager):
    result = await manager.restore_backup("backup/fake/20200101T000000")
    assert result is False


# ------------------------------------------------------------------ #
# cleanup_old_backups
# ------------------------------------------------------------------ #

async def test_cleanup_old_backups_removes_old(manager, git_repo):
    # Manually create a tag with an old timestamp
    old_tag = "backup/sess-004/20200101T000000000000"
    await _run_git(["tag", old_tag], cwd=git_repo)

    # Create a recent one via the API
    recent_tag = await manager.create_backup("sess-004")

    deleted = await manager.cleanup_old_backups(max_age_days=30)

    assert old_tag in deleted
    assert recent_tag not in deleted

    # Verify old tag is gone
    output = await _run_git(["tag", "-l", old_tag], cwd=git_repo)
    assert output.strip() == ""


async def test_cleanup_old_backups_keeps_recent(manager):
    tag = await manager.create_backup("sess-005")
    deleted = await manager.cleanup_old_backups(max_age_days=30)
    assert tag not in deleted
