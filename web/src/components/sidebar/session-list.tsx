import { Plus, Sun, Moon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { Session } from "@/lib/api";
import { SessionItem } from "./session-item";
import { useTheme } from "@/hooks/use-theme";

function generateSessionName(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `Session ${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

interface SessionListProps {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: (name: string) => void;
  onDelete: (id: string) => void;
}

export function SessionList({ sessions, activeId, onSelect, onCreate, onDelete }: SessionListProps) {
  const { resolved, toggle } = useTheme();
  const handleCreate = () => {
    onCreate(generateSessionName());
  };

  return (
    <div className="flex h-full w-full flex-col border-r border-border bg-sidebar-background lg:w-60">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold text-sidebar-foreground">Sessions</h2>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-sidebar-foreground"
            onClick={toggle}
            title={resolved === "light" ? "Switch to dark mode" : "Switch to light mode"}
          >
            {resolved === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-sidebar-foreground"
            onClick={handleCreate}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <Separator />
      <ScrollArea className="flex-1 px-2 py-1">
        <div className="space-y-0.5">
          {sessions.map((s) => (
            <SessionItem
              key={s.id}
              session={s}
              active={s.id === activeId}
              onSelect={() => onSelect(s.id)}
              onDelete={() => onDelete(s.id)}
            />
          ))}
          {sessions.length === 0 && (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              No sessions yet
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
