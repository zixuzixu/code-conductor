"""WebSocket endpoints for real-time event streaming."""

import asyncio
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websockets"])
logger = structlog.get_logger()

# --- Connection registries ---
# session_id -> set of connected WebSockets
_session_connections: dict[str, set[WebSocket]] = {}
# thread_id -> set of connected WebSockets
_thread_connections: dict[str, set[WebSocket]] = {}


async def broadcast_session_event(session_id: UUID, event: dict) -> None:
    """Broadcast an event to all WebSocket clients subscribed to a session.

    Called by SessionDispatcher when worker completes, status changes, etc.
    """
    key = str(session_id)
    conns = _session_connections.get(key, set())
    dead = []
    for ws in conns:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        conns.discard(ws)


async def broadcast_thread_event(thread_id: UUID, event: dict) -> None:
    """Broadcast an event to all WebSocket clients subscribed to a thread.

    Called by WorkerRunner to stream NDJSON output in real-time.
    """
    key = str(thread_id)
    conns = _thread_connections.get(key, set())
    dead = []
    for ws in conns:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        conns.discard(ws)


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: UUID):
    """Session-level WebSocket — receives worker completion summaries, status updates."""
    await websocket.accept()
    key = str(session_id)
    _session_connections.setdefault(key, set()).add(websocket)
    logger.info("ws.session.connected", session_id=key)

    try:
        while True:
            # Keep connection alive; client can send pings or commands
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        _session_connections.get(key, set()).discard(websocket)
        logger.info("ws.session.disconnected", session_id=key)


@router.websocket("/ws/threads/{thread_id}")
async def thread_websocket(websocket: WebSocket, thread_id: UUID):
    """Thread-level WebSocket — streams live Worker NDJSON output."""
    await websocket.accept()
    key = str(thread_id)
    _thread_connections.setdefault(key, set()).add(websocket)
    logger.info("ws.thread.connected", thread_id=key)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        _thread_connections.get(key, set()).discard(websocket)
        logger.info("ws.thread.disconnected", thread_id=key)
