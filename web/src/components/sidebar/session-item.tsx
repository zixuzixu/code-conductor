import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Session } from "@/lib/api";

interface SessionItemProps {
  session: Session;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export function SessionItem({ session, active, onSelect, onDelete }: SessionItemProps) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "group flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{session.name}</div>
        {session.repo_path && (
          <div className="truncate text-xs text-muted-foreground">
            {session.repo_path.split("/").pop()}
          </div>
        )}
      </div>
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.stopPropagation();
            onDelete();
          }
        }}
        className="ml-2 hidden shrink-0 rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive group-hover:inline-flex"
      >
        <X className="h-3.5 w-3.5" />
      </span>
    </button>
  );
}
