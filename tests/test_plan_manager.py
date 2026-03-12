"""Tests for PlanManager CRUD operations."""

from uuid import uuid4

import pytest

from conductor.core.models import Plan, PlanStep
from conductor.managers.plan_manager import PlanManager


@pytest.fixture
def plan_mgr(tmp_path, monkeypatch):
    monkeypatch.setattr("conductor.managers.plan_manager.PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr("conductor.core.constants.PLANS_DIR", tmp_path / "plans")
    return PlanManager()


class TestPlanManager:
    def test_create_plan(self, plan_mgr):
        sid = uuid4()
        plan = plan_mgr.create_plan(sid, "Test Plan", [
            {"description": "Step 1", "priority": "p0"},
            {"description": "Step 2"},
        ])
        assert plan.title == "Test Plan"
        assert plan.session_id == sid
        assert len(plan.steps) == 2
        assert plan.status == "draft"

    def test_get_plan(self, plan_mgr):
        sid = uuid4()
        created = plan_mgr.create_plan(sid, "My Plan", [{"description": "Do X"}])
        fetched = plan_mgr.get_plan(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.title == "My Plan"

    def test_get_nonexistent_plan(self, plan_mgr):
        assert plan_mgr.get_plan(uuid4()) is None

    def test_list_plans_filters_by_session(self, plan_mgr):
        s1, s2 = uuid4(), uuid4()
        plan_mgr.create_plan(s1, "Plan A", [])
        plan_mgr.create_plan(s2, "Plan B", [])
        plan_mgr.create_plan(s1, "Plan C", [])

        plans = plan_mgr.list_plans(s1)
        assert len(plans) == 2
        assert all(p.session_id == s1 for p in plans)

    def test_update_plan(self, plan_mgr):
        plan = plan_mgr.create_plan(uuid4(), "Draft", [{"description": "Step 1"}])
        updated = plan_mgr.update_plan(plan.id, {"title": "Approved Plan", "status": "approved"})
        assert updated is not None
        assert updated.title == "Approved Plan"
        assert updated.status == "approved"

    def test_update_nonexistent_plan(self, plan_mgr):
        assert plan_mgr.update_plan(uuid4(), {"title": "x"}) is None

    def test_delete_plan(self, plan_mgr):
        plan = plan_mgr.create_plan(uuid4(), "To Delete", [])
        assert plan_mgr.delete_plan(plan.id) is True
        assert plan_mgr.get_plan(plan.id) is None

    def test_delete_nonexistent(self, plan_mgr):
        assert plan_mgr.delete_plan(uuid4()) is False

    def test_get_enabled_steps(self, plan_mgr):
        plan = plan_mgr.create_plan(uuid4(), "Mixed", [
            {"description": "Enabled", "enabled": True},
            {"description": "Disabled", "enabled": False},
            {"description": "Also enabled"},
        ])
        enabled = plan_mgr.get_enabled_steps(plan.id)
        assert len(enabled) == 2
        assert all(s.enabled for s in enabled)

    def test_update_steps(self, plan_mgr):
        plan = plan_mgr.create_plan(uuid4(), "Steps", [{"description": "Old"}])
        updated = plan_mgr.update_plan(plan.id, {
            "steps": [
                {"description": "New Step 1", "priority": "p0"},
                {"description": "New Step 2", "priority": "p2", "enabled": False},
            ]
        })
        assert updated is not None
        assert len(updated.steps) == 2
        assert updated.steps[0].description == "New Step 1"
        assert updated.steps[1].enabled is False
