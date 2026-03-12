import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { Task } from "@/lib/api";
import { AddTaskForm } from "./add-task-form";
import { TaskCard } from "./task-card";

interface ThreadPanelProps {
  tasks: Task[];
  sessionId: string | null;
  onAdd: (title: string, description: string, priority: string) => void;
  onDelete: (taskId: string) => void;
}

export function ThreadPanel({ tasks, sessionId, onAdd, onDelete }: ThreadPanelProps) {
  return (
    <div className="flex h-full w-80 flex-col border-l border-border">
      <div className="px-4 py-3">
        <h2 className="text-sm font-semibold">Threads</h2>
        <p className="text-xs text-muted-foreground">
          {tasks.length} task{tasks.length !== 1 ? "s" : ""}
        </p>
      </div>
      <Separator />
      <ScrollArea className="flex-1 p-3">
        {!sessionId ? (
          <p className="px-2 py-8 text-center text-xs text-muted-foreground">
            Select a session
          </p>
        ) : tasks.length === 0 ? (
          <p className="px-2 py-8 text-center text-xs text-muted-foreground">
            No tasks in queue
          </p>
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <TaskCard key={t.id} task={t} onDelete={() => onDelete(t.id)} />
            ))}
          </div>
        )}
      </ScrollArea>
      {sessionId && (
        <>
          <Separator />
          <div className="p-3">
            <AddTaskForm onAdd={onAdd} />
          </div>
        </>
      )}
    </div>
  );
}
