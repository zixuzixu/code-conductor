import { useCallback, useEffect, useState } from "react";
import {
  createPlan,
  deletePlan,
  executePlan,
  fetchPlans,
  updatePlan,
  type Plan,
  type PlanStep,
} from "@/lib/api";

export function usePlans(sessionId: string | null) {
  const [plans, setPlans] = useState<Plan[]>([]);

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setPlans([]);
      return;
    }
    try {
      setPlans(await fetchPlans(sessionId));
    } catch {
      /* silent */
    }
  }, [sessionId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(
    async (title: string, steps: Array<{ description: string; priority?: string }>) => {
      if (!sessionId) return;
      await createPlan({ session_id: sessionId, title, steps });
      await refresh();
    },
    [sessionId, refresh],
  );

  const update = useCallback(
    async (planId: string, data: { title?: string; status?: string; steps?: PlanStep[] }) => {
      await updatePlan(planId, data);
      await refresh();
    },
    [refresh],
  );

  const execute = useCallback(
    async (planId: string) => {
      const result = await executePlan(planId);
      await refresh();
      return result;
    },
    [refresh],
  );

  const remove = useCallback(
    async (planId: string) => {
      await deletePlan(planId);
      await refresh();
    },
    [refresh],
  );

  return { plans, refresh, create, update, execute, remove };
}
