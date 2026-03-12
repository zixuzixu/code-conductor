import { GripVertical } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { PlanStep } from "@/lib/api";

interface PlanStepRowProps {
  step: PlanStep;
  onToggle: () => void;
  onPriorityChange: (priority: string) => void;
}

const priorityColors: Record<string, string> = {
  p0: "bg-red-500/15 text-red-500",
  p1: "bg-yellow-500/15 text-yellow-500",
  p2: "bg-zinc-500/15 text-zinc-400",
};

export function PlanStepRow({ step, onToggle, onPriorityChange }: PlanStepRowProps) {
  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${
        step.enabled ? "border-border" : "border-border/50 opacity-50"
      }`}
    >
      <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <input
        type="checkbox"
        checked={step.enabled}
        onChange={onToggle}
        className="mt-1 shrink-0 accent-primary"
      />
      <p className="flex-1 leading-relaxed">{step.description}</p>
      <select
        value={step.priority}
        onChange={(e) => onPriorityChange(e.target.value)}
        className="shrink-0 rounded border border-border bg-transparent px-1 py-0.5 text-xs"
      >
        <option value="p0">P0</option>
        <option value="p1">P1</option>
        <option value="p2">P2</option>
      </select>
      <Badge className={`shrink-0 ${priorityColors[step.priority] || ""}`}>
        {step.priority.toUpperCase()}
      </Badge>
    </div>
  );
}
