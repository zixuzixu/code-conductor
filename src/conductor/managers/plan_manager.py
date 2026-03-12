"""Plan manager — CRUD for execution plans within sessions."""

import json
from pathlib import Path
from uuid import UUID

import structlog

from conductor.core.constants import PLANS_DIR
from conductor.core.models import Plan, PlanStep

logger = structlog.get_logger()


class PlanManager:
    """Manages plans stored as JSON files in the plans directory."""

    def __init__(self) -> None:
        self._plans_dir = PLANS_DIR
        self._plans_dir.mkdir(parents=True, exist_ok=True)

    def _plan_path(self, plan_id: UUID) -> Path:
        return self._plans_dir / f"{plan_id}.json"

    def create_plan(self, session_id: UUID, title: str, steps: list[dict]) -> Plan:
        """Create a new plan with the given steps."""
        plan_steps = [PlanStep(**s) for s in steps]
        plan = Plan(session_id=session_id, title=title, steps=plan_steps)
        self._save(plan)
        logger.info("plan.created", plan_id=str(plan.id), steps=len(plan_steps))
        return plan

    def get_plan(self, plan_id: UUID) -> Plan | None:
        path = self._plan_path(plan_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return Plan(**data)

    def list_plans(self, session_id: UUID) -> list[Plan]:
        plans = []
        for path in self._plans_dir.glob("*.json"):
            data = json.loads(path.read_text())
            plan = Plan(**data)
            if plan.session_id == session_id:
                plans.append(plan)
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    def update_plan(self, plan_id: UUID, updates: dict) -> Plan | None:
        """Update plan fields (steps, status, title)."""
        plan = self.get_plan(plan_id)
        if plan is None:
            return None

        if "title" in updates:
            plan.title = updates["title"]
        if "status" in updates:
            plan.status = updates["status"]
        if "steps" in updates:
            plan.steps = [PlanStep(**s) if isinstance(s, dict) else s for s in updates["steps"]]

        from datetime import datetime

        plan.updated_at = datetime.now()
        self._save(plan)
        return plan

    def delete_plan(self, plan_id: UUID) -> bool:
        path = self._plan_path(plan_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_enabled_steps(self, plan_id: UUID) -> list[PlanStep]:
        """Return only enabled steps for execution."""
        plan = self.get_plan(plan_id)
        if plan is None:
            return []
        return [s for s in plan.steps if s.enabled]

    def _save(self, plan: Plan) -> None:
        """Atomic write: write to temp file then rename."""
        path = self._plan_path(plan.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(plan.model_dump_json(indent=2))
        tmp.replace(path)
