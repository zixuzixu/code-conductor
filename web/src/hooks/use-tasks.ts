import { useCallback, useEffect, useRef, useState } from "react";
import { type Task, fetchTasks, createTask, deleteTask } from "@/lib/api";

export function useTasks(sessionId: string | null) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      setTasks(await fetchTasks(sessionId));
    } catch {
      // Silently fail on poll errors
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setTasks([]);
      return;
    }
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
