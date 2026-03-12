"""Tests for /api/memory endpoints."""

import pytest
from fastapi.testclient import TestClient

from conductor.api.deps import get_memory_manager
from server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated memory file."""
    from conductor.managers.memory_manager import MemoryManager

    mem_path = tmp_path / "MEMORY.md"
    factory = lambda: MemoryManager(memory_path=mem_path)  # noqa: E731

    get_memory_manager.cache_clear()
    # Patch both the deps module AND the memory route module (which holds its own import reference)
    monkeypatch.setattr("conductor.api.deps.get_memory_manager", factory)
    monkeypatch.setattr("conductor.api.memory.get_memory_manager", factory)
    yield TestClient(app)
    get_memory_manager.cache_clear()


def test_read_empty_memory(client):
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert resp.json()["content"] == ""


def test_write_and_read_memory(client):
    client.put("/api/memory", json={"content": "# Memory\n\n- **lang**: Python"})
    resp = client.get("/api/memory")
    assert "Python" in resp.json()["content"]


def test_update_memory_key(client):
    # First write some content
    client.put("/api/memory", json={"content": "# Memory\n"})

    # Update a key
    client.patch("/api/memory", json={"key": "framework", "value": "FastAPI"})
    resp = client.get("/api/memory")
    assert "FastAPI" in resp.json()["content"]

    # Update same key
    client.patch("/api/memory", json={"key": "framework", "value": "Django"})
    resp = client.get("/api/memory")
    assert "Django" in resp.json()["content"]
    # Old value should be replaced
    assert "FastAPI" not in resp.json()["content"]
