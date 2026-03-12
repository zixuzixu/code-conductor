# Code Conductor Project Specification

## 1. Project Overview & Objectives
**Code Conductor** is a Python-based system designed to coordinate and manage multiple **Claude Code** instances (Workers) to complete complex tasks. The primary interface is a responsive Web UI for desktop and mobile access.

### 1.1 Objectives
- **Agent Orchestration**: Enable an API-based **Master Agent** (Gemini 3.1 Pro, Kimi k2.5) to manage and coordinate **Claude Code** Worker instances.
- **Task Delegation**: Master delegates coding tasks to Workers; actual code analysis and implementation planning is performed by the Workers themselves.
- **Python-Native**: Built entirely in Python for extensibility and ease of integration with AI toolsets.

---

## 2. Technical Stack
- **Language**: Python 3.10+
- **Master Agent**: API-based LLM (Gemini 3.1 Pro primary, Kimi k2.5 fallback)
- **Worker Agent**: Claude Code (local CLI invocation, non-interactive mode)
- **Backend**: FastAPI, WebSockets/SSE for real-time streaming, asyncio for concurrency
- **Frontend**: React SPA built to static files, served by FastAPI
- **Logging**: structlog (structured logging, NDJSON-compatible)
- **Testing**: pytest + pytest-asyncio
- **Storage**: JSON for state/data, YAML for configuration

---

## 3. Directory Structure

### 3.1 Home Directory (`~/.code-conductor/` or `CODE_CONDUCTOR_HOME`)
All instance-specific data (configs, logs, sessions) is stored here.

```text
~/.code-conductor/
├── config.yaml          # API keys, settings, and project_dirs list
├── MEMORY.md            # Globally shared memory (user preferences, facts)
└── sessions/            # Session directories
    └── {session_uuid}/
        ├── metadata.json      # Session info (name, repo, branch)
        ├── task_queue.json    # Session's priority task queue
        ├── repo.git/          # Session-scoped bare git repository
        ├── data/              # Session-level JSON data
        └── threads/           # Thread directories
            └── {thread_uuid}/
                ├── metadata.json    # Thread info (task description, status)
                └── data/            # Thread-specific JSON data (logs, state)
```

**Worktrees** are stored in the repository root, not under `~/.code-conductor/`:

```text
<repo_path>/
├── .git/
├── worktree/                           # Overall worktree directory
│   ├── main/                           # Session's base branch worktree
│   ├── code-conductor/task-{ts}-{id}/      # Thread worktree (isolated branch)
│   └── code-conductor/conflict-{ts}-{id}/  # Conflict resolver worktree
└── src/
```

For sessions created with `repo_url` (no local path), worktrees fall back to `~/.code-conductor/sessions/{uuid}/worktree/`.

**Notes:**
- `logs/`: Stores application-level logs (server errors, HTTP access, Worker spawn/crash events). Individual Worker logs are in `threads/{uuid}/data/`.
- `repo.git/`: Bare git repository is session-scoped.
- `CLAUDE.md`: Written into each thread's worktree (so Claude Code finds it via cwd).
- `project_dirs`: Config option (`config.yaml`) listing workspace directories to scan for git projects. The `GET /api/sessions/projects` endpoint returns discovered projects for the UI project picker.

### 3.2 Repository Code Structure (Stateless)
```text
code-conductor/
├── src/
│   └── conductor/      # Python package (src layout, PyPA recommended)
│       ├── core/       # Models, config, constants
│       ├── api/        # FastAPI route handlers
│       ├── agents/     # LLM providers, Master Agent
│       └── managers/   # Session, Thread, Queue, Git, Memory managers
├── tests/              # pytest test suite
├── web/                # React frontend (src/ for dev, static/ for runtime)
├── config/             # Default templates and examples
├── pyproject.toml      # Project config (dependencies, ruff, pytest)
├── server.py           # Entry point
└── project.md          # This specification
```

---

## 4. Core Architecture

### 4.1 Agent Roles
| Role | Type | Responsibilities |
|------|------|------------------|
| **Master Agent** | API LLM (Gemini 3.1 Pro / Kimi k2.5) | User interaction, task classification (P0/P1/P2), high-level planning decisions, reviewing Worker results. Does NOT perform code analysis or queue operations. |
| **Queue Manager** | Python (Deterministic) | Hard-coded queue logic: push/pop/reorder tasks, monitor Worker slots, spawn Workers. Stateless, no LLM involvement. |
| **Worker Agent** | Claude Code CLI | Code analysis, implementation planning, file editing, git operations, testing. Runs in non-interactive mode (`claude -p --dangerously-skip-permissions`). |

**Model Abstraction**: The LLM client is wrapped in an abstract `LLMProvider` class, enabling easy addition of other models without modifying core logic.

### 4.2 Session & Thread Model
- **Session**: Represents a project/workspace. Each Session has:
  - One Git Worktree (associated with a specific repo/branch)
  - A priority task queue (`task_queue.json`)
  - Multiple Threads (concurrent Workers)
  
- **Thread**: Represents a single Worker task. Each Thread has:
  - Its own isolated Git branch (e.g., `code-conductor/task-{timestamp}-{id}`)
  - A dedicated worktree under `<repo_path>/worktree/<branch_name>/`
  - A `CLAUDE.md` file written into the worktree with task instructions

### 4.3 Git Isolation Strategy
- **Session Worktree**: Base working directory for the project
- **Thread Branch Isolation**: Each Worker operates on its own branch to prevent conflicts
- **Conflict Resolution**: When auto-merge fails, a dedicated **Conflict Resolution Worker** reads commit messages from both branches, analyzes the changes, and performs an intelligent merge

### 4.4 Symlink & Shared File Strategy
Thread worktrees use **symlinks** to share session-level files without duplication:

| File | Strategy | Reason |
|------|----------|--------|
| `task_queue.json` | Symlink | Shared task queue, atomic access via lock |
| `dev-task.lock` | Symlink | File lock for cross-worker coordination |
| `config.yaml` / API keys | Symlink | Single source of truth for credentials |
| `PROGRESS.md` | **No symlink** — use `git -C <main_repo>` to edit | Must live in main repo; symlink would cause Worker confusion about repo root |
| `CLAUDE.md` | **Copy per worktree** | Each Worker needs task-specific instructions |
| `node_modules/` | Symlink | Avoid redundant installs, save disk space |
| `data/` | **Isolated per worktree** | Each Worker may produce different experimental data |

**Rule**: Symlink only files that are read-shared or require cross-worker coordination. Files that Workers write to independently must be isolated.

---

## 5. Core Workflows

### 5.1 Ralph Loop (Continuous Task Consumption)
Code Conductor operates in a continuous loop where Workers automatically pull and execute tasks. The Worker prompt is minimal: **"干活；干完活退出 (exit)"** — all task context lives in `CLAUDE.md`.

1. **Task Queue** (`task_queue.json`): Three priority levels
   - **P0 (Immediate)**: Active conversation — execute immediately
   - **P1 (Standard)**: Features/bugs — consume when slots available
   - **P2 (Background)**: Refactoring/docs — batch during idle time

2. **Task Ingestion** (Master Agent - LLM):
   - User submits request via chat
   - Master Agent classifies priority (P0/P1/P2) and generates task description
   - Python Queue Manager receives the classified task and pushes to queue

3. **Worker Task Lifecycle** (Queue Manager - Python, 9 atomic steps):

   ```
   ┌─────────────────────────────────────────────────────────┐
   │  1. Claim Task      Atomic pop from task_queue.json     │
   │  2. Create Worktree  git worktree add -b task/xxx       │
   │  3. Setup            mkdir data/, symlink shared files,  │
   │                      allocate port, write CLAUDE.md      │
   │  4. Execute          Claude Code runs in isolated env    │
   │  5. Commit           git commit on task branch           │
   │  6. Merge + Test     git fetch origin && git merge main  │
   │                      → run tests (npm test / pytest)     │
   │  7. Conflict?        If merge fails → resolve (§9.3)    │
   │                      If tests fail → retry up to 3x     │
   │                      then escalate to Step 6 again       │
   │  8. Push             git merge main task-xxx &&          │
   │                      git push origin main                │
   │  9. Cleanup          Update task status in queue,        │
   │                      git worktree remove, delete branch, │
   │                      log lessons to PROGRESS.md          │
   └─────────────────────────────────────────────────────────┘
   ```

   **Critical**: Step 9 must update `task_queue.json` status BEFORE cleanup. If process is killed mid-cleanup, task state is already persisted and won't be re-executed.

4. **Verification & Acceptance Loop** (Master Agent - LLM):
   - When Worker finishes, Master Agent **reviews results against original task requirements**
   - Review criteria: code correctness, test pass, no regressions, task objectives met
   - **Accept**: Master summarizes to user, marks task complete
   - **Reject**: Master creates follow-up fix task (P0) with specific feedback, re-enters queue
   - **Partial**: Master accepts completed parts, creates new tasks for remaining work
   - This closes the feedback loop — without verification, the system produces output but has no quality signal

5. **Survivability**: On restart, Queue Manager reloads queue state and resumes from where it left off. Tasks in `IN_PROGRESS` state are re-queued with their original priority.

### 5.2 Plan Mode (Two-Phase Execution)
For complex tasks, Code Conductor uses a planning phase:

**Phase 1: Planning** (Master Agent decides, Queue Manager executes)
- Master Agent determines task requires planning phase
- Queue Manager creates "Plan Thread" with `--plan-mode` flag
- Worker analyzes and outputs detailed execution plan (no file modifications)
- Plan displayed in Web UI as editable checklist

**Phase 2: Execution** (User approves, Queue Manager schedules)
- User reviews, edits, or approves the plan
- Upon approval, Master Agent classifies plan steps as P0/P1
- Queue Manager pushes approved steps into task queue
- Execution Workers run approved steps (popped by Queue Manager)
- Multiple plans can execute in parallel across different Threads

---

## 6. Memory & Knowledge Management

### 6.1 Global Knowledge Files (Concurrency Guarded)
All files use synchronization locks to prevent race conditions:

| File | Purpose | Access Pattern |
|------|---------|----------------|
| **MEMORY.md** | User preferences ("dark mode"), facts ("works at Citadel"), personalization | Read at session start; updated when preferences/facts revealed |
| **PROGRESS.md** | Lessons learned, debugging history, cross-worker knowledge | Appended after each task completion; read by new Workers at start |

### 6.2 PROGRESS.md — Lessons Learned System
Each Worker is instructed (via `CLAUDE.md`) to append to `PROGRESS.md` after completing a task. This prevents the same mistakes from recurring across Workers and sessions.

**Required format per entry:**
```markdown
## [YYYY-MM-DD HH:MM] Task: <task_title>
- **Commit**: <git_commit_id>
- **Problem**: What went wrong or was challenging
- **Solution**: How it was resolved
- **Prevention**: How to avoid this in the future
- **Key Files**: Which files were touched and why
```

**Rules:**
- Workers MUST write to `PROGRESS.md` via `git -C <main_repo_path>` (not via symlink — see §4.4)
- Same problem must NOT appear twice — Workers check existing entries before writing
- Master Agent periodically distills `PROGRESS.md` into actionable rules and promotes them to `CLAUDE.md` templates
- `PROGRESS.md` is NOT suitable for frequently changing state (use `task_queue.json` for that)

### 6.3 Context Management Strategies
- **Master Layer**: Conversation summarization (compress early history, keep last ~10 turns); hierarchical context (System > Session Summary > Recent Dialogue > Retrieved snippets)
- **Worker Layer**: Task decomposition; file scoping via `CLAUDE.md` (explicitly limit focus to relevant modules)
- **Cross-Worker Knowledge**: Workers read `PROGRESS.md` at start to inherit lessons from previous Workers — this is the primary mechanism for long-term AI memory across sessions

---

## 7. User Interface

### 7.1 Web UI Layout
- **Sessions (Sidebar)**: Multi-channel organization (like Slack). Each session = separate project/context.
- **Chat Interface**: Main area for Master Agent interaction (ChatGPT-like).
- **Threads (Sub-Agents)**: Nested under sessions. Each thread = Claude Code Worker task. Users can drill down to view status/logs.

### 7.2 Mobile PWA Support
The Web UI is designed as a **Progressive Web App (PWA)** for mobile-first access:
- **Manifest**: `manifest.json` with `display: standalone`, app icon, theme color
- **Service Worker**: Cache shell assets for offline access to UI (task queue remains online-only)
- **iOS**: Users add to Home Screen via Safari → behaves like native app (no browser chrome)
- **Responsive**: All panels (Sessions, Chat, Threads) stack vertically on mobile; swipe to switch

**Design rationale** (from field experience): SSH on mobile is painful — tiny terminal, constant refreshing, can't multitask. A web interface accessed via phone means vibe coding is possible 24/7, not just when sitting at a laptop. This alone can extend productive AI-coding hours from ~8h to ~24h/day.

### 7.3 Voice Input (Push-to-Talk)
**Workflow**:
1. User presses/clicks button to start recording
2. Presses/clicks again to stop and send
3. Audio uploaded to backend
4. **Gemini 3.1 Pro** transcribes (supports Chinese, English, mixed)
5. Transcription displayed in UI first
6. Passed to Master with disclaimer: *"This is a voice-transcribed message and may not be exactly accurate. Please ask clarifying questions if anything is unclear."*

---

## 8. Communication & Monitoring

### 8.1 Real-Time Streaming
- **WebSockets or SSE**: Stream PTY output directly from Worker to frontend
- **HTTP GET**: Used for loading historical logs (non-real-time)
- **Persistence**: Worker state is flushed to disk in real-time; Master can resume after restart

### 8.2 JSON Stream Monitoring (Manager Intelligence Layer)
Workers run with `--output-format stream-json --verbose`. The Manager parses structured NDJSON logs to achieve **closed-loop observability**:

```json
{"type": "thinking", "content": "Analyzing..."}
{"type": "file_write", "path": "src/auth.py", "lines_added": 45}
{"type": "tool_use", "tool": "bash", "command": "npm test"}
{"type": "error", "message": "ImportError..."}
{"type": "complete", "status": "success"}
```

**Manager monitoring behaviors:**

| Signal | Detection | Action |
|--------|-----------|--------|
| Long `thinking` with no tool use | >60s of thinking events only | Log warning; if >180s, consider stuck |
| Repeated identical errors | Same error message 3+ times | Kill Worker, re-queue with error context |
| No output at all | No events for >120s | Health check; restart if process dead |
| `file_write` to unexpected paths | Path outside worktree | Alert user, potential safety issue |
| `complete` with `status: error` | Worker self-reported failure | Master reviews error, creates fix task |
| Test failure after merge | Test command returns non-zero | Retry merge or escalate to conflict resolution |

**Key insight**: The difference between a 20% and 95% task success rate lies in the Manager's ability to read structured Worker output, diagnose failures, and autonomously create corrective tasks. Without this monitoring layer, the Manager is blind to what Workers are actually doing.

---

## 9. Error Handling & Resilience

### 9.1 Model Fallback
- Primary: **Gemini 3.1 Pro**
- Fallback: **Kimi k2.5** (automatic switch on API failure, transparent to user)

### 9.2 Quota Exhaustion Handling
- Worker enters **PENDING_QUOTA** state on quota error
- Queue Manager (Python) periodically polls for quota recovery
- Task auto-resumes when quota available; Master Agent notified to inform user
- All context persisted to disk during wait

### 9.3 Merge Conflict Resolution
When auto-merge fails:
1. Spawn **Conflict Resolution Worker** in a dedicated worktree (`code-conductor/conflict-{ts}-{id}`)
2. Worker reads commit messages from both branches to understand intent
3. Analyzes conflicted files and surrounding context
4. Decides: keep one side, merge both, or rewrite
5. Creates resolution commit with explanation
6. Runs full test suite to verify resolution
7. If resolution fails tests, retry from step 3 (max 3 attempts), then escalate to user

**Rebase failure recovery** (from `PROGRESS.md` pattern):
1. If "unstaged changes" error → `git stash` current changes first
2. If merge conflicts → `git status` to list conflicted files → read both sides → resolve → `git add` → `git rebase --continue`
3. **Never give up on rebase** — must resolve the issue before proceeding, cannot skip

### 9.4 Auto-Backup Strategy
- **State backup**: `task_queue.json` and session metadata are backed up every hour to `~/.code-conductor/backups/{timestamp}/`
- **Git safety**: All Worker code is committed to branches before merge — even if process is killed, work is recoverable via `git reflog`
- **Backup retention**: Keep last 24 hourly backups + last 7 daily backups; prune older ones
- **Database** (if applicable): For any persistent data stores, schedule hourly `pg_dump` or equivalent — never trust that "it won't crash"

---

## 10. Design Philosophy — "Context, not Control"

The core principle of Code Conductor is **servant leadership for AI**: provide context and environment, not micromanagement.

### 10.1 What This Means in Practice

| Instead of... | Do this... |
|---------------|------------|
| Reviewing every line of AI-generated code | Write better `CLAUDE.md` instructions and test suites |
| Telling the Worker HOW to implement | Describe WHAT the task requires and WHY it matters |
| Manually triggering each step | Let the Ralph Loop consume tasks autonomously |
| Debugging Worker failures yourself | Let Master Agent diagnose via JSON stream and create fix tasks |
| Writing detailed implementation plans | Use Plan Mode — let the Worker propose, you review |

### 10.2 Implications for System Design
- **CLAUDE.md is the product**: The quality of Worker output is directly proportional to the quality of its instructions. Invest time in writing clear, scoped `CLAUDE.md` templates.
- **Tests are the acceptance criteria**: If you can't write a test for it, the Worker can't verify it either. Prefer testable task definitions.
- **First-principles scope**: Ask "what is the speed of light here?" — what's the theoretical maximum throughput? Design toward that, remove bottlenecks.
- **Closed-loop over open-loop**: Every Worker output must be verified (by tests, by Master review, or by user acceptance). Output without feedback is waste.
- **Compound improvement**: `PROGRESS.md` entries compound over time — each lesson learned makes ALL future Workers smarter. This is the system's long-term competitive advantage.

---

## 11. Development Guidelines

### 11.1 Code Style
- **Standard**: PEP 8 (4-space indent, 120 column limit)
- **Tooling**: Ruff (linting + formatting), configured in `pyproject.toml`:
  ```toml
  [tool.ruff]
  line-length = 120
  target-version = "py310"

  [tool.ruff.lint]
  select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]

  [tool.ruff.format]
  quote-style = "double"
  indent-style = "space"
  ```
- **Type hints**: Modern syntax — `str | None` (not `Optional[str]`), `list[str]` (not `List[str]`)

### 11.2 Worker Instructions (CLAUDE.md)
Each Thread's `CLAUDE.md` contains:
1. Default shared instructions from `~/.code-conductor/SUBAGENT_PROMPT.md` (coding standards, YOLO mode, git conventions)
2. Specific task description and objectives
3. Session-specific context/constraints

---

## 12. Implementation Status

### 12.1 MVP Target (To Be Implemented)

**Backend**
- FastAPI server (`server.py`)
- All API routes: `/api/sessions`, `/api/chat`, `/api/threads`, `/api/voice`, `/api/memory`
- `MasterAgent` with Gemini (primary) + Kimi (fallback) LLM providers, streaming, conversation summarization
- `QueueManager` — priority queue (P0 > P1 > P2) with atomic JSON persistence via `os.replace`
- `SessionDispatcher` — per-session background queue loop that pops tasks, creates threads, and spawns Claude Code workers (`claude -p --dangerously-skip-permissions --output-format stream-json --verbose`)
- Worker completion handling: dispatcher reads worker's NDJSON event log, asks Master Agent to review and summarize, appends summary to session conversation history, broadcasts via session WebSocket
- `SessionManager`, `ThreadManager`, `MemoryManager`, `GitManager`
- `init_conductor_home()` — seeds `~/.code-conductor/` on first run with default `config.yaml`
- Memory updates: Master Agent can include `memory_update` field in any response to persist user preferences/facts to `MEMORY.md`

**WebSocket Endpoints**
- `/ws/sessions/{session_id}` — session-level events (worker completion summaries pushed to chat)
- `/ws/threads/{thread_id}` — thread-level events (live Worker NDJSON output streaming)

**Frontend**
- React SPA (Vite + TypeScript) built to `web/static/`, served by FastAPI StaticFiles (Node.js/npm is build-time only)
- Panels: Sessions sidebar, Chat (SSE streaming), Threads list, Plan review checklist, Voice push-to-talk
- ChatPanel subscribes to session WebSocket — receives worker summaries and renders them as assistant messages
- ThreadsPanel polls every 3 seconds for thread status updates
- No-cache middleware on HTML to prevent stale JS bundles
- Draft persistence: unsent message text is saved to localStorage per session (debounced 300ms) and restored on session switch-back or page reload

**Configuration**
- `~/.code-conductor/config.yaml` is the single source of truth for API keys and settings — no environment variables
- Active models: `gemini-3.1-pro-preview` (primary), `kimi-k2.5` (fallback)

### 12.2 Pending / Not Yet Implemented

