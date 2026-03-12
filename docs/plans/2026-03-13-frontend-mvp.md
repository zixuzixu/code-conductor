# Frontend MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a three-panel React frontend (Sessions sidebar + Chat SSE + Threads panel) that connects to the existing FastAPI backend.

**Architecture:** Vite + React + TypeScript SPA with Tailwind CSS + shadcn/ui. Dark theme, Linear-style aesthetic. Dev proxy to FastAPI :8000, prod builds to `web/static/`. No state management library — useState + props drilling. Custom fetch hooks for API calls.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui, pnpm

---

### Task 1: Vite Project Scaffold

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.app.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/globals.css`

**Step 1: Initialize Vite project**

```bash
cd /home/zixu/codes/code-conductor
pnpm create vite@latest web --template react-ts
```

Accept defaults. This creates the scaffold.

**Step 2: Install dependencies**

```bash
cd web
pnpm install
```

**Step 3: Configure Vite proxy + build output**

Replace `web/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
  build: {
    outDir: "../web/static",
    emptyOutDir: true,
  },
});
```

**Step 4: Verify dev server starts**

```bash
cd web && pnpm dev
```

Expected: Vite dev server on http://localhost:5173, shows default React page.

**Step 5: Commit**

```bash
git add web/
git commit -m "feat(web): scaffold Vite + React + TypeScript project"
```

---

### Task 2: Tailwind CSS + shadcn/ui Setup

**Files:**
- Modify: `web/package.json` (add deps)
- Create: `web/postcss.config.js`
- Create: `web/tailwind.config.ts`
- Modify: `web/src/globals.css`
- Create: `web/components.json`
- Create: `web/src/lib/utils.ts`

**Step 1: Install Tailwind + shadcn/ui deps**

```bash
cd web
pnpm add tailwindcss @tailwindcss/vite
pnpm add class-variance-authority clsx tailwind-merge lucide-react
```

**Step 2: Configure Tailwind in vite.config.ts**

Add `@tailwindcss/vite` plugin to Vite config.

**Step 3: Setup globals.css with Tailwind + dark theme CSS variables**

Replace `web/src/globals.css` with Tailwind imports + shadcn/ui CSS variables (dark theme defaults from shadcn zinc preset).

**Step 4: Create utils.ts**

```typescript
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

**Step 5: Initialize shadcn/ui**

```bash
cd web && pnpm dlx shadcn@latest init
```

Select: New York style, Zinc color, CSS variables: yes.

**Step 6: Add required components**

```bash
pnpm dlx shadcn@latest add button input card badge scroll-area separator textarea
```

**Step 7: Verify Tailwind works**

Replace App.tsx with a simple dark-themed div with Tailwind classes. Confirm styles render in browser.

**Step 8: Commit**

```bash
git add web/
git commit -m "feat(web): setup Tailwind CSS + shadcn/ui with dark theme"
```

---

### Task 3: API Client Library

**Files:**
- Create: `web/src/lib/api.ts`

**Step 1: Write API client**

```typescript
const BASE = "";

// --- Sessions ---
export async function fetchSessions() {
  const res = await fetch(`${BASE}/api/sessions`);
  if (!res.ok) throw new Error(`GET /sessions: ${res.status}`);
  return res.json();
}

export async function createSession(data: { name: string; repo_path?: string }) {
  const res = await fetch(`${BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`POST /sessions: ${res.status}`);
  return res.json();
}

export async function deleteSession(id: string) {
  const res = await fetch(`${BASE}/api/sessions/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE /sessions: ${res.status}`);
}

// --- Chat (SSE via fetch + ReadableStream) ---
export async function* streamChat(sessionId: string, message: string) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) throw new Error(`POST /chat: ${res.status}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop()!;

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data === "[DONE]") return;
        yield data;
      }
    }
  }
}

// --- Tasks ---
export async function fetchTasks(sessionId: string) {
  const res = await fetch(`${BASE}/api/threads/tasks/${sessionId}`);
  if (!res.ok) throw new Error(`GET /tasks: ${res.status}`);
  return res.json();
}

export async function createTask(data: {
  session_id: string;
  title: string;
  description?: string;
  priority?: string;
}) {
  const res = await fetch(`${BASE}/api/threads/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`POST /tasks: ${res.status}`);
  return res.json();
}

export async function deleteTask(sessionId: string, taskId: string) {
  const res = await fetch(`${BASE}/api/threads/tasks/${sessionId}/${taskId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`DELETE /tasks: ${res.status}`);
}
```

**Step 2: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat(web): add API client library for sessions, chat, tasks"
```

---

### Task 4: Custom React Hooks

**Files:**
- Create: `web/src/hooks/use-sessions.ts`
- Create: `web/src/hooks/use-chat.ts`
- Create: `web/src/hooks/use-tasks.ts`
- Create: `web/src/hooks/use-websocket.ts`

**Step 1: Write useSessions hook**

```typescript
import { useCallback, useEffect, useState } from "react";
import { fetchSessions, createSession, deleteSession } from "@/lib/api";

export interface Session {
  id: string;
  name: string;
  repo_path: string | null;
  status: string;
  created_at: string;
  max_workers: number;
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setSessions(await fetchSessions());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const create = async (name: string, repoPath?: string) => {
    const s = await createSession({ name, repo_path: repoPath });
    setSessions((prev) => [...prev, s]);
    return s;
  };

  const remove = async (id: string) => {
    await deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  };

  return { sessions, loading, refresh, create, remove };
}
```

**Step 2: Write useChat hook**

```typescript
import { useCallback, useState } from "react";
import { streamChat } from "@/lib/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export function useChat(sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);

  const send = useCallback(async (text: string) => {
    if (!sessionId || streaming) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setStreaming(true);

    let full = "";
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      for await (const chunk of streamChat(sessionId, text)) {
        full += chunk;
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: full };
          return updated;
        });
      }
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: full + `\n\n[Error: ${e}]`,
        };
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  }, [sessionId, streaming]);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, streaming, send, clear };
}
```

**Step 3: Write useTasks hook**

```typescript
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchTasks, createTask, deleteTask } from "@/lib/api";

export interface Task {
  id: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  created_at: string;
}

export function useTasks(sessionId: string | null) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    setTasks(await fetchTasks(sessionId));
  }, [sessionId]);

  // Poll every 3s
  useEffect(() => {
    if (!sessionId) { setTasks([]); return; }
    refresh();
    intervalRef.current = setInterval(refresh, 3000);
    return () => clearInterval(intervalRef.current);
  }, [sessionId, refresh]);

  const add = async (title: string, description: string, priority: string) => {
    if (!sessionId) return;
    const t = await createTask({ session_id: sessionId, title, description, priority });
    setTasks((prev) => [...prev, t]);
  };

  const remove = async (taskId: string) => {
    if (!sessionId) return;
    await deleteTask(sessionId, taskId);
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
  };

  return { tasks, refresh, add, remove };
}
```

**Step 4: Write useWebSocket hook**

```typescript
import { useEffect, useRef } from "react";

export function useWebSocket(
  url: string | null,
  onMessage: (data: unknown) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!url) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data));
      } catch {
        onMessage(ev.data);
      }
    };

    // Ping every 30s to keep alive
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30000);

    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, [url, onMessage]);

  return wsRef;
}
```

**Step 5: Commit**

```bash
git add web/src/hooks/
git commit -m "feat(web): add React hooks for sessions, chat SSE, tasks, websocket"
```

---

### Task 5: Sessions Sidebar Component

**Files:**
- Create: `web/src/components/sidebar/session-list.tsx`
- Create: `web/src/components/sidebar/session-item.tsx`

**Step 1: Write SessionItem**

A single row: session name, repo path truncated, status badge. Click to select, right-click or X button to delete.

**Step 2: Write SessionList**

List of SessionItems + "New Session" button at bottom. Input field appears inline when creating.

**Step 3: Verify renders**

Wire into App.tsx temporarily, confirm list renders with mock data or against running backend.

**Step 4: Commit**

```bash
git add web/src/components/sidebar/
git commit -m "feat(web): add Sessions sidebar components"
```

---

### Task 6: Chat Panel Component

**Files:**
- Create: `web/src/components/chat/chat-panel.tsx`
- Create: `web/src/components/chat/message.tsx`
- Create: `web/src/components/chat/chat-input.tsx`

**Step 1: Write Message component**

Render user messages (right-aligned, muted bg) and assistant messages (left-aligned). Support markdown-like code blocks with `<pre>` tags. Auto-scroll to bottom on new messages.

**Step 2: Write ChatInput**

Textarea with Ctrl+Enter to send. Disable while streaming. Show streaming indicator.

**Step 3: Write ChatPanel**

Combines ScrollArea of Messages + ChatInput. Uses `useChat` hook. Shows "Select a session" placeholder when no session active.

**Step 4: Verify SSE streaming works**

Start FastAPI backend (`uv run server.py`), start Vite dev (`pnpm dev`). Select session, send message, confirm chunks stream in.

**Step 5: Commit**

```bash
git add web/src/components/chat/
git commit -m "feat(web): add Chat panel with SSE streaming"
```

---

### Task 7: Threads Panel Component

**Files:**
- Create: `web/src/components/threads/thread-panel.tsx`
- Create: `web/src/components/threads/task-card.tsx`
- Create: `web/src/components/threads/add-task-form.tsx`

**Step 1: Write TaskCard**

Card with: priority badge (P0=red, P1=yellow, P2=gray), title, status badge (queued/running/completed/failed), delete button.

**Step 2: Write AddTaskForm**

Inline form: title input, description textarea, priority select (P0/P1/P2), submit button.

**Step 3: Write ThreadPanel**

List of TaskCards sorted by priority + AddTaskForm at bottom. Uses `useTasks` hook. Shows "No tasks" empty state.

**Step 4: Commit**

```bash
git add web/src/components/threads/
git commit -m "feat(web): add Threads panel with task queue management"
```

---

### Task 8: App Layout + Integration

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/globals.css` (if needed)

**Step 1: Wire three-panel layout**

```tsx
function App() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const sessionHook = useSessions();
  const chatHook = useChat(activeSessionId);
  const tasksHook = useTasks(activeSessionId);

  return (
    <div className="flex h-screen bg-background text-foreground">
      <SessionList ... />
      <ChatPanel ... />
      <ThreadPanel ... />
    </div>
  );
}
```

**Step 2: Handle session switching**

When `activeSessionId` changes, clear chat messages and reload tasks.

**Step 3: WebSocket integration**

Connect to `/ws/sessions/{id}` when session is active. On worker_completed events, show notification in chat.

**Step 4: localStorage draft persistence**

Save chat input draft per session to localStorage. Restore on session switch.

**Step 5: Verify full flow**

1. Start backend: `uv run server.py`
2. Start frontend: `cd web && pnpm dev`
3. Create session → appears in sidebar
4. Select session → chat panel active
5. Send message → SSE streams response
6. Add task → appears in threads panel
7. Delete task → removed from list

**Step 6: Commit**

```bash
git add web/src/
git commit -m "feat(web): integrate three-panel layout with full data flow"
```

---

### Task 9: Production Build + Static Serving

**Files:**
- Modify: `web/vite.config.ts` (verify build.outDir)
- Modify: `.gitignore` (add web/static/)

**Step 1: Build for production**

```bash
cd web && pnpm build
```

Expected: Output in `web/static/` with index.html + assets/.

**Step 2: Verify FastAPI serves static**

```bash
cd /home/zixu/codes/code-conductor
uv run server.py
# Visit http://localhost:8000 — should serve the React app
```

**Step 3: Add web/static/ to .gitignore**

Build artifacts should not be committed.

**Step 4: Update task_plan.md**

Mark Phase 6 as complete.

**Step 5: Commit**

```bash
git add .gitignore web/vite.config.ts
git commit -m "feat(web): configure production build to web/static/"
```

---

## Summary

| Task | Description | Est. Steps |
|------|-------------|------------|
| 1 | Vite scaffold | 5 |
| 2 | Tailwind + shadcn/ui | 8 |
| 3 | API client library | 2 |
| 4 | React hooks | 5 |
| 5 | Sessions sidebar | 4 |
| 6 | Chat panel + SSE | 5 |
| 7 | Threads panel | 4 |
| 8 | App layout integration | 6 |
| 9 | Production build | 5 |
