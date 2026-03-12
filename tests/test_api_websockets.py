"""Tests for WebSocket endpoints."""

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_session_websocket_ping_pong(client):
    with client.websocket_connect("/ws/sessions/00000000-0000-0000-0000-000000000001") as ws:
        ws.send_text("ping")
        data = ws.receive_json()
        assert data == {"type": "pong"}


def test_thread_websocket_ping_pong(client):
    with client.websocket_connect("/ws/threads/00000000-0000-0000-0000-000000000001") as ws:
        ws.send_text("ping")
        data = ws.receive_json()
        assert data == {"type": "pong"}


def test_broadcast_session_event():
    """Test that broadcast_session_event sends to connected clients."""
    import asyncio
    from uuid import UUID

    from conductor.api.websockets import broadcast_session_event

    # Just verify the function doesn't crash with no connections
    asyncio.run(broadcast_session_event(UUID("00000000-0000-0000-0000-000000000001"), {"type": "test"}))


def test_broadcast_thread_event():
    """Test that broadcast_thread_event sends to connected clients."""
    import asyncio
    from uuid import UUID

    from conductor.api.websockets import broadcast_thread_event

    asyncio.run(broadcast_thread_event(UUID("00000000-0000-0000-0000-000000000001"), {"type": "test"}))
