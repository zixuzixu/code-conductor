# Task Plan: Code Conductor — Full Implementation

## Goal
根据 project.md 规格说明，从零实现 Code Conductor：一个基于 Python 的多 Claude Code Worker 编排系统，包含 FastAPI 后端、React 前端、实时 WebSocket 通信和完整的任务生命周期管理。

## Current Phase
Complete (Phase 1-8 all done)

## Phases

### Phase 1: Project Scaffolding & Core Models
- [x] 1.1 `uv init` + pyproject.toml (依赖: fastapi, uvicorn[standard], pyyaml, httpx, filelock, structlog; dev: pytest, pytest-asyncio, ruff)
- [x] 1.2 创建 src/conductor/ 包结构 (core/, api/, agents/, managers/) + tests/
- [x] 1.3 src/conductor/core/constants.py — 路径常量、状态枚举 (SessionStatus, ThreadStatus, TaskStatus, Priority)
- [x] 1.4 src/conductor/core/models.py — Pydantic v2 数据模型 (Session, Thread, Task, ConductorConfig)，类型标注用 `X | None` 现代语法
- [x] 1.5 src/conductor/core/config.py — init_conductor_home(), load_config(), save_config(), 默认 config.yaml 模板
- [x] 1.6 pyproject.toml 内配置 Ruff (PEP 8, 4-space, 120 col) + pytest + hatchling build-system
- [x] 1.7 server.py — FastAPI 入口 (/api/health, CORS, no-cache 中间件, 静态文件挂载, structlog + lifespan)
- [x] 1.8 验证: pytest 通过，`/api/health` 返回 200, `ruff check .` 零错误
- **Status:** complete

### Phase 2: Git & Session/Thread Management
- [x] 2.1 `GitManager` (src/conductor/managers/git_manager.py)
  - [x] 2.1a `create_worktree(branch_name)` — `git worktree add -b`
  - [x] 2.1b `remove_worktree(worktree_path)` — `git worktree remove` + 删除分支
  - [x] 2.1c `merge_branch(source_branch, target_branch)` — checkout + merge + restore
  - [x] 2.1d `get_current_branch()` / `branch_exists()` / `list_worktrees()` / `has_changes()`
  - [x] 2.1e 异步封装 (`asyncio.create_subprocess_exec` via `_run_git()`)
  - [x] 2.1f `commit_in_worktree()` / `fetch_origin()` / `push()`
- [x] 2.2 `SessionManager` (src/conductor/managers/session_manager.py)
  - [x] 2.2a `create_session()` → 创建 session 目录 + metadata.json (原子写入)
  - [x] 2.2b `get_session(id)` / `list_sessions()` / `delete_session(id)`
  - [x] 2.2c `update_session()` — 更新会话元数据
  - [x] 2.2d `scan_projects(dirs)` — 扫描项目目录，返回 git repo 列表
- [x] 2.3 `ThreadManager` (src/conductor/managers/thread_manager.py)
  - [x] 2.3a `create_thread(session, task)` → GitManager 创建 worktree + 分支
  - [x] 2.3b `setup_thread(thread)` → symlink 共享文件 + 写 CLAUDE.md
  - [x] 2.3c `cleanup_thread(thread)` → 更新状态 → 清理 symlink → 删除 worktree
  - [x] 2.3d 状态流转 (PENDING → SETTING_UP → RUNNING → COMPLETED/FAILED)
- [x] 2.4 `MemoryManager` (src/conductor/managers/memory_manager.py)
  - [x] 2.4a `read_memory()` / `update_memory(key, value)` — MEMORY.md 读写 + filelock
  - [x] 2.4b `append_progress(entry)` — PROGRESS.md 追加（直接写入 main repo）
  - [x] 2.4c `read_progress()` — 读取 PROGRESS.md
- [x] 2.5 Symlink 策略 (src/conductor/managers/symlink_strategy.py)
  - [x] 2.5a `setup_worktree_links(worktree_path, repo_path)` — §4.4 规则
  - [x] 2.5b `cleanup_worktree_links(worktree_path)` — 删除 symlink 防止误删共享文件
- [x] 2.6 测试: 26 tests passed (6 git + 6 session + 9 memory + 5 thread)
- **Status:** complete

### Phase 3: LLM Providers & Master Agent (MVP)
- [x] `LLMProvider` 抽象基类 (ABC, generate/stream/is_available)
- [x] `GeminiProvider` — google-genai SDK, 环境变量 GEMINI_API_KEY 优先
- [x] `KimiProvider` — openai SDK (OpenAI-compatible), 环境变量 KIMI_API_KEY 优先
- [x] 自动故障转移 (Primary → Fallback, MasterAgent.chat 内自动切换)
- [x] `MasterAgent` MVP — 接收消息 → 调用 LLM → 返回流式回复 + failover
- [x] project.md 更新: API keys 改用环境变量
- [x] 测试: 45 tests passed (26 existing + 19 new), ruff check clean
- **Status:** complete

### Phase 3b: Master Agent 完整版
- [x] 任务分类 (P0/P1/P2) — classify_task() LLM-based 任务提取和优先级分类
- [x] 对话摘要 — summarize_conversation() 压缩历史消息 >10 条，保留最近 6 轮
- [x] Memory update 机制 — extract_memory_updates() 从 LLM 回复提取 [MEMORY_UPDATE] 标签
- [x] Worker 结果审查 — review_worker_result() LLM-based accept/reject/partial 判定
- **Status:** complete

### Phase 4: Queue Manager & Worker Lifecycle
- [x] `QueueManager` — 优先级队列 (P0>P1>P2)、原子 JSON 持久化 (`os.replace`)、文件锁
- [x] `WorkerRunner` — 启动 Claude Code CLI、解析 NDJSON 输出、WorkerResult 聚合
- [x] `WorkerMonitor` — 6 类信号检测 (思考超时、重复错误、无输出、路径逃逸、错误状态、测试失败)
- [x] `SessionDispatcher` — 每个 Session 的后台消费循环、并发 Worker 上限控制
- [x] Worker 9 步生命周期实现 (Claim → Worktree → Setup → Execute → Commit → Merge → Conflict? → Push → Cleanup)
- [x] CLAUDE.md 模板系统 (Phase 2 ThreadManager 已实现)
- [x] NDJSON 日志解析 & Manager 监控层
- [x] 崩溃恢复：QueueManager.recover_in_progress() 重启后 IN_PROGRESS 任务重新入队
- [x] Worker 完成处理：Master 审查 → Accept/Reject/Partial (Phase 3b 已实现)
- [x] Quota 耗尽处理 PENDING_QUOTA (WorkerMonitor 检测 + SessionDispatcher 重试 + WebSocket 广播 + Resume API + 前端指示器)
- [x] 测试: 64 tests passed (45 existing + 10 queue + 9 worker), ruff check clean
- **Status:** complete

### Phase 5: API Routes & WebSockets
- [x] REST API: `/api/sessions` CRUD (GET/POST/PATCH/DELETE)
- [x] REST API: `/api/chat` (SSE 流式, conversation persistence)
- [x] REST API: `/api/threads/tasks` 任务队列管理 (POST/GET/DELETE)
- [ ] REST API: `/api/voice` 语音转录 (移至 Phase 7)
- [x] REST API: `/api/memory` 记忆管理 (GET/PUT/PATCH)
- [x] REST API: `/api/sessions/projects` 项目扫描
- [x] WebSocket: `/ws/sessions/{session_id}` — Session 级事件 + broadcast helper
- [x] WebSocket: `/ws/threads/{thread_id}` — Worker NDJSON 实时流 + broadcast helper
- [ ] Plan Mode API (移至 Phase 7)
- [x] 依赖注入: `api/deps.py` 单例 Manager 工厂
- [x] 测试: 83 tests passed (64 existing + 19 new), ruff check clean
- **Status:** complete

### Phase 6: React Frontend (MVP)
- [x] Vite + TypeScript + React 项目初始化
- [x] Tailwind CSS v4 + shadcn/ui (dark theme, zinc preset)
- [x] API 客户端库 (sessions, chat SSE, tasks)
- [x] React Hooks (useSessions, useChat, useTasks, useWebSocket)
- [x] Sessions 侧边栏 (Linear 风格, 新建/删除/选择)
- [x] Chat 面板 (SSE 流式, 自动滚动, Ctrl+Enter 发送)
- [x] Threads 面板 (优先级色标, 状态轮询 3s, 任务 CRUD)
- [x] 三栏布局集成 (App.tsx, session 切换, WebSocket 连接)
- [x] 草稿持久化 (localStorage per session)
- [x] 构建到 `web/static/`，FastAPI 静态服务
- [ ] Plan 审查清单 UI (移至 Phase 7)
- [ ] Voice 按住说话组件 (移至 Phase 7)
- [ ] PWA 支持 (移至 Phase 7)
- [ ] 响应式设计 (移至 Phase 7)
- **Status:** complete

### Phase 7: Integration, Error Handling & Polish
- [x] 合并冲突解决 Worker (§9.3) — ConflictResolver: dry-run merge 检测, ours/theirs/smart 自动解决
- [x] 自动备份策略 (§9.4) — BackupManager: git tag-based backup/restore/cleanup, 微秒精度
- [x] No-cache 中间件防止旧 JS bundle — 3-tier Cache-Control (HTML no-cache, hashed assets immutable, API no-cache)
- [x] 端到端测试 — 10 E2E 集成场景 (session lifecycle, priority scheduling, worker simulation, failover, crash recovery)
- [x] PROGRESS.md 经验沉淀系统验证
- [x] 安全审查 — 修复 5 个 Critical/High 问题 (branch name injection, path traversal, input length limits), docs/security-audit.md
- [ ] REST API: `/api/voice` 语音转录 (deferred, nice-to-have)
- [ ] Plan Mode API (deferred, nice-to-have)
- [ ] Plan 审查清单 UI (deferred, nice-to-have)
- [ ] Voice 按住说话组件 (deferred, nice-to-have)
- [ ] PWA 支持 (deferred, nice-to-have)
- [ ] 响应式设计 (deferred, nice-to-have)
- [x] Quota 耗尽处理 PENDING_QUOTA (完成: 检测 + 重试 + 广播 + Resume API + 前端)
- **Status:** complete

## Key Questions
1. Gemini 3.1 Pro API 使用什么 SDK？ → google-genai 或直接 HTTP
2. Kimi k2.5 API 端点和认证方式？ → OpenAI 兼容格式
3. Claude Code CLI 的 `--output-format stream-json` 输出的具体 NDJSON 格式？ → 需要实际测试
4. React 用什么 UI 库？ → 规格未指定，需决定
5. 文件锁策略？ → fcntl / filelock / 自定义
6. WebSocket 用 fastapi-websocket 原生还是 socket.io？ → 原生

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 前端: Tailwind CSS + shadcn/ui | 轻量，定制性强 |
| Python 包管理: uv | 快速现代，替代 pip/poetry |
| 顺序推进 Phase 1→7 | 各阶段存在依赖关系 |
| Python >=3.10 | 匹配本地 3.10.12 |
| 包结构: src/conductor/ (src layout) | PyPA 推荐，短包名，优雅导入 |
| server.py 放根目录 | 符合规格，`uv run server.py` 简洁 |
| Ruff 替代 YAPF | 同一团队(Astral)出品，lint+format 合一，10-100x 更快 |
| 4-space indent (PEP 8) | Python 社区标准，2-space 是 Google 内部特例 |
| 类型标注: `X \| None` 现代语法 | Python 3.10+ 原生支持，更简洁 |
| structlog 结构化日志 | 与 Worker NDJSON 风格统一 |
| pytest + pytest-asyncio | 现代 Python 测试标准 |
| LLMProvider 用 ABC | 需要运行时强制检查，Provider 数量有限 |
| 异步子进程 asyncio.create_subprocess_exec | 避免阻塞事件循环 |
| API keys: 环境变量优先 | 安全标准做法，config.yaml 作为 fallback |
| Gemini SDK: google-genai | 官方新 SDK，简洁 API |
| Kimi SDK: openai | OpenAI 兼容格式，官方 SDK 最稳定 |
| Phase 3 先做 MVP | 最小可用路径优先，完整版 (3b) 后续补充 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `on_event("startup")` DeprecationWarning | 1 | 改用 lifespan context manager |
| `ModuleNotFoundError: conductor` | 1 | 添加 hatchling build-system + `[tool.hatch.build.targets.wheel]` |
| RUF001 全角分号误报 | 1 | `# noqa: RUF001`，中文 prompt 有意为之 |

### Phase 8: Frontend UX Polish
- [x] 8.1 日间模式配色更新 — 重新设计 `:root` 下的 CSS 变量，使用蓝色调高对比度 light mode 配色 (oklch blue tint)
- [x] 8.2 Enter 发送消息 / Shift+Enter 换行 — 修改 ChatInput 键盘事件逻辑，反转默认行为
- [x] 8.3 Session 自动命名 — 点击 `+` 自动生成 `Session YYYY-MM-DD HH:mm` 名称，一键创建
- **Status:** complete

## Notes
- project.md §12.1 描述的 "Completed (MVP)" 是目标功能列表，不是已实现的代码
- 优先级：先跑通最小可用路径（发消息 → Master 回复 → 创建任务 → Worker 执行），再补充功能
- 代码风格：PEP 8, 4-space indent, 120 column limit (Ruff)
- 所有配置在 `~/.code-conductor/config.yaml`，不用环境变量
