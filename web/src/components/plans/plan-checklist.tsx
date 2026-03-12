import { Check, CheckCheck, Play, Square, Trash2, X } from "lucide-react";
import { useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Plan, PlanStep } from "@/lib/api";
import { PlanStepRow } from "./plan-step";

interface PlanChecklistProps {
  plan: Plan;
  onUpdate: (planId: string, data: { steps?: PlanStep[]; status?: string }) => void;
  onExecute: (planId: string) => void;
  onDelete: (planId: string) => void;
}

const statusColors: Record<string, string> = {
  draft: "bg-zinc-500/15 text-zinc-400",
  approved: "bg-blue-500/15 text-blue-500",
  executing: "bg-amber-500/15 text-amber-500",
  completed: "bg-green-500/15 text-green-500",
};

export function PlanChecklist({ plan, onUpdate, onExecute, onDelete }: PlanChecklistProps) {
  const enabledCount = plan.steps.filter((s) => s.enabled).length;
  const isEditable = plan.status === "draft" || plan.status === "approved";

  const toggleStep = useCallback(
    (index: number) => {
      const updated = plan.steps.map((s, i) =>
        i === index ? { ...s, enabled: !s.enabled } : s,
      );
      onUpdate(plan.id, { steps: updated });
    },
    [plan, onUpdate],
  );

  const changePriority = useCallback(
    (index: number, priority: string) => {
      const updated = plan.steps.map((s, i) =>
        i === index ? { ...s, priority } : s,
      );
      onUpdate(plan.id, { steps: updated });
    },
    [plan, onUpdate],
  );

  const toggleAll = useCallback(
    (enabled: boolean) => {
      const updated = plan.steps.map((s) => ({ ...s, enabled }));
      onUpdate(plan.id, { steps: updated });
    },
    [plan, onUpdate],
  );

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{plan.title || "Untitled Plan"}</h3>
          <Badge className={statusColors[plan.status] || ""}>{plan.status}</Badge>
        </div>
        <div className="flex items-center gap-1">
          {isEditable && (
            <>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => toggleAll(true)}
                title="Enable all"
              >
                <CheckCheck className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => toggleAll(false)}
                title="Disable all"
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => onDelete(plan.id)}
            className="text-destructive"
            title="Delete plan"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Step list */}
      <ScrollArea className="max-h-[400px]">
        <div className="space-y-1.5">
          {plan.steps.map((step, i) => (
            <PlanStepRow
              key={step.id}
              step={step}
              onToggle={() => isEditable && toggleStep(i)}
              onPriorityChange={(p) => isEditable && changePriority(i, p)}
            />
          ))}
          {plan.steps.length === 0 && (
            <p className="py-4 text-center text-xs text-muted-foreground">No steps</p>
          )}
        </div>
      </ScrollArea>

      {/* Actions */}
      {isEditable && (
        <div className="flex items-center justify-between border-t border-border pt-3">
          <span className="text-xs text-muted-foreground">
            {enabledCount}/{plan.steps.length} steps enabled
          </span>
          <div className="flex gap-2">
            {plan.status === "draft" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onUpdate(plan.id, { status: "approved" })}
              >
                <Check className="mr-1 h-3.5 w-3.5" />
                Approve
              </Button>
            )}
            <Button
              size="sm"
              onClick={() => onExecute(plan.id)}
              disabled={enabledCount === 0}
            >
              <Play className="mr-1 h-3.5 w-3.5" />
              Execute ({enabledCount})
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
