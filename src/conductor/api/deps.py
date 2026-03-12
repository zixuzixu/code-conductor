"""Shared dependencies — singleton manager instances for FastAPI DI."""

from functools import lru_cache

from conductor.core.config import load_config
from conductor.core.models import ConductorConfig
from conductor.managers.memory_manager import MemoryManager
from conductor.managers.queue_manager import QueueManager
from conductor.managers.session_manager import SessionManager


@lru_cache
def get_config() -> ConductorConfig:
    return load_config()


@lru_cache
def get_session_manager() -> SessionManager:
    return SessionManager()


@lru_cache
def get_queue_manager() -> QueueManager:
    return QueueManager()


@lru_cache
def get_memory_manager() -> MemoryManager:
    return MemoryManager()


# Registry of active dispatchers — keyed by str(session_id)
_dispatchers: dict[str, object] = {}


def get_dispatchers() -> dict[str, object]:
    """Return the global dispatcher registry."""
    return _dispatchers
