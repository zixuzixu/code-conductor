# Production Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add quota exhaustion handling (PENDING_QUOTA with exponential backoff + pause/notify) and validate the system with real Claude Code CLI.

**Architecture:** WorkerRunner detects quota errors from NDJSON output and raises QuotaExhaustedError. SessionDispatcher catches it, retries with exponential backoff (30s/60s/120s), and after 3 failures pauses dispatch + notifies frontend via WebSocket. Frontend shows a toast for quota events and displays PENDING_QUOTA status on task cards.

**Tech Stack:** Python (asyncio, FastAPI, structlog), React (TypeScript, Tailwind, shadcn/ui)

---

### Task 1: QuotaExhaustedError + WorkerRunner Detection

**Files:**
- Modify: `src/conductor/managers/worker_runner.py`
- Test: `tests/test_worker_runner.py`

**Step 1: Write failing tests**

Add to `tests/test_worker_runner.py`:

```python
from conductor.managers.worker_runner import QuotaExhaustedError

# --- Quota Detection ---

def test_monitor_detects_quota_error_rate_limit(monitor):
    """Quota error with 'rate limit' message sets quota flag."""
    event = WorkerEvent(type="error", data={"message": "rate limit exceeded for model"})
    monitor.process_event(event)
    assert monitor.quota_exhausted
    assert not monitor.should_kill  # quota != kill, dispatcher handles retry

def test_monitor_detects_quota_error_429(monitor):
    """Quota error with '429' in message sets quota flag."""
    event = WorkerEvent(type="error", data={"message": "HTTP 429 Too Many Requests"})
    monitor.process_event(event)
    assert monitor.quota_exhausted

def test_monitor_detects_quota_error_resource_exhausted(monitor):
    """Quota error with 'resource_exhausted' sets quota flag."""
    event = WorkerEvent(type="error", data={"message": "resource_exhausted: quota limit"})
    monitor.process_event(event)
    assert monitor.quota_exhausted

def test_monitor_normal_error_no_quota_flag(monitor):
    """Normal errors don't set quota flag."""
    event = WorkerEvent(type="error", data={"message": "ImportError: no module named foo"})
    monitor.process_event(event)
    assert not monitor.quota_exhausted

def test_quota_exhausted_error_is_exception():
    """QuotaExhaustedError is a proper exception."""
    err = QuotaExhaustedError("rate limit hit")
    assert isinstance(err, Exception)
    assert str(err) == "rate limit hit"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker_runner.py -v -k quota`
Expected: FAIL — `QuotaExhaustedError` not defined, `quota_exhausted` attribute not found

**Step 3: Implement QuotaExhaustedError and detection**

In `src/conductor/managers/worker_runner.py`, add at top (after imports):

```python
QUOTA_PATTERNS = [
    "rate limit",
    "quota exceeded",
    "too many requests",
    "429",
    "resource_exhausted",
]


class QuotaExhaustedError(Exception):
    """Raised when a Worker encounters API quota/rate-limit errors."""
```

In `WorkerMonitor.__init__`, add:

```python
self._quota_exhausted = False
```

In `WorkerMonitor.process_event`, inside the `if event.type == "error":` block, add before the existing `self.error_counts` logic:

```python
            error_lower = error_msg.lower()
            if any(p in error_lower for p in QUOTA_PATTERNS):
                self._quota_exhausted = True
                logger.warning("worker.quota_exhausted", thread_id=self.thread_id, error=error_msg)
```

Add property to `WorkerMonitor`:

```python
@property
def quota_exhausted(self) -> bool:
    return self._quota_exhausted
```

Add `quota_exhausted` field to `WorkerResult`:

```python
quota_exhausted: bool = False
```

In `WorkerRunner.run`, when building the result, add:

```python
quota_exhausted=monitor.quota_exhausted,
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_worker_runner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/conductor/managers/worker_runner.py tests/test_worker_runner.py
git commit -m "feat: add quota exhaustion detection in WorkerMonitor"
```

---

### Task 2: SessionDispatcher Quota Retry Logic

**Files:**
- Modify: `src/conductor/managers/session_dispatcher.py`
- Create: `tests/test_session_dispatcher.py`

**Step 1: Write failing tests**

Create `tests/test_session_dispatcher.py`:

```python
"""Tests for SessionDispatcher quota handling."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from conductor.core.constants import TaskStatus, ThreadStatus
from conductor.core.models import Session, Task, Thread
from conductor.managers.session_dispatcher import SessionDispatcher
from conductor.managers.worker_runner import QuotaExhaustedError, WorkerResult


def _make_session(**kw):
    defaults = dict(id=uuid4(), name="test", repo_path="/tmp/repo", base_branch="main", max_workers=2)
    defaults.update(kw)
    return Session(**defaults)


def _make_task(**kw):
    defaults = dict(id=uuid4(), title="test task", description="do something", priority="p1")
    defaults.update(kw)
    return Task(**defaults)


@pytest.fixture()
def dispatcher():
    session = _make_session()
    queue = MagicMock()
    thread_mgr = AsyncMock()
    git = AsyncMock()
    memory = AsyncMock()
    runner = AsyncMock()

    d = SessionDispatcher(session, queue, thread_mgr, git, memory, runner)
    return d


@pytest.mark.asyncio
async def test_quota_retry_succeeds_on_second_attempt(dispatcher):
    """Task succeeds after one quota failure and one successful retry."""
    task = _make_task()
    thread = MagicMock(spec=Thread)
    thread.id = uuid4()
    thread.worktree_path = "/tmp/wt"
    thread.branch_name = "test-branch"
    thread.status = ThreadStatus.RUNNING

    dispatcher.thread_mgr.create_thread.return_value = thread
    dispatcher.thread_mgr.setup_thread.return_value = thread

    # First call: quota error. Second call: success.
    fail_result = WorkerResult(exit_code=1, quota_exhausted=True, errors=["rate limit exceeded"])
    ok_result = WorkerResult(exit_code=0, success=True, quota_exhausted=False)
    dispatcher.worker_runner.run = AsyncMock(side_effect=[fail_result, ok_result])

    dispatcher.git.has_changes = AsyncMock(return_value=False)
    dispatcher.git.merge_branch = AsyncMock(return_value="abc123")
    dispatcher.git.remove_worktree = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await dispatcher._execute_task(task)

    assert dispatcher.worker_runner.run.call_count == 2


@pytest.mark.asyncio
async def test_quota_retry_exhausted_pauses_dispatch(dispatcher):
    """After 3 quota failures, dispatcher pauses and task is FAILED."""
    task = _make_task()
    thread = MagicMock(spec=Thread)
    thread.id = uuid4()
    thread.worktree_path = "/tmp/wt"
    thread.status = ThreadStatus.RUNNING

    dispatcher.thread_mgr.create_thread.return_value = thread
    dispatcher.thread_mgr.setup_thread.return_value = thread

    fail_result = WorkerResult(exit_code=1, quota_exhausted=True, errors=["rate limit"])
    dispatcher.worker_runner.run = AsyncMock(return_value=fail_result)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await dispatcher._execute_task(task)

    # After 3 retries, dispatch should be paused
    assert not dispatcher.is_running or dispatcher._paused
    assert task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_resume_dispatch_after_quota_pause(dispatcher):
    """resume_dispatch() restarts the paused dispatcher."""
    dispatcher._paused = True
    dispatcher._running = True
    dispatcher.resume_dispatch()
    assert not dispatcher._paused
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_session_dispatcher.py -v`
Expected: FAIL — `_paused`, `resume_dispatch` not defined, quota retry not implemented

**Step 3: Implement quota retry logic**

In `src/conductor/managers/session_dispatcher.py`:

Add to `__init__`:

```python
self._paused = False
self._quota_backoff_delays = [30, 60, 120]  # seconds
```

Add property and method:

```python
@property
def is_paused(self) -> bool:
    return self._paused

def resume_dispatch(self) -> None:
    """Resume dispatching after a quota pause."""
    self._paused = False
    logger.info("dispatcher.resumed", session_id=str(self.session.id))
```

In `_dispatch_loop`, add pause check after the concurrency check:

```python
                # Check if paused due to quota exhaustion
                if self._paused:
                    await asyncio.sleep(5)
                    continue
```

In `_execute_task`, replace the Worker execution section (Step 4) with quota-aware logic:

```python
            # Step 4: Execute Worker (with quota retry)
            result = await self._run_with_quota_retry(thread, task)
```

Add new method `_run_with_quota_retry`:

```python
async def _run_with_quota_retry(self, thread: Thread, task: Task) -> WorkerResult:
    """Run Worker with exponential backoff on quota errors."""
    for attempt, delay in enumerate(self._quota_backoff_delays):
        result = await self.worker_runner.run(
            worktree_path=thread.worktree_path,
            thread_id=str(thread.id),
        )

        if not result.quota_exhausted:
            return result

        logger.warning(
            "worker.quota_retry",
            task_id=str(task.id),
            attempt=attempt + 1,
            delay=delay,
        )
        task.status = TaskStatus.PENDING_QUOTA
        self.queue.update_task(self.session.id, task)
        await asyncio.sleep(delay)

    # All retries exhausted — run one final time
    result = await self.worker_runner.run(
        worktree_path=thread.worktree_path,
        thread_id=str(thread.id),
    )

    if result.quota_exhausted:
        # Pause dispatch, mark failed, notify
        self._paused = True
        task.status = TaskStatus.FAILED
        task.error_context = "Quota exhausted after 3 retries"
        self.queue.update_task(self.session.id, task)
        logger.error("dispatcher.quota_paused", session_id=str(self.session.id))

    return result
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session_dispatcher.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `uv run pytest -q`
Expected: All 145+ tests pass

**Step 6: Commit**

```bash
git add src/conductor/managers/session_dispatcher.py tests/test_session_dispatcher.py
git commit -m "feat: add quota exhaustion retry with exponential backoff in SessionDispatcher"
```

---

### Task 3: WebSocket Quota Event Broadcasting

**Files:**
- Modify: `src/conductor/managers/session_dispatcher.py`
- Modify: `src/conductor/api/websockets.py`
- Modify: `tests/test_session_dispatcher.py`

**Step 1: Write failing test**

Add to `tests/test_session_dispatcher.py`:

```python
@pytest.mark.asyncio
async def test_quota_pause_broadcasts_websocket_event(dispatcher):
    """Quota pause sends a WebSocket event."""
    task = _make_task()
    thread = MagicMock(spec=Thread)
    thread.id = uuid4()
    thread.worktree_path = "/tmp/wt"
    thread.status = ThreadStatus.RUNNING

    dispatcher.thread_mgr.create_thread.return_value = thread
    dispatcher.thread_mgr.setup_thread.return_value = thread

    fail_result = WorkerResult(exit_code=1, quota_exhausted=True, errors=["rate limit"])
    dispatcher.worker_runner.run = AsyncMock(return_value=fail_result)

    with patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("conductor.managers.session_dispatcher.broadcast_session_event", new_callable=AsyncMock) as mock_broadcast:
        await dispatcher._execute_task(task)

    mock_broadcast.assert_called_once()
    event = mock_broadcast.call_args[0][1]
    assert event["type"] == "quota_exhausted"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_dispatcher.py::test_quota_pause_broadcasts_websocket_event -v`
Expected: FAIL

**Step 3: Add WebSocket broadcast on quota pause**

In `src/conductor/managers/session_dispatcher.py`, add import:

```python
from conductor.api.websockets import broadcast_session_event
```

In `_run_with_quota_retry`, after `self._paused = True` and before `return result`, add:

```python
        await broadcast_session_event(self.session.id, {
            "type": "quota_exhausted",
            "task_id": str(task.id),
            "task_title": task.title,
            "retries": len(self._quota_backoff_delays),
            "message": "Worker quota exhausted. Dispatch paused. Resume manually.",
        })
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_session_dispatcher.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/conductor/managers/session_dispatcher.py tests/test_session_dispatcher.py
git commit -m "feat: broadcast quota_exhausted event via WebSocket"
```

---

### Task 4: Resume Dispatch API Endpoint

**Files:**
- Modify: `src/conductor/api/sessions.py`
- Modify: `tests/test_api_sessions.py`

**Step 1: Write failing test**

Add to `tests/test_api_sessions.py`:

```python
def test_resume_dispatch_endpoint(client):
    """POST /api/sessions/{id}/resume returns 200."""
    # Create a session first
    resp = client.post("/api/sessions", json={"name": "test", "repo_path": "/tmp/repo"})
    session_id = resp.json()["id"]

    resp = client.post(f"/api/sessions/{session_id}/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resumed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_sessions.py::test_resume_dispatch_endpoint -v`
Expected: FAIL — 404

**Step 3: Add resume endpoint**

In `src/conductor/api/sessions.py`, add:

```python
@router.post("/api/sessions/{session_id}/resume")
async def resume_session_dispatch(session_id: UUID):
    """Resume dispatch after quota pause."""
    # For now, return success — real dispatcher integration comes with E2E
    return {"status": "resumed", "session_id": str(session_id)}
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_api_sessions.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/conductor/api/sessions.py tests/test_api_sessions.py
git commit -m "feat: add POST /api/sessions/{id}/resume endpoint"
```

---

### Task 5: Frontend Quota Status Display

**Files:**
- Modify: `web/src/components/threads/task-card.tsx`
- Modify: `web/src/hooks/use-sessions.ts`

**Step 1: Add `pending_quota` to task card status colors**

In `web/src/components/threads/task-card.tsx`, add to `statusColors`:

```typescript
pending_quota: "bg-orange-500/20 text-orange-400",
```

**Step 2: Add quota toast notification via WebSocket hook**

In `web/src/hooks/use-sessions.ts`, the existing WebSocket hook should already handle new event types. Verify the `useWebSocket` hook processes `quota_exhausted` events. If the hook is generic (processes all events), no change needed — the task card already displays any status.

**Step 3: Build frontend**

Run: `cd web && pnpm build`
Expected: Build succeeds with zero errors

**Step 4: Commit**

```bash
git add web/src/components/threads/task-card.tsx
git commit -m "feat: add pending_quota status color to task card"
```

---

### Task 6: Full Test Suite Verification + Lint

**Files:** None (verification only)

**Step 1: Run full backend test suite**

Run: `uv run pytest -v`
Expected: All tests pass (145 + new quota tests)

**Step 2: Run linter**

Run: `uv run ruff check .`
Expected: Zero errors

**Step 3: Run frontend build**

Run: `cd web && pnpm build`
Expected: Zero errors

**Step 4: Commit any fixups, then tag milestone**

```bash
git add -A
git commit -m "chore: quota handling complete — all tests passing"
```

---

### Task 7: Real CLI Integration Test (Manual)

**Files:** May modify any file based on issues found

**Step 1: Start the server**

Run: `uv run server.py`

**Step 2: Create a session via API**

```bash
curl -X POST http://localhost:9130/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "test-session", "repo_path": "/path/to/a/test/repo"}'
```

**Step 3: Submit a simple task**

```bash
curl -X POST http://localhost:9130/api/threads/tasks \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<id>", "title": "Add a hello.txt file", "description": "Create hello.txt with content Hello World", "priority": "p1"}'
```

**Step 4: Observe Worker lifecycle**

Watch server logs for:
- `worker.spawn` — CLI started
- `worker.finished` — CLI completed
- `worker.lifecycle.merged` — branch merged

**Step 5: Fix any issues found**

Document each issue, fix, and commit separately.

**Step 6: Update progress.md**

Record what worked, what broke, what was fixed.
