# Code Conductor

Multi-Claude Code Worker 编排系统。通过 API-based Master Agent 协调多个 Claude Code 实例并行执行编码任务。

## 架构

```
用户 ──► Web UI ──► FastAPI ──► Master Agent (Gemini/Kimi)
                                     │
                                     ▼
                               Queue Manager
                              ┌──────┼──────┐
                              ▼      ▼      ▼
                           Worker  Worker  Worker
                         (Claude Code CLI, 独立 worktree)
```

- **Master Agent** — API-based LLM (Gemini 3.1 Pro primary, Kimi k2.5 fallback)，负责用户交互、任务分类 (P0/P1/P2)、Worker 结果审查
- **Queue Manager** — 优先级任务队列，原子持久化，崩溃恢复
- **Worker** — Claude Code CLI 在隔离 git worktree 中执行，NDJSON 实时监控
- **Web UI** — React + Tailwind + shadcn/ui 三栏布局，SSE 流式 + WebSocket 实时更新

## 快速开始

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Node.js 18+ (前端开发)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (Worker 运行时)

### 安装

```bash
git clone <repo-url> && cd code-conductor
uv sync
```

### 配置

设置 LLM API keys（至少一个）：

```bash
export GEMINI_API_KEY="your-key"
export KIMI_API_KEY="your-key"
```

或编辑 `~/.code-conductor/config.yaml`（首次启动自动生成）。

#### 端口配置

默认端口为 `9130`，可通过以下方式修改（优先级从高到低）：

1. 环境变量：`export CONDUCTOR_PORT=9200`
2. 配置文件：`~/.code-conductor/config.yaml` 中的 `server_port` 字段

前后端共用同一配置，改一处即可。

### 运行

```bash
uv run server.py
# → http://localhost:9130
```

### 前端开发

```bash
cd web
pnpm install
pnpm dev
# → http://localhost:5173 (proxy → 9130)
```

构建生产版本：

```bash
pnpm build  # 输出到 web/static/，FastAPI 自动服务
```

## 项目结构

```
src/conductor/
├── core/          # 数据模型、配置、常量
├── api/           # FastAPI 路由 (sessions, chat, threads, memory, websockets)
├── agents/        # LLM Provider 抽象 + Master Agent
└── managers/      # Session, Thread, Queue, Git, Memory, Worker, Conflict, Backup
web/               # React 前端 (Vite + TypeScript + Tailwind + shadcn/ui)
tests/             # 145 tests (pytest + pytest-asyncio)
server.py          # FastAPI 入口
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/sessions` | GET/POST/PATCH/DELETE | Session CRUD |
| `/api/sessions/projects` | GET | 扫描本地 Git 项目 |
| `/api/chat` | POST | SSE 流式对话 |
| `/api/threads/tasks` | GET/POST/DELETE | 任务队列管理 |
| `/api/memory` | GET/PUT/PATCH | 全局记忆管理 |
| `/ws/sessions/{id}` | WS | Session 级实时事件 |
| `/ws/threads/{id}` | WS | Worker NDJSON 实时流 |

## Worker 生命周期

1. **Claim** — 从优先级队列原子弹出任务
2. **Worktree** — 创建隔离 git worktree + 分支
3. **Setup** — Symlink 共享文件 + 写入 CLAUDE.md
4. **Execute** — Claude Code CLI 在 worktree 中运行
5. **Commit** — 提交变更
6. **Merge** — 合并到目标分支 + 运行测试
7. **Conflict** — 自动冲突解决（如需要）
8. **Push** — 推送到远程
9. **Cleanup** — 清理 worktree，记录进度

## 测试

```bash
uv run pytest           # 运行全部 145 tests
uv run pytest -x -q     # 快速模式，遇错即停
uv run ruff check .     # Lint 检查
```

## 技术决策

- **src layout** — PyPA 推荐的包结构
- **Ruff** — lint + format 合一，替代 YAPF + flake8
- **ABC for LLMProvider** — 运行时强制接口约束
- **asyncio.create_subprocess_exec** — 非阻塞 Worker 进程管理
- **filelock** — 多进程安全的状态文件访问
- **原子写入** (tmp + os.replace) — 防止状态文件损坏

## License

MIT
