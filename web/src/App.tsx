import { useCallback, useState } from "react";
import { MessageSquare, ListTodo, Menu, Sun, Moon } from "lucide-react";
import { SessionList } from "@/components/sidebar/session-list";
import { ChatPanel } from "@/components/chat/chat-panel";
import { ThreadPanel } from "@/components/threads/thread-panel";
import { PlansPanel } from "@/components/plans/plans-panel";
import { QuotaBanner } from "@/components/threads/quota-banner";
import { Button } from "@/components/ui/button";
import { useSessions } from "@/hooks/use-sessions";
import { useChat } from "@/hooks/use-chat";
import { useTasks } from "@/hooks/use-tasks";
import { usePlans } from "@/hooks/use-plans";
import { useWebSocket } from "@/hooks/use-websocket";
import { useTheme } from "@/hooks/use-theme";

type MobilePanel = "sessions" | "chat" | "tasks";

function App() {
  const { resolved, toggle } = useTheme();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [quotaPaused, setQuotaPaused] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("chat");
  const { sessions, create, remove } = useSessions();
  const { messages, streaming, send, clear } = useChat(activeSessionId);
  const { tasks, add: addTask, remove: removeTask } = useTasks(activeSessionId);
  const { plans, update: updatePlan, execute: executePlan, remove: removePlan } = usePlans(activeSessionId);

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

  const handleResumeDispatch = useCallback(async () => {
    if (!activeSessionId) return;
    try {
      const { resumeDispatch } = await import("@/lib/api");
      await resumeDispatch(activeSessionId);
    } catch (e) {
      console.error("Failed to resume dispatch:", e);
    }
    setQuotaPaused(false);
  }, [activeSessionId]);

  // WebSocket: listen for worker events on active session
  const handleWsMessage = useCallback((data: unknown) => {
    const event = data as Record<string, unknown>;
    if (event?.type === "quota_exhausted") {
      setQuotaPaused(true);
    }
    console.log("[ws]", data);
  }, []);

  useWebSocket(
    activeSessionId ? `/ws/sessions/${activeSessionId}` : null,
    handleWsMessage,
  );

  return (
    <div className="flex h-screen flex-col bg-background text-foreground lg:flex-row">
      {/* Desktop: always visible sidebar; Mobile: shown when mobilePanel === "sessions" */}
      <div className={`${mobilePanel === "sessions" ? "flex" : "hidden"} flex-col lg:flex`}>
        <SessionList
          sessions={sessions}
          activeId={activeSessionId}
          onSelect={(id) => {
            handleSelectSession(id);
            setMobilePanel("chat");
          }}
          onCreate={handleCreateSession}
          onDelete={handleDeleteSession}
        />
      </div>

      {/* Desktop: always visible chat; Mobile: shown when mobilePanel === "chat" */}
      <div className={`${mobilePanel === "chat" ? "flex" : "hidden"} min-w-0 flex-1 lg:flex`}>
        <ChatPanel
          messages={messages}
          streaming={streaming}
          onSend={send}
          sessionId={activeSessionId}
        />
      </div>

      {/* Desktop: always visible threads; Mobile: shown when mobilePanel === "tasks" */}
      <div className={`${mobilePanel === "tasks" ? "flex" : "hidden"} flex-col lg:flex`}>
        {quotaPaused && (
          <QuotaBanner onResume={handleResumeDispatch} />
        )}
        <ThreadPanel
          tasks={tasks}
          sessionId={activeSessionId}
          onAdd={addTask}
          onDelete={removeTask}
        />
        <PlansPanel
          plans={plans}
          onUpdate={updatePlan}
          onExecute={executePlan}
          onDelete={removePlan}
        />
      </div>

      {/* Mobile bottom tab bar */}
      <nav className="flex shrink-0 items-center justify-around border-t border-border bg-sidebar-background px-2 py-1 lg:hidden">
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5"
          onClick={toggle}
        >
          {resolved === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </Button>
        <Button
          variant={mobilePanel === "sessions" ? "secondary" : "ghost"}
          size="sm"
          className="flex-1 gap-1.5"
          onClick={() => setMobilePanel("sessions")}
        >
          <Menu className="h-4 w-4" />
          <span className="text-xs">Sessions</span>
        </Button>
        <Button
          variant={mobilePanel === "chat" ? "secondary" : "ghost"}
          size="sm"
          className="flex-1 gap-1.5"
          onClick={() => setMobilePanel("chat")}
        >
          <MessageSquare className="h-4 w-4" />
          <span className="text-xs">Chat</span>
        </Button>
        <Button
          variant={mobilePanel === "tasks" ? "secondary" : "ghost"}
          size="sm"
          className="flex-1 gap-1.5"
          onClick={() => setMobilePanel("tasks")}
        >
          <ListTodo className="h-4 w-4" />
          <span className="text-xs">Tasks</span>
        </Button>
      </nav>
    </div>
  );
}

export default App;
