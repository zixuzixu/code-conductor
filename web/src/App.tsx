import { useCallback, useState } from "react";
import { SessionList } from "@/components/sidebar/session-list";
import { ChatPanel } from "@/components/chat/chat-panel";
import { ThreadPanel } from "@/components/threads/thread-panel";
import { useSessions } from "@/hooks/use-sessions";
import { useChat } from "@/hooks/use-chat";
import { useTasks } from "@/hooks/use-tasks";
import { useWebSocket } from "@/hooks/use-websocket";


function App() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const { sessions, create, remove } = useSessions();
  const { messages, streaming, send, clear } = useChat(activeSessionId);
  const { tasks, add: addTask, remove: removeTask } = useTasks(activeSessionId);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id !== activeSessionId) {
        setActiveSessionId(id);
        clear();
      }
    },
    [activeSessionId, clear],
  );

  const handleCreateSession = useCallback(
    async (name: string) => {
      const s = await create(name);
      setActiveSessionId(s.id);
    },
    [create],
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      await remove(id);
      if (activeSessionId === id) {
        setActiveSessionId(null);
        clear();
      }
    },
    [activeSessionId, remove, clear],
  );

  // WebSocket: listen for worker events on active session
  const handleWsMessage = useCallback((data: unknown) => {
    // For now, log worker events. Future: show notifications in chat.
    console.log("[ws]", data);
  }, []);

  useWebSocket(
    activeSessionId ? `/ws/sessions/${activeSessionId}` : null,
    handleWsMessage,
  );

  return (
    <div className="flex h-screen bg-background text-foreground">
      <SessionList
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={handleSelectSession}
        onCreate={handleCreateSession}
        onDelete={handleDeleteSession}
      />
      <ChatPanel
        messages={messages}
        streaming={streaming}
        onSend={send}
        sessionId={activeSessionId}
      />
      <ThreadPanel
        tasks={tasks}
        sessionId={activeSessionId}
        onAdd={addTask}
        onDelete={removeTask}
      />
    </div>
  );
}

export default App;
