"""Tests for /api/sessions endpoints."""

import pytest
from fastapi.testclient import TestClient

from conductor.api.deps import get_session_manager
from server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated session storage."""
    monkeypatch.setattr("conductor.core.constants.SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr("conductor.managers.session_manager.SESSIONS_DIR", tmp_path / "sessions")
    (tmp_path / "sessions").mkdir()

    # Clear cached deps
    get_session_manager.cache_clear()
    yield TestClient(app)
    get_session_manager.cache_clear()


def test_list_sessions_empty(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_get_session(client):
    resp = client.post("/api/sessions", json={"name": "test-project", "repo_path": "/tmp/repo"})
    assert resp.status_code == 201
    session = resp.json()
    assert session["name"] == "test-project"
    assert session["repo_path"] == "/tmp/repo"
    assert session["status"] == "active"

    # GET by id
    resp2 = client.get(f"/api/sessions/{session['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "test-project"


def test_list_sessions_after_create(client):
    client.post("/api/sessions", json={"name": "s1"})
    client.post("/api/sessions", json={"name": "s2"})
    resp = client.get("/api/sessions")
    assert len(resp.json()) == 2


def test_update_session(client):
    resp = client.post("/api/sessions", json={"name": "original"})
    sid = resp.json()["id"]

    resp2 = client.patch(f"/api/sessions/{sid}", json={"name": "renamed", "max_workers": 5})
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "renamed"
    assert resp2.json()["max_workers"] == 5


def test_delete_session(client):
    resp = client.post("/api/sessions", json={"name": "to-delete"})
    sid = resp.json()["id"]

    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_get_nonexistent_session(client):
    resp = client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_delete_nonexistent_session(client):
    resp = client.delete("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_scan_projects(client, tmp_path, monkeypatch):
    """Scan configured project dirs for git repos."""
    # Create a fake git repo
    repo = tmp_path / "projects" / "my-repo"
    (repo / ".git").mkdir(parents=True)

    # Mock config to include our temp dir
    from conductor.api.deps import get_config
    from conductor.core.models import ConductorConfig

    get_config.cache_clear()
    monkeypatch.setattr(
        "conductor.api.deps.load_config",
        lambda: ConductorConfig(project_dirs=[str(tmp_path / "projects")]),
    )

    resp = client.get("/api/sessions/projects")
    assert resp.status_code == 200
    repos = resp.json()
    assert len(repos) == 1
    assert repos[0]["name"] == "my-repo"

    get_config.cache_clear()
