"""Tests for WorkerRunner and WorkerMonitor."""

import time

import pytest

from conductor.managers.worker_runner import WorkerEvent, WorkerMonitor, WorkerRunner

# --- WorkerMonitor ---


@pytest.fixture()
def monitor(tmp_path):
    return WorkerMonitor(worktree_path=tmp_path, thread_id="test-thread")


def test_monitor_process_thinking_event(monitor):
    """Monitor tracks events."""
    event = WorkerEvent(type="thinking", data={"content": "Analyzing..."})
    monitor.process_event(event)
    assert len(monitor.events) == 1
    assert not monitor.should_kill


def test_monitor_process_tool_use(monitor):
    """Tool use updates last_tool_use_time."""
    before = monitor.last_tool_use_time
    event = WorkerEvent(type="tool_use", data={"tool": "bash"})
    monitor.process_event(event)
    assert monitor.last_tool_use_time >= before


def test_monitor_file_write_tracked(monitor):
    """File writes are tracked."""
    event = WorkerEvent(type="file_write", data={"path": "src/main.py", "lines_added": 10})
    monitor.process_event(event)
    assert "src/main.py" in monitor.files_modified


def test_monitor_repeated_errors_trigger_kill(monitor):
    """3 identical errors trigger kill signal."""
    error_event = WorkerEvent(type="error", data={"message": "ImportError: no module named foo"})
    monitor.process_event(error_event)
    monitor.process_event(error_event)
    assert not monitor.should_kill

    monitor.process_event(error_event)
    assert monitor.should_kill
    assert "Repeated error" in monitor.kill_reason


def test_monitor_different_errors_no_kill(monitor):
    """Different error messages don't trigger kill."""
    for i in range(5):
        event = WorkerEvent(type="error", data={"message": f"Error {i}"})
        monitor.process_event(event)
    assert not monitor.should_kill


def test_monitor_no_output_timeout(monitor):
    """No output for too long triggers kill."""
    monitor.last_event_time = time.time() - 200  # 200s ago
    monitor.check_timeouts()
    assert monitor.should_kill
    assert "No output" in monitor.kill_reason


def test_monitor_no_timeout_when_recent(monitor):
    """Recent events don't trigger timeout."""
    monitor.last_event_time = time.time()
    monitor.check_timeouts()
    assert not monitor.should_kill


# --- WorkerRunner ---


def test_parse_ndjson_valid():
    """Parse valid NDJSON line."""
    line = '{"type": "thinking", "content": "Analyzing code..."}'
    event = WorkerRunner._parse_ndjson_line(line)
    assert event.type == "thinking"
    assert event.data["content"] == "Analyzing code..."


def test_parse_ndjson_invalid():
    """Invalid JSON becomes raw event."""
    event = WorkerRunner._parse_ndjson_line("not json at all")
    assert event.type == "raw"
    assert event.data["content"] == "not json at all"


def test_parse_ndjson_complete():
    """Parse complete event."""
    line = '{"type": "complete", "status": "success"}'
    event = WorkerRunner._parse_ndjson_line(line)
    assert event.type == "complete"
    assert event.data["status"] == "success"
