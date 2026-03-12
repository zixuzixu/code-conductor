import { useCallback, useEffect, useState } from "react";
import { type Session, fetchSessions, createSession, deleteSession } from "@/lib/api";

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

  useEffect(() => {
    refresh();
  }, [refresh]);

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
