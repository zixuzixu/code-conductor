import { Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { Session } from "@/lib/api";
import { SessionItem } from "./session-item";

interface SessionListProps {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: (name: string) => void;
  onDelete: (id: string) => void;
}

export function SessionList({ sessions, activeId, onSelect, onCreate, onDelete }: SessionListProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const handleCreate = () => {
    if (!newName.trim()) return;
    onCreate(newName.trim());
    setNewName("");
    setCreating(false);
  };

  return (
    <div className="flex h-full w-60 flex-col border-r border-border bg-sidebar-background">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold text-sidebar-foreground">Sessions</h2>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-sidebar-foreground"
          onClick={() => setCreating(!creating)}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <Separator />
      {creating && (
        <div className="px-3 py-2">
          <Input
            autoFocus
            placeholder="Session name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
              if (e.key === "Escape") setCreating(false);
            }}
            className="h-8 text-sm"
          />
        </div>
      )}
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
