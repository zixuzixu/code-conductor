"""Phase 7c: End-to-end integration tests.

These tests exercise full request chains through the FastAPI app,
using mocks for LLM providers and Claude CLI subprocess calls.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from conductor.agents.llm_provider import ChatMessage, LLMProvider
from conductor.api.deps import get_memory_manager, get_queue_manager, get_session_manager
from conductor.core.constants import TaskStatus
from conductor.core.models import LLMProviderConfig
from server import app

# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """Deterministic LLM provider for testing — no real API calls."""

    def __init__(self, response: str = "Mock response from LLM."):
        config = LLMProviderConfig(provider="mock", model="mock-v1")
        super().__init__(config)
        self.response = response
        self.generate_calls: list[list[ChatMessage]] = []
        self.stream_calls: list[list[ChatMessage]] = []

    async def generate(self, messages: list[ChatMessage], **kwargs) -> str:
        self.generate_calls.append(messages)
        return self.response

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncIterator[str]:
        self.stream_calls.append(messages)
        for word in self.response.split():
            yield word + " "

    async def is_available(self) -> bool:
        return True


class FailingLLMProvider(LLMProvider):
    """LLM provider that always raises — used to test failover paths."""

    def __init__(self):
        config = LLMProviderConfig(provider="failing", model="fail-v1")
        super().__init__(config)

    async def generate(self, messages: list[ChatMessage], **kwargs) -> str:
        raise RuntimeError("Primary LLM exploded")

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncIterator[str]:
        raise RuntimeError("Primary LLM exploded")
        yield  # pragma: no cover — makes this a generator

    async def is_available(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fully isolated TestClient — sessions, queue, and memory all use tmp_path."""
    from conductor.managers.memory_manager import MemoryManager

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    # Isolate filesystem paths
    monkeypatch.setattr("conductor.core.constants.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("conductor.managers.session_manager.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("conductor.managers.queue_manager.SESSIONS_DIR", sessions_dir)

    # Isolate memory
    mem_path = tmp_path / "MEMORY.md"
    mem_factory = lambda: MemoryManager(memory_path=mem_path)  # noqa: E731
    monkeypatch.setattr("conductor.api.deps.get_memory_manager", mem_factory)
    monkeypatch.setattr("conductor.api.memory.get_memory_manager", mem_factory)

    # Clear all singleton caches
    get_session_manager.cache_clear()
    get_queue_manager.cache_clear()
    get_memory_manager.cache_clear()

    yield TestClient(app)

    get_session_manager.cache_clear()
    get_queue_manager.cache_clear()
    get_memory_manager.cache_clear()


@pytest.fixture()
def session_id(client):
    """Create a session and return its id string."""
    resp = client.post("/api/sessions", json={"name": "e2e-session", "repo_path": "/tmp/repo"})
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Scenario 1: Complete session lifecycle
# ---------------------------------------------------------------------------


def test_e2e_full_session_lifecycle_create_chat_task(client, session_id, monkeypatch):
    """Full lifecycle: create session -> send chat message (mock LLM) -> receive
    reply -> create task -> task enqueued -> verify consistent state."""
    mock_provider = MockLLMProvider(response="Here is my analysis.")

    # Patch _build_master_agent to use our mock
    def _mock_build():
        from conductor.agents.master_agent import MasterAgent

        return MasterAgent(primary=mock_provider)

    monkeypatch.setattr("conductor.api.chat._build_master_agent", _mock_build)

    # Send a chat message via SSE
    resp = client.post("/api/chat", json={"session_id": session_id, "message": "Analyze the codebase"})
    assert resp.status_code == 200
    body = resp.text
    assert "Here" in body
    assert "analysis." in body

    # Chat should have recorded conversation history
    session_resp = client.get(f"/api/sessions/{session_id}")
    session = session_resp.json()
    assert len(session["conversation_history"]) == 2
    assert session["conversation_history"][0]["role"] == "user"
    assert session["conversation_history"][1]["role"] == "assistant"

    # Create a task under the same session
    task_resp = client.post(
        "/api/threads/tasks",
        json={"session_id": session_id, "title": "Fix bug #1", "priority": "p0"},
    )
    assert task_resp.status_code == 201
    task = task_resp.json()
    assert task["status"] == "queued"

    # Verify task appears in the queue
    tasks = client.get(f"/api/threads/tasks/{session_id}").json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task["id"]


# ---------------------------------------------------------------------------
# Scenario 2: Multi-task priority scheduling
# ---------------------------------------------------------------------------


def test_e2e_multi_task_priority_dequeue_order(client, session_id):
    """Add tasks with P2, P0, P1 -> verify pop order is P0 -> P1 -> P2."""
    from conductor.api.deps import get_queue_manager

    priorities = [("Low task", "p2"), ("Critical task", "p0"), ("Normal task", "p1")]
    for title, prio in priorities:
        resp = client.post(
            "/api/threads/tasks",
            json={"session_id": session_id, "title": title, "priority": prio},
        )
        assert resp.status_code == 201

    # Pop tasks via QueueManager directly (no REST endpoint for pop)
    queue = get_queue_manager()
    sid = __import__("uuid").UUID(session_id)

    t1 = queue.pop(sid)
    t2 = queue.pop(sid)
    t3 = queue.pop(sid)

    assert t1 is not None and t1.priority.value == "p0"
    assert t2 is not None and t2.priority.value == "p1"
    assert t3 is not None and t3.priority.value == "p2"

    # Queue should now be empty of QUEUED tasks
    assert queue.pop(sid) is None


# ---------------------------------------------------------------------------
# Scenario 3: Worker execution simulation (mock WorkerRunner)
# ---------------------------------------------------------------------------


def test_e2e_worker_execution_mock_success(client, session_id):
    """Create task -> mock WorkerRunner returns success -> task status becomes completed."""
    from uuid import UUID

    from conductor.api.deps import get_queue_manager

    resp = client.post(
        "/api/threads/tasks",
        json={"session_id": session_id, "title": "Add login page", "priority": "p1"},
    )
    task_data = resp.json()

    queue = get_queue_manager()
    sid = UUID(session_id)

    # Pop the task (simulates dispatcher picking it up)
    popped = queue.pop(sid)
    assert popped is not None
    assert popped.status == TaskStatus.IN_PROGRESS

    # Simulate worker completing successfully
    popped.status = TaskStatus.COMPLETED
    queue.update_task(sid, popped)

    # Verify final state
    tasks = queue.get_all(sid)
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.COMPLETED
    assert tasks[0].id == UUID(task_data["id"])


# ---------------------------------------------------------------------------
# Scenario 4: Worker failure and recovery
# ---------------------------------------------------------------------------


def test_e2e_worker_failure_requeue_then_succeed(client, session_id):
    """Create task -> worker fails -> requeue -> second attempt succeeds."""
    from uuid import UUID

    from conductor.api.deps import get_queue_manager

    client.post(
        "/api/threads/tasks",
        json={"session_id": session_id, "title": "Flaky migration", "priority": "p1"},
    )

    queue = get_queue_manager()
    sid = UUID(session_id)

    # First attempt: pop and fail
    task = queue.pop(sid)
    assert task is not None
    task.status = TaskStatus.FAILED
    task.error_context = "Connection timeout to database"
    queue.update_task(sid, task)

    # Requeue the failed task
    queue.requeue(sid, task)
    requeued = queue.get_all(sid)
    assert requeued[0].status == TaskStatus.QUEUED
    assert requeued[0].retry_count == 1

    # Second attempt: pop and succeed
    task2 = queue.pop(sid)
    assert task2 is not None
    assert task2.retry_count == 1
    task2.status = TaskStatus.COMPLETED
    queue.update_task(sid, task2)

    final = queue.get_all(sid)
    assert final[0].status == TaskStatus.COMPLETED
    assert final[0].retry_count == 1


# ---------------------------------------------------------------------------
# Scenario 5: Concurrent session isolation
# ---------------------------------------------------------------------------


def test_e2e_concurrent_sessions_task_isolation(client):
    """Create sessions A and B, add tasks to each -> tasks must not leak across sessions."""
    from uuid import UUID

    from conductor.api.deps import get_queue_manager

    # Create two sessions
    resp_a = client.post("/api/sessions", json={"name": "session-alpha"})
    resp_b = client.post("/api/sessions", json={"name": "session-beta"})
    sid_a = resp_a.json()["id"]
    sid_b = resp_b.json()["id"]

    # Add tasks to each session
    client.post("/api/threads/tasks", json={"session_id": sid_a, "title": "Task A1", "priority": "p0"})
    client.post("/api/threads/tasks", json={"session_id": sid_a, "title": "Task A2", "priority": "p1"})
    client.post("/api/threads/tasks", json={"session_id": sid_b, "title": "Task B1", "priority": "p2"})

    # Verify isolation via API
    tasks_a = client.get(f"/api/threads/tasks/{sid_a}").json()
    tasks_b = client.get(f"/api/threads/tasks/{sid_b}").json()

    assert len(tasks_a) == 2
    assert len(tasks_b) == 1
    assert all("A" in t["title"] for t in tasks_a)
    assert tasks_b[0]["title"] == "Task B1"

    # Verify isolation via QueueManager pop
    queue = get_queue_manager()
    popped_a = queue.pop(UUID(sid_a))
    assert popped_a is not None
    assert popped_a.title == "Task A1"  # P0 first

    popped_b = queue.pop(UUID(sid_b))
    assert popped_b is not None
    assert popped_b.title == "Task B1"


# ---------------------------------------------------------------------------
# Scenario 6: Memory read/write integration
# ---------------------------------------------------------------------------


def test_e2e_memory_crud_via_api(client, session_id):
    """Write memory via API -> read back -> update key -> read again -> verify."""
    # Initially empty
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert resp.json()["content"] == ""

    # Write full content
    client.put("/api/memory", json={"content": "# Memory\n\n- **lang**: Python\n"})
    resp = client.get("/api/memory")
    assert "Python" in resp.json()["content"]

    # Update a key
    client.patch("/api/memory", json={"key": "framework", "value": "FastAPI"})
    resp = client.get("/api/memory")
    content = resp.json()["content"]
    assert "FastAPI" in content
    assert "Python" in content  # original key should still be there

    # Update existing key to new value
    client.patch("/api/memory", json={"key": "lang", "value": "Rust"})
    resp = client.get("/api/memory")
    content = resp.json()["content"]
    assert "Rust" in content
    assert "Python" not in content  # replaced

    # Framework key should survive
    assert "FastAPI" in content


# ---------------------------------------------------------------------------
# Scenario 7: Chat history persistence
# ---------------------------------------------------------------------------


def test_e2e_chat_history_persisted_across_messages(client, session_id, monkeypatch):
    """Send multiple chat messages -> session's conversation_history grows correctly."""
    call_count = 0

    class CountingMockProvider(MockLLMProvider):
        def __init__(self):
            super().__init__()

        async def stream(self, messages, **kwargs):
            nonlocal call_count
            call_count += 1
            reply = f"Reply number {call_count}."
            for word in reply.split():
                yield word + " "

    mock_provider = CountingMockProvider()

    def _mock_build():
        from conductor.agents.master_agent import MasterAgent

        return MasterAgent(primary=mock_provider)

    monkeypatch.setattr("conductor.api.chat._build_master_agent", _mock_build)

    # Send three messages
    for i in range(1, 4):
        resp = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": f"Question {i}"},
        )
        assert resp.status_code == 200

    # Retrieve session — should have 6 entries (3 user + 3 assistant)
    session = client.get(f"/api/sessions/{session_id}").json()
    history = session["conversation_history"]
    assert len(history) == 6

    # Verify alternating roles
    for idx in range(0, 6, 2):
        assert history[idx]["role"] == "user"
        assert history[idx + 1]["role"] == "assistant"

    # Verify content ordering
    assert "Question 1" in history[0]["content"]
    assert "Question 3" in history[4]["content"]


# ---------------------------------------------------------------------------
# Scenario 8 (bonus): Queue crash recovery
# ---------------------------------------------------------------------------


def test_e2e_crash_recovery_requeues_in_progress_tasks(client, session_id):
    """Tasks stuck in IN_PROGRESS after a 'crash' get recovered to QUEUED."""
    from uuid import UUID

    from conductor.api.deps import get_queue_manager

    queue = get_queue_manager()
    sid = UUID(session_id)

    # Create and pop a task (simulates it being picked up before crash)
    client.post(
        "/api/threads/tasks",
        json={"session_id": session_id, "title": "Crashed task", "priority": "p1"},
    )
    popped = queue.pop(sid)
    assert popped is not None
    assert popped.status == TaskStatus.IN_PROGRESS

    # Simulate crash recovery
    recovered = queue.recover_in_progress(sid)
    assert len(recovered) == 1
    assert recovered[0].status == TaskStatus.QUEUED
    assert "Recovered" in recovered[0].error_context

    # Task can now be popped again
    repicked = queue.pop(sid)
    assert repicked is not None
    assert repicked.title == "Crashed task"


# ---------------------------------------------------------------------------
# Scenario 9 (bonus): Session CRUD full cycle
# ---------------------------------------------------------------------------


def test_e2e_session_create_update_delete_cycle(client):
    """Full CRUD cycle: create -> update -> verify -> delete -> confirm gone."""
    # Create
    resp = client.post(
        "/api/sessions",
        json={"name": "lifecycle-test", "repo_path": "/tmp/repo", "max_workers": 2},
    )
    assert resp.status_code == 201
    sid = resp.json()["id"]
    assert resp.json()["max_workers"] == 2

    # Update
    resp = client.patch(f"/api/sessions/{sid}", json={"name": "renamed", "max_workers": 5})
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed"
    assert resp.json()["max_workers"] == 5

    # Verify via GET
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["name"] == "renamed"

    # Delete
    assert client.delete(f"/api/sessions/{sid}").status_code == 204

    # Confirm gone
    assert client.get(f"/api/sessions/{sid}").status_code == 404


# ---------------------------------------------------------------------------
# Scenario 10 (bonus): Chat with LLM failover
# ---------------------------------------------------------------------------


def test_e2e_chat_failover_primary_fails_fallback_succeeds(client, session_id, monkeypatch):
    """Primary LLM fails -> Master Agent fails over to fallback -> user gets a reply."""
    failing = FailingLLMProvider()
    fallback = MockLLMProvider(response="Fallback saved the day.")

    def _mock_build():
        from conductor.agents.master_agent import MasterAgent

        return MasterAgent(primary=failing, fallback=fallback)

    monkeypatch.setattr("conductor.api.chat._build_master_agent", _mock_build)

    resp = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "Help me"},
    )
    assert resp.status_code == 200
    assert "Fallback" in resp.text
    assert "saved" in resp.text

    # Conversation should still be persisted
    session = client.get(f"/api/sessions/{session_id}").json()
    assert len(session["conversation_history"]) == 2
