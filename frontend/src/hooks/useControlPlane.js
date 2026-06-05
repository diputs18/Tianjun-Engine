import { useCallback, useEffect, useMemo, useState } from "react";
import { getHealth, getReport } from "../services/api.js";

const REFRESH_MS = 5000;

export function useControlPlane() {
  const [report, setReport] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [nextReport, nextHealth] = await Promise.all([getReport(), getHealth()]);
      setReport(nextReport);
      setHealth(nextHealth);
      setUpdatedAt(new Date());
    } catch (nextError) {
      setError(nextError);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const handle = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(handle);
  }, [refresh]);

  const state = useMemo(() => {
    const nodes = report?.nodes ?? [];
    const onlineNodes = nodes.filter((node) => node.online).length;
    const totals = report?.totals ?? {};
    const metrics = report?.metrics ?? {};
    const model = report?.model_runtime ?? health?.model_runtime ?? {};
    const llm = health?.chat_runtime?.llm ?? {};
    return {
      nodes,
      totals,
      metrics,
      model,
      llm,
      onlineNodes,
      nodeCount: nodes.length,
      healthStatus: error ? "degraded" : "ok",
      slaRate: Number(metrics.sla_rate ?? 0),
      successRate: Number(metrics.success_rate ?? 0),
      pendingTasks: Number(totals.pending_tasks ?? 0),
      runningTasks: Number(totals.running_tasks ?? totals.leased_tasks ?? 0),
      modelLoaded: model.status === "loaded",
      llmEnabled: Boolean(llm.enabled),
    };
  }, [error, health, report]);

  return { report, health, loading, error, updatedAt, refresh, state };
}
