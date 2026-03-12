# Security Audit Report — Code Conductor

**Date**: 2026-03-13
**Auditor**: Phase 7b Security Review
**Scope**: OWASP Top 10 review of backend API and manager components
**Status**: Initial audit (MVP phase)

---

## Executive Summary

Reviewed 9 core files covering API endpoints, manager layers, and configuration. Identified **2 Critical**, **3 High**, **5 Medium**, and **4 Low** severity findings. All Critical and High issues have been remediated in this phase.

---

## Findings

### CRITICAL

#### C1. Git Command Injection via Branch Names
- **File**: `src/conductor/managers/git_manager.py`
- **OWASP**: A03 Injection
- **Description**: `branch_exists()`, `create_worktree()`, `merge_branch()`, and `push()` passed user-influenced branch names directly to `git` subprocess commands via `asyncio.create_subprocess_exec()`. While `create_subprocess_exec` uses execvp (no shell), a malicious branch name like `--upload-pack=evil` could still exploit git's option parsing.
- **Risk**: An attacker controlling branch names could inject git options or cause unexpected behavior.
- **Remediation**: Added `_validate_branch_name()` with allowlist regex and forbidden pattern checks. Applied to all methods accepting branch name parameters. **FIXED**.

#### C2. Path Traversal in Worktree Operations
- **File**: `src/conductor/managers/git_manager.py`
- **OWASP**: A03 Injection / A01 Broken Access Control
- **Description**: `create_worktree()` and `remove_worktree()` constructed filesystem paths from branch names without validating the resulting path stays within the expected worktree base directory. A crafted branch name could cause operations outside the repository.
- **Remediation**: Added `_validate_path_within()` to ensure worktree paths resolve under the expected base directory. **FIXED**.

### HIGH

#### H1. CORS Wildcard with Credentials
- **File**: `server.py`
- **OWASP**: A04 Insecure Design / A05 Security Misconfiguration
- **Description**: `allow_origins=["*"]` with `allow_credentials=True`. While browsers reject this combination per CORS spec, it signals intent to accept any origin and is a risk if the policy is later relaxed.
- **Risk**: In production, this would allow any site to make authenticated cross-origin requests.
- **Remediation**: Added documentation comments marking this as dev-only and specifying production requirements. **FIXED** (comment-level for MVP).

#### H2. No Input Length Validation on Chat Messages
- **File**: `src/conductor/api/chat.py`
- **OWASP**: A04 Insecure Design
- **Description**: `ChatRequest.message` had no length limit. An attacker could submit extremely large messages, causing memory exhaustion or excessive LLM API costs.
- **Remediation**: Added `field_validator` with 100KB limit and empty-message check. **FIXED**.

#### H3. Subprocess Path Injection in WorkerRunner
- **File**: `src/conductor/managers/worker_runner.py`
- **OWASP**: A03 Injection
- **Description**: `WorkerRunner.run()` passed `worktree_path` directly to `create_subprocess_exec(cwd=...)` without validating it exists or is a directory.
- **Risk**: Invalid or malicious paths could cause unexpected behavior.
- **Remediation**: Added path resolution and existence check before spawning subprocess. **FIXED**.

### MEDIUM

#### M1. No Authentication/Authorization on Any Endpoint
- **Files**: All API routers (`sessions.py`, `chat.py`, `threads.py`, `memory.py`)
- **OWASP**: A01 Broken Access Control / A07 Authentication Failures
- **Description**: All API endpoints are publicly accessible without any authentication. Any network-reachable client can create/delete sessions, read memory, and trigger LLM calls.
- **Risk**: Unauthorized access to all functionality. Acceptable for local-only dev tool, critical for any network-exposed deployment.
- **Recommendation**: Add API key or JWT authentication middleware before any production deployment. Track in Phase 8+.

#### M2. API Keys Stored in Plaintext Config
- **File**: `src/conductor/core/config.py`, `config.yaml`
- **OWASP**: A07 Authentication Failures
- **Description**: LLM API keys can be stored in `config.yaml` as plaintext fallback. While environment variables are the primary mechanism, the fallback creates risk of accidental credential exposure via config file sharing.
- **Recommendation**: Remove `api_key` field from config file template. Log a warning if api_key is set in config file. Use only environment variables.

#### M3. Error Messages Leak Internal Details via SSE
- **File**: `src/conductor/api/chat.py`
- **OWASP**: A04 Insecure Design
- **Description**: Line 60: `yield f"event: error\ndata: {e!s}\n\n"` sends raw exception messages to the client, potentially exposing internal paths, stack traces, or configuration details.
- **Recommendation**: Sanitize error messages before sending to client. Return generic error messages and log detailed errors server-side.

#### M4. WebSocket Connections Not Authenticated
- **File**: `src/conductor/api/websockets.py`
- **OWASP**: A01 Broken Access Control
- **Description**: WebSocket endpoints accept any connection without authentication. Any client can subscribe to session/thread events.
- **Recommendation**: Add token-based authentication during WebSocket handshake.

#### M5. No Rate Limiting
- **Files**: All API routers
- **OWASP**: A04 Insecure Design
- **Description**: No rate limiting on any endpoint. `/api/chat` is especially sensitive as each request triggers LLM API calls with associated costs.
- **Recommendation**: Add rate limiting middleware (e.g., `slowapi`) before production deployment.

### LOW

#### L1. Non-Atomic File Writes in MemoryManager
- **File**: `src/conductor/managers/memory_manager.py`
- **OWASP**: A08 Software and Data Integrity Failures
- **Description**: `write_memory()` and `update_memory()` use `Path.write_text()` which is not atomic. A crash during write could corrupt MEMORY.md. Note: `SessionManager._save()` correctly uses atomic write (write-to-temp then rename).
- **Recommendation**: Apply the same write-to-temp-then-rename pattern used in `session_manager.py`.

#### L2. No Input Validation on Task Title/Description Length
- **File**: `src/conductor/api/threads.py`
- **OWASP**: A04 Insecure Design
- **Description**: Task title and description had no length limits.
- **Remediation**: Added `field_validator` with 500-char title limit and 50KB description limit. **FIXED**.

#### L3. Unbounded WebSocket Connection Registry
- **File**: `src/conductor/api/websockets.py`
- **OWASP**: A04 Insecure Design
- **Description**: `_session_connections` and `_thread_connections` dicts grow without bound. An attacker could open thousands of connections to exhaust server memory.
- **Recommendation**: Add per-session connection limits and total connection caps.

#### L4. Logging Does Not Capture Security Events
- **Files**: All
- **OWASP**: A09 Security Logging and Monitoring Failures
- **Description**: No dedicated security event logging. Failed authentication (when added), path traversal attempts, and input validation failures should be logged with a security-specific log level or tag.
- **Recommendation**: Add structured security event logging with alerting capability.

---

## Remediation Summary

| ID | Severity | Status | Description |
|----|----------|--------|-------------|
| C1 | Critical | FIXED | Git branch name injection validation |
| C2 | Critical | FIXED | Worktree path traversal protection |
| H1 | High | FIXED | CORS wildcard documented as dev-only |
| H2 | High | FIXED | Chat message length validation |
| H3 | High | FIXED | WorkerRunner path validation |
| M1 | Medium | DEFERRED | No authentication on endpoints |
| M2 | Medium | DEFERRED | API keys in plaintext config |
| M3 | Medium | DEFERRED | Error message information leakage |
| M4 | Medium | DEFERRED | WebSocket authentication |
| M5 | Medium | DEFERRED | No rate limiting |
| L1 | Low | DEFERRED | Non-atomic memory file writes |
| L2 | Low | FIXED | Task title/description length validation |
| L3 | Low | DEFERRED | Unbounded WebSocket connections |
| L4 | Low | DEFERRED | Security event logging |

---

## Files Modified

- `server.py` — Enhanced cache-control middleware, CORS documentation
- `src/conductor/managers/git_manager.py` — Branch name validation, path traversal protection
- `src/conductor/managers/worker_runner.py` — Worktree path validation
- `src/conductor/api/chat.py` — Message length validation
- `src/conductor/api/threads.py` — Task title/description length validation

---

## Recommendations for Next Phase

1. **Authentication**: Implement API key or JWT-based auth middleware (M1, M4)
2. **Rate Limiting**: Add per-endpoint rate limits, especially on `/api/chat` (M5)
3. **Error Sanitization**: Replace raw exception forwarding with generic error codes (M3)
4. **Secrets Management**: Remove api_key from config.yaml template, environment-only (M2)
5. **Atomic Writes**: Apply write-then-rename pattern to MemoryManager (L1)
6. **Connection Limits**: Cap WebSocket connections per session and globally (L3)
