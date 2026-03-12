import { ClipboardList } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Plan, PlanStep } from "@/lib/api";
import { PlanChecklist } from "./plan-checklist";

interface PlansPanelProps {
  plans: Plan[];
  onUpdate: (planId: string, data: { steps?: PlanStep[]; status?: string }) => void;
  onExecute: (planId: string) => void;
  onDelete: (planId: string) => void;
}

export function PlansPanel({ plans, onUpdate, onExecute, onDelete }: PlansPanelProps) {
  if (plans.length === 0) return null;

  return (
    <div className="border-t border-border">
      <div className="flex items-center gap-2 px-4 py-2">
        <ClipboardList className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-xs font-semibold text-muted-foreground">
          Plans ({plans.length})
        </h3>
      </div>
      <Separator />
      <ScrollArea className="max-h-[500px] p-3">
        <div className="space-y-3">
          {plans.map((plan) => (
            <PlanChecklist
              key={plan.id}
              plan={plan}
              onUpdate={onUpdate}
              onExecute={onExecute}
              onDelete={onDelete}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
