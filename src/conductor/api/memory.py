"""Memory management endpoints — MEMORY.md CRUD."""

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from conductor.api.deps import get_memory_manager

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = structlog.get_logger()


class MemoryUpdateRequest(BaseModel):
    key: str
    value: str


class MemoryWriteRequest(BaseModel):
    content: str


@router.get("")
async def read_memory():
    """Read the full MEMORY.md content."""
    mgr = get_memory_manager()
    return {"content": mgr.read_memory()}


@router.put("")
async def write_memory(req: MemoryWriteRequest):
    """Overwrite the full MEMORY.md content."""
    mgr = get_memory_manager()
    mgr.write_memory(req.content)
    return {"status": "ok"}


@router.patch("")
async def update_memory(req: MemoryUpdateRequest):
    """Add or update a key-value entry in MEMORY.md."""
    mgr = get_memory_manager()
    mgr.update_memory(req.key, req.value)
    return {"status": "ok"}
