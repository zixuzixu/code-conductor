"""Tests for MemoryManager — MEMORY.md and PROGRESS.md operations."""

import pytest

from conductor.managers.memory_manager import MemoryManager


@pytest.fixture
def memory_mgr(tmp_path):
    memory_path = tmp_path / "MEMORY.md"
    memory_path.write_text("# Memory\n\n")
    return MemoryManager(memory_path=memory_path)


def test_read_memory(memory_mgr):
    content = memory_mgr.read_memory()
    assert "# Memory" in content


def test_write_memory(memory_mgr):
    memory_mgr.write_memory("# Memory\n\n- **name**: Alice\n")
    content = memory_mgr.read_memory()
    assert "Alice" in content


def test_update_memory_add_new(memory_mgr):
    memory_mgr.update_memory("theme", "dark mode")
    content = memory_mgr.read_memory()
    assert "- **theme**: dark mode" in content


def test_update_memory_overwrite_existing(memory_mgr):
    memory_mgr.update_memory("theme", "dark mode")
    memory_mgr.update_memory("theme", "light mode")
    content = memory_mgr.read_memory()
    assert "light mode" in content
    assert "dark mode" not in content


def test_read_nonexistent_memory(tmp_path):
    mgr = MemoryManager(memory_path=tmp_path / "nonexistent.md")
    assert mgr.read_memory() == ""


# --- PROGRESS.md ---


def test_read_progress(tmp_path):
    mgr = MemoryManager()
    progress = tmp_path / "PROGRESS.md"
    progress.write_text("# Progress\n\nSome entries\n")
    assert "Some entries" in mgr.read_progress(tmp_path)


def test_read_progress_nonexistent(tmp_path):
    mgr = MemoryManager()
    assert mgr.read_progress(tmp_path / "empty") == ""


async def test_append_progress(tmp_path):
    mgr = MemoryManager()
    await mgr.append_progress(
        tmp_path,
        task_title="Fix login bug",
        commit_id="abc1234",
        problem="Token expired too fast",
        solution="Extended token TTL to 24h",
        prevention="Add TTL to config, not hardcoded",
        key_files=["src/auth.py", "config.yaml"],
    )

    content = (tmp_path / "PROGRESS.md").read_text()
    assert "Fix login bug" in content
    assert "abc1234" in content
    assert "src/auth.py" in content
