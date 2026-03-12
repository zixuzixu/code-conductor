"""Tests for /api/threads endpoints (task queue management)."""

import pytest
from fastapi.testclient import TestClient

from conductor.api.deps import get_queue_manager, get_session_manager
from server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated storage."""
    monkeypatch.setattr("conductor.core.constants.SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr("conductor.managers.session_manager.SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr("conductor.managers.queue_manager.SESSIONS_DIR", tmp_path / "sessions")
    (tmp_path / "sessions").mkdir()

    get_session_manager.cache_clear()
    get_queue_manager.cache_clear()
    yield TestClient(app)
    get_session_manager.cache_clear()
    get_queue_manager.cache_clear()


@pytest.fixture
def session_id(client):
    resp = client.post("/api/sessions", json={"name": "test-session"})
    return resp.json()["id"]


def test_create_task(client, session_id):
    resp = client.post(
        "/api/threads/tasks",
        json={"session_id": session_id, "title": "Fix bug #42", "priority": "p0"},
    )
    assert resp.status_code == 201
    task = resp.json()
    assert task["title"] == "Fix bug #42"
    assert task["priority"] == "p0"
    assert task["status"] == "queued"


def test_list_tasks(client, session_id):
    client.post("/api/threads/tasks", json={"session_id": session_id, "title": "Task A", "priority": "p1"})
    client.post("/api/threads/tasks", json={"session_id": session_id, "title": "Task B", "priority": "p0"})

    resp = client.get(f"/api/threads/tasks/{session_id}")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 2
    # P0 should come first (sorted by priority)
    assert tasks[0]["priority"] == "p0"


def test_delete_task(client, session_id):
    resp = client.post("/api/threads/tasks", json={"session_id": session_id, "title": "To delete"})
    task_id = resp.json()["id"]

    assert client.delete(f"/api/threads/tasks/{session_id}/{task_id}").status_code == 204
    tasks = client.get(f"/api/threads/tasks/{session_id}").json()
    assert len(tasks) == 0


def test_create_task_invalid_session(client):
    resp = client.post(
        "/api/threads/tasks",
        json={"session_id": "00000000-0000-0000-0000-000000000000", "title": "orphan"},
    )
    assert resp.status_code == 404
