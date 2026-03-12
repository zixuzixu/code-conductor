import { Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface AddTaskFormProps {
  onAdd: (title: string, description: string, priority: string) => void;
}

export function AddTaskForm({ onAdd }: AddTaskFormProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("p1");

  const handleSubmit = () => {
    if (!title.trim()) return;
    onAdd(title.trim(), "", priority);
    setTitle("");
    setOpen(false);
  };

  if (!open) {
    return (
      <Button
        variant="ghost"
        className="w-full justify-start text-muted-foreground"
        onClick={() => setOpen(true)}
      >
        <Plus className="mr-2 h-4 w-4" />
        Add Task
      </Button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <Input
        autoFocus
        placeholder="Task title..."
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") handleSubmit();
          if (e.key === "Escape") setOpen(false);
        }}
        className="h-8 text-sm"
      />
      <div className="flex items-center gap-2">
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="p0">P0 - Immediate</option>
          <option value="p1">P1 - Standard</option>
          <option value="p2">P2 - Background</option>
        </select>
        <div className="flex-1" />
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={!title.trim()}>
          Add
        </Button>
      </div>
    </div>
  );
}
