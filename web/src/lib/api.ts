const BASE = "";

// --- Sessions ---
export interface Session {
  id: string;
  name: string;
  repo_path: string | null;
  repo_url: string | null;
  base_branch: string;
  status: string;
  created_at: string;
  updated_at: string;
  max_workers: number;
  conversation_history: Array<{ role: string; content: string }>;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  created_at: string;
  updated_at: string;
  thread_id: string | null;
  retry_count: number;
  error_context: string | null;
}

export async function fetchSessions(): Promise<Session[]> {
  const res = await fetch(`${BASE}/api/sessions`);
  if (!res.ok) throw new Error(`GET /sessions: ${res.status}`);
  return res.json();
}

export async function createSession(data: { name: string; repo_path?: string }): Promise<Session> {
  const res = await fetch(`${BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`POST /sessions: ${res.status}`);
  return res.json();
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${BASE}/api/sessions/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE /sessions: ${res.status}`);
}

// --- Chat (SSE via fetch + ReadableStream) ---
export async function* streamChat(sessionId: string, message: string): AsyncGenerator<string> {
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
export async function fetchTasks(sessionId: string): Promise<Task[]> {
  const res = await fetch(`${BASE}/api/threads/tasks/${sessionId}`);
  if (!res.ok) throw new Error(`GET /tasks: ${res.status}`);
  return res.json();
}

export async function createTask(data: {
  session_id: string;
  title: string;
  description?: string;
  priority?: string;
}): Promise<Task> {
  const res = await fetch(`${BASE}/api/threads/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`POST /tasks: ${res.status}`);
  return res.json();
}

export async function deleteTask(sessionId: string, taskId: string): Promise<void> {
  const res = await fetch(`${BASE}/api/threads/tasks/${sessionId}/${taskId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`DELETE /tasks: ${res.status}`);
}
