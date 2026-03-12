# Findings & Decisions

## Requirements (from project.md)

### 核心架构
- **Master Agent**: API-based LLM (Gemini 3.1 Pro primary, Kimi k2.5 fallback) — 负责用户交互、任务分类、审查结果
- **Queue Manager**: 纯 Python 确定性逻辑 — push/pop/reorder、监控 Worker 槽位、生成 Worker
- **Worker Agent**: Claude Code CLI (`claude -p --dangerously-skip-permissions --output-format stream-json --verbose`) — 代码分析、实现、git 操作
- **LLMProvider 抽象层**: 方便切换/添加模型

### 技术栈
- Python 3.10+, FastAPI, asyncio
- React SPA (Vite + TypeScript), 构建到 `web/static/`
- JSON 状态存储, YAML 配置
- WebSocket/SSE 实时通信

### 数据模型
- Session → 项目/工作区，包含 task_queue.json 和多个 Thread
- Thread → 单个 Worker 任务，独立 Git 分支 + worktree + CLAUDE.md
- Task → P0/P1/P2 优先级，8 种状态流转

### 目录结构
- Home: `~/.code-conductor/` (config.yaml, MEMORY.md, sessions/)
- Worktree: `<repo_path>/worktree/` (不在 home 下)
- 代码仓库: `code-conductor/` (src/, web/, config/, server.py)

### Worker 9 步生命周期
1. Claim Task (原子 pop)
2. Create Worktree
3. Setup (symlink, port, CLAUDE.md)
4. Execute (Claude Code 隔离运行)
5. Commit
6. Merge + Test
7. Conflict Resolution (如需要)
8. Push
9. Cleanup (更新状态 → 清理 worktree → 记录 PROGRESS.md)

### API 端点
- `/api/sessions` — CRUD + projects 扫描
- `/api/chat` — SSE 流式 + Master 交互
- `/api/threads` — Thread 管理
- `/api/voice` — 语音转录 (Gemini)
- `/api/memory` — MEMORY.md 管理
- `/ws/sessions/{id}` — Session 事件
- `/ws/threads/{id}` — Worker 实时输出

## Research Findings
- 项目目前只有 project.md 和 .gitignore，零代码
- §12.1 的 "Completed" 列表是 MVP 目标功能，不是已完成的代码

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 前端 UI: Tailwind CSS + shadcn/ui | 轻量，定制性强，不引入重框架 |
| Python 包管理: uv | 快速，现代，替代 pip/poetry |
| 从 Phase 1 顺序推进 | 每个阶段依赖前一阶段的基础设施 |
| Ruff 替代 YAPF | lint+format 合一，和 uv 同一团队，配置进 pyproject.toml |
| PEP 8 4-space indent | Python 社区标准，2-space 是反模式 |
| 现代类型标注 `X \| None` | Python 3.10+ 原生支持 |
| structlog 结构化日志 | 与 Worker NDJSON 日志风格统一 |
| pytest + pytest-asyncio | 从 Phase 1 建立测试基础 |
| ABC 用于 LLMProvider | 运行时强制检查，Provider 数量有限不需要 Protocol 灵活性 |
| asyncio.create_subprocess_exec | 避免阻塞事件循环 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| async def 不含 yield 是 coroutine 不是 async generator | 需要在 raise 后加 unreachable yield 使其成为 async generator |

## Phase 8: Frontend UX Polish — 分析

### 8.1 日间模式配色现状
- 当前 `:root` (light mode) 使用的是 shadcn/ui 默认 neutral 配色 — 纯灰色系，无色彩倾向
- `@theme inline` 块里的颜色是暗色模式（oklch(0.145...) 是接近黑色），body 默认使用这些值
- 问题：`:root` 下定义了 light 变量，但 `@theme inline` 覆盖为暗色 → body 默认暗色
- light mode 的 `--background: oklch(1 0 0)` 是纯白，视觉上缺乏层次感

### 8.2 ChatInput 键盘行为现状
- 当前：`Ctrl+Enter` / `Cmd+Enter` 发送消息
- Textarea 默认行为：`Enter` 换行
- 需要反转：`Enter` 发送，`Shift+Enter` 或 `Ctrl+Enter` 换行

### 8.3 Session 创建流程现状
- 当前：点击 `+` → 出现输入框 → 手动输入名称 → Enter 确认
- 需要改为：点击 `+` → 自动生成名称 → 立即创建 session
- 自动名称格式方案：`Session YYYY-MM-DD HH:mm` 或使用 session 序号

## Resources
- project.md — 完整规格说明 (396 行)
- `.yapf` — 代码风格 (Google Style, 2-space indent)
