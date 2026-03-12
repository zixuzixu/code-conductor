# Production Readiness: Quota Handling + Real CLI Integration

## Goal

让 Code Conductor 从 "全 mock 测试通过" 变成 "真正能跑" 的系统。

## Part 1: Quota 处理 (PENDING_QUOTA)

### 状态流转

```
RUNNING → (quota error detected) → PENDING_QUOTA
  → retry 1: wait 30s → RUNNING (or fail)
  → retry 2: wait 60s → RUNNING (or fail)
  → retry 3: wait 120s → RUNNING (or fail)
  → all retries exhausted → FAILED + pause session dispatch + notify frontend
```

### 变更清单

1. **`constants.py`** — TaskStatus 新增 `PENDING_QUOTA = "pending_quota"`
2. **`worker_runner.py`**
   - 新增 `QuotaExhaustedError(Exception)` 异常类
   - NDJSON 解析中检测 quota/rate-limit error patterns (HTTP 429, "rate limit", "quota exceeded")
   - 遇到 quota error 时 raise QuotaExhaustedError
3. **`session_dispatcher.py`**
   - `_execute_task()` 捕获 QuotaExhaustedError
   - 实现指数退避重试 (30s, 60s, 120s)，最多 3 次
   - 重试期间任务状态设为 PENDING_QUOTA
   - 3 次失败后：任务 FAILED，暂停 Session 调度，广播 WebSocket 事件
   - 新增 `resume_dispatch()` 方法供恢复调度
4. **`websockets.py`** — 广播 quota_exhausted 事件
5. **前端** — 收到 quota 事件显示 Toast 通知
6. **测试** — quota 检测、退避重试、暂停/恢复调度

### Quota Error 识别模式

```python
QUOTA_PATTERNS = [
    "rate limit",
    "quota exceeded",
    "too many requests",
    "429",
    "resource_exhausted",
]
```

## Part 2: 真实 CLI 集成验证

手动验证完整 Worker 9 步生命周期：

1. 启动 server (`uv run server.py`)
2. 通过 API 创建 Session (指定本地 git repo)
3. 提交简单任务
4. 观察 Worker 执行全流程
5. 修复所有发现的问题

这部分不预设具体变更，而是在真实运行中发现和修复。
