import { Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Task } from "@/lib/api";

interface TaskCardProps {
  task: Task;
  onDelete: () => void;
}

const priorityColors: Record<string, string> = {
  p0: "bg-red-500/20 text-red-400 border-red-500/30",
  p1: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  p2: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

const statusColors: Record<string, string> = {
  queued: "bg-blue-500/20 text-blue-400",
  in_progress: "bg-amber-500/20 text-amber-400",
  completed: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
  pending_review: "bg-purple-500/20 text-purple-400",
  pending_quota: "bg-orange-500/20 text-orange-400",
};

export function TaskCard({ task, onDelete }: TaskCardProps) {
  return (
    <div className="group rounded-lg border border-border bg-card p-3 transition-colors hover:border-accent">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn("text-[10px] uppercase", priorityColors[task.priority] || "")}
            >
              {task.priority}
            </Badge>
            <Badge className={cn("text-[10px]", statusColors[task.status] || "")}>
              {task.status.replace("_", " ")}
            </Badge>
          </div>
          <p className="mt-1.5 text-sm font-medium">{task.title}</p>
          {task.description && (
            <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
              {task.description}
            </p>
          )}
        </div>
        <button
          onClick={onDelete}
          className="hidden shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive group-hover:block"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
