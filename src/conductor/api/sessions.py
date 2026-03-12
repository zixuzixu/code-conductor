"""Session CRUD and project scanning endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from conductor.api.deps import get_config, get_session_manager
from conductor.core.models import Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = structlog.get_logger()


# --- Request/Response schemas ---


class CreateSessionRequest(BaseModel):
    name: str
    repo_path: str | None = None
    repo_url: str | None = None
    base_branch: str = "main"
    max_workers: int = 3


class UpdateSessionRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    max_workers: int | None = None


# --- Routes ---


@router.get("", response_model=list[Session])
async def list_sessions():
    mgr = get_session_manager()
    return mgr.list_sessions()


@router.post("", response_model=Session, status_code=201)
async def create_session(req: CreateSessionRequest):
    mgr = get_session_manager()
    return mgr.create_session(
        name=req.name,
        repo_path=req.repo_path,
        repo_url=req.repo_url,
        base_branch=req.base_branch,
        max_workers=req.max_workers,
    )


@router.get("/projects")
async def scan_projects():
    """Scan configured project directories for git repositories."""
    config = get_config()
    mgr = get_session_manager()
    return mgr.scan_projects(config.project_dirs)


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: UUID):
    mgr = get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return session


@router.patch("/{session_id}", response_model=Session)
async def update_session(session_id: UUID, req: UpdateSessionRequest):
    mgr = get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if req.name is not None:
        session.name = req.name
    if req.status is not None:
        session.status = req.status
    if req.max_workers is not None:
        session.max_workers = req.max_workers
    return mgr.update_session(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: UUID):
    mgr = get_session_manager()
    if not mgr.delete_session(session_id):
        raise HTTPException(404, "Session not found")
