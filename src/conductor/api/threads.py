"""Thread and task management endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from conductor.api.deps import get_queue_manager, get_session_manager
from conductor.core.constants import Priority
from conductor.core.models import Task

router = APIRouter(prefix="/api/threads", tags=["threads"])
logger = structlog.get_logger()


class CreateTaskRequest(BaseModel):
    session_id: UUID
    title: str
    description: str = ""
    priority: Priority = Priority.P1

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title must not be empty")
        if len(v) > 500:
            raise ValueError("Title exceeds maximum length of 500 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if len(v) > 50_000:
            raise ValueError("Description exceeds maximum length of 50000 characters")
        return v


# --- Task queue endpoints ---


@router.post("/tasks", response_model=Task, status_code=201)
async def create_task(req: CreateTaskRequest):
    """Create a task and push it to the session's priority queue."""
    mgr = get_session_manager()
    session = mgr.get_session(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    task = Task(
        title=req.title,
        description=req.description,
        priority=req.priority,
    )
    queue = get_queue_manager()
    queue.push(req.session_id, task)
    return task


@router.get("/tasks/{session_id}", response_model=list[Task])
async def list_tasks(session_id: UUID):
    """List all tasks in a session's queue."""
    queue = get_queue_manager()
    return queue.get_all(session_id)


@router.delete("/tasks/{session_id}/{task_id}", status_code=204)
async def delete_task(session_id: UUID, task_id: UUID):
    """Remove a task from the queue."""
    queue = get_queue_manager()
    if not queue.remove_task(session_id, task_id):
        raise HTTPException(404, "Task not found")
