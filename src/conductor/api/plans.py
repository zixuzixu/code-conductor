"""Plan Mode API — CRUD for execution plans."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from conductor.api.deps import get_plan_manager, get_queue_manager, get_session_manager
from conductor.core.constants import Priority
from conductor.core.models import Task

router = APIRouter(prefix="/api/plans", tags=["plans"])
logger = structlog.get_logger()


class PlanStepInput(BaseModel):
    description: str
    priority: str = "p1"
    enabled: bool = True


class CreatePlanRequest(BaseModel):
    session_id: UUID
    title: str
    steps: list[PlanStepInput] = Field(default_factory=list)


class UpdatePlanRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    steps: list[dict] | None = None


@router.post("")
async def create_plan(req: CreatePlanRequest):
    """Create a new execution plan for a session."""
    mgr = get_session_manager()
    if mgr.get_session(req.session_id) is None:
        raise HTTPException(404, "Session not found")

    plan_mgr = get_plan_manager()
    steps = [s.model_dump() for s in req.steps]
    plan = plan_mgr.create_plan(req.session_id, req.title, steps)
    return plan.model_dump(mode="json")


@router.get("/{plan_id}")
async def get_plan(plan_id: UUID):
    """Get a plan by ID."""
    plan = get_plan_manager().get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return plan.model_dump(mode="json")


@router.get("/session/{session_id}")
async def list_plans(session_id: UUID):
    """List all plans for a session."""
    return [p.model_dump(mode="json") for p in get_plan_manager().list_plans(session_id)]


@router.patch("/{plan_id}")
async def update_plan(plan_id: UUID, req: UpdatePlanRequest):
    """Update plan (edit steps, change status, rename)."""
    updates = req.model_dump(exclude_none=True)
    plan = get_plan_manager().update_plan(plan_id, updates)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return plan.model_dump(mode="json")


@router.post("/{plan_id}/execute")
async def execute_plan(plan_id: UUID):
    """Convert enabled plan steps to tasks in the queue.

    Sets plan status to 'executing' and creates one task per enabled step.
    """
    plan_mgr = get_plan_manager()
    plan = plan_mgr.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")

    if plan.status not in ("draft", "approved"):
        raise HTTPException(409, f"Plan is already {plan.status}")

    steps = plan_mgr.get_enabled_steps(plan_id)
    if not steps:
        raise HTTPException(422, "No enabled steps to execute")

    queue = get_queue_manager()
    created_tasks = []
    for step in steps:
        priority_map = {"p0": Priority.P0, "p1": Priority.P1, "p2": Priority.P2}
        priority = priority_map.get(step.priority.value if hasattr(step.priority, "value") else str(step.priority), Priority.P1)
        task = Task(
            title=step.description[:120],
            description=step.description,
            priority=priority,
        )
        queue.push(str(plan.session_id), task)
        created_tasks.append(task.model_dump(mode="json"))

    plan_mgr.update_plan(plan_id, {"status": "executing"})
    logger.info("plan.executing", plan_id=str(plan_id), tasks_created=len(created_tasks))
    return {"plan_id": str(plan_id), "tasks_created": len(created_tasks), "tasks": created_tasks}


@router.delete("/{plan_id}")
async def delete_plan(plan_id: UUID):
    """Delete a plan."""
    if not get_plan_manager().delete_plan(plan_id):
        raise HTTPException(404, "Plan not found")
    return {"deleted": True}
