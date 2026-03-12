"""Tests for the Plan Mode API endpoints."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conductor.api.deps import get_plan_manager, get_queue_manager, get_session_manager
from server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated storage."""
    monkeypatch.setattr("conductor.core.constants.SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr("conductor.managers.session_manager.SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr("conductor.core.constants.PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr("conductor.managers.plan_manager.PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr("conductor.managers.queue_manager.SESSIONS_DIR", tmp_path / "sessions")
    (tmp_path / "sessions").mkdir()

    get_session_manager.cache_clear()
    get_queue_manager.cache_clear()
    get_plan_manager.cache_clear()
    yield TestClient(app, raise_server_exceptions=False)
    get_session_manager.cache_clear()
    get_queue_manager.cache_clear()
    get_plan_manager.cache_clear()


def _create_session(client):
    resp = client.post("/api/sessions", json={"name": "Test Session"})
    return resp.json()["id"]


class TestPlansAPI:
    def test_create_plan(self, client):
        sid = _create_session(client)
        resp = client.post("/api/plans", json={
            "session_id": sid,
            "title": "My Plan",
            "steps": [
                {"description": "Step 1", "priority": "p0"},
                {"description": "Step 2"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "My Plan"
        assert len(data["steps"]) == 2
        assert data["status"] == "draft"

    def test_create_plan_invalid_session(self, client):
        resp = client.post("/api/plans", json={
            "session_id": str(uuid4()),
            "title": "Bad Plan",
            "steps": [],
        })
        assert resp.status_code == 404

    def test_get_plan(self, client):
        sid = _create_session(client)
        create_resp = client.post("/api/plans", json={
            "session_id": sid,
            "title": "Fetch Me",
            "steps": [{"description": "Do something"}],
        })
        plan_id = create_resp.json()["id"]

        resp = client.get(f"/api/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Fetch Me"

    def test_get_nonexistent_plan(self, client):
        resp = client.get(f"/api/plans/{uuid4()}")
        assert resp.status_code == 404

    def test_list_plans_for_session(self, client):
        sid = _create_session(client)
        client.post("/api/plans", json={"session_id": sid, "title": "Plan A", "steps": []})
        client.post("/api/plans", json={"session_id": sid, "title": "Plan B", "steps": []})

        resp = client.get(f"/api/plans/session/{sid}")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_plan(self, client):
        sid = _create_session(client)
        create_resp = client.post("/api/plans", json={
            "session_id": sid, "title": "Old", "steps": [],
        })
        plan_id = create_resp.json()["id"]

        resp = client.patch(f"/api/plans/{plan_id}", json={"title": "Updated", "status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"
        assert resp.json()["status"] == "approved"

    def test_delete_plan(self, client):
        sid = _create_session(client)
        create_resp = client.post("/api/plans", json={
            "session_id": sid, "title": "Doomed", "steps": [],
        })
        plan_id = create_resp.json()["id"]

        resp = client.delete(f"/api/plans/{plan_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/plans/{plan_id}")
        assert resp.status_code == 404

    def test_execute_plan_creates_tasks(self, client):
        sid = _create_session(client)
        create_resp = client.post("/api/plans", json={
            "session_id": sid,
            "title": "Execute Me",
            "steps": [
                {"description": "Step 1", "priority": "p0"},
                {"description": "Step 2", "priority": "p1"},
                {"description": "Skipped", "enabled": False},
            ],
        })
        plan_id = create_resp.json()["id"]

        resp = client.post(f"/api/plans/{plan_id}/execute")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_created"] == 2

        plan = client.get(f"/api/plans/{plan_id}").json()
        assert plan["status"] == "executing"

    def test_execute_plan_no_enabled_steps(self, client):
        sid = _create_session(client)
        create_resp = client.post("/api/plans", json={
            "session_id": sid,
            "title": "Empty",
            "steps": [{"description": "Disabled", "enabled": False}],
        })
        plan_id = create_resp.json()["id"]

        resp = client.post(f"/api/plans/{plan_id}/execute")
        assert resp.status_code == 422

    def test_execute_already_executing_plan(self, client):
        sid = _create_session(client)
        create_resp = client.post("/api/plans", json={
            "session_id": sid, "title": "Running", "steps": [{"description": "Step"}],
        })
        plan_id = create_resp.json()["id"]

        client.post(f"/api/plans/{plan_id}/execute")
        resp = client.post(f"/api/plans/{plan_id}/execute")
        assert resp.status_code == 409
