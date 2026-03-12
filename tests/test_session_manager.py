"""Tests for SessionManager — Session CRUD and persistence."""

import pytest

from conductor.managers.session_manager import SessionManager


@pytest.fixture
def session_mgr(tmp_path, monkeypatch):
    """SessionManager with a temporary sessions directory."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr("conductor.managers.session_manager.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("conductor.core.constants.SESSIONS_DIR", sessions_dir)
    return SessionManager()


def test_create_and_get_session(session_mgr):
    session = session_mgr.create_session(name="test-project", repo_path="/tmp/test-repo")
    assert session.name == "test-project"
    assert session.repo_path == "/tmp/test-repo"

    loaded = session_mgr.get_session(session.id)
    assert loaded is not None
    assert loaded.name == "test-project"
    assert loaded.id == session.id


def test_list_sessions(session_mgr):
    session_mgr.create_session(name="proj-a")
    session_mgr.create_session(name="proj-b")

    sessions = session_mgr.list_sessions()
    assert len(sessions) == 2
    names = {s.name for s in sessions}
    assert names == {"proj-a", "proj-b"}


def test_update_session(session_mgr):
    session = session_mgr.create_session(name="old-name")
    session.name = "new-name"
    session_mgr.update_session(session)

    loaded = session_mgr.get_session(session.id)
    assert loaded.name == "new-name"


def test_delete_session(session_mgr):
    session = session_mgr.create_session(name="to-delete")
    assert session_mgr.delete_session(session.id) is True
    assert session_mgr.get_session(session.id) is None
    assert session_mgr.delete_session(session.id) is False  # already deleted


def test_get_nonexistent_session(session_mgr):
    from uuid import uuid4

    assert session_mgr.get_session(uuid4()) is None


def test_scan_projects(session_mgr, tmp_path):
    # Create fake git repos
    for name in ["repo-a", "repo-b", "not-a-repo"]:
        d = tmp_path / "projects" / name
        d.mkdir(parents=True)
        if name != "not-a-repo":
            (d / ".git").mkdir()

    repos = session_mgr.scan_projects([str(tmp_path / "projects")])
    assert len(repos) == 2
    names = {r["name"] for r in repos}
    assert names == {"repo-a", "repo-b"}
