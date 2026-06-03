import { Descriptions, Empty, Progress, Tag } from "@arco-design/web-react";

function findPolicy(artifacts) {
  return artifacts?.policy ?? artifacts?.commit?.policy ?? artifacts?.dashboard_payload?.policy ?? null;
}

function findSimulation(artifacts) {
  return artifacts?.simulation ?? null;
}

function formatValue(value) {
  if (value == null || value === "") return "-";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) {
    const items = value.map((item) => formatValue(item)).filter((item) => item !== "-");
    return items.length ? items.join("；") : "-";
  }
  if (typeof value === "object") {
    const summary = typeof value.summary === "string" && value.summary.trim() ? value.summary.trim() : null;
    const details = [
      ...(Array.isArray(value.factors) ? value.factors : []),
      ...(Array.isArray(value.risks) ? value.risks : []),
      ...(Array.isArray(value.questions) ? value.questions : []),
    ].filter(Boolean);
    if (summary && details.length) return `${summary}；${details.join("；")}`;
    if (summary) return summary;
    if (details.length) return details.join("；");
    try {
      return JSON.stringify(value);
    } catch {
      return "-";
    }
  }
  return String(value);
}

function pickNumber(...values) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

function getDecisionNodeId(decision, policy) {
  return (
    decision?.selected_node
    ?? decision?.node_id
    ?? decision?.selected_compute?.node_id
    ?? policy?.selected_compute?.node_id
    ?? null
  );
}

function getDecisionScore(decision, simulation) {
  const rawScore = pickNumber(
    decision?.fusion_score,
    decision?.total_score,
    decision?.match_score,
    decision?.score,
    decision?.network_snapshot?.feature_fusion_score,
    simulation?.score,
  );
  if (rawScore == null) return 0;
  const normalized = rawScore > 1 ? rawScore / 100 : rawScore;
  return Math.max(0, Math.min(1, normalized));
}

function getDecisionLatency(decision, policy) {
  return pickNumber(
    decision?.predicted_latency_ms,
    decision?.network_snapshot?.deterministic_latency_ms,
    decision?.network_snapshot?.stable_latency_ms,
    policy?.selected_network?.stable_latency_ms,
  );
}

function getDecisionCost(decision, policy) {
  return pickNumber(
    decision?.predicted_cost,
    policy?.expected_effect?.cost?.expected_cost,
  );
}

function getPolicyStatus(artifacts, simulation, commitPolicyId) {
  if (artifacts?.commit) return { color: "arcoblue", label: "已提交" };
  if (simulation?.feasible === false) return { color: "red", label: "受阻" };
  if (simulation?.feasible === true && commitPolicyId) return { color: "green", label: "可提交" };
  return { color: "orange", label: "等待仿真" };
}

export function PolicyWorkspace({ artifacts, commitPolicyId }) {
  const policy = findPolicy(artifacts);
  const simulation = findSimulation(artifacts);
  if (!policy && !simulation && !commitPolicyId) {
    return <Empty className="tj-ai-empty" description="策略草案会显示在这里" />;
  }
  const decision = policy?.decision ?? policy?.preview_decision ?? {};
  const nodeId = getDecisionNodeId(decision, policy);
  const score = getDecisionScore(decision, simulation);
  const latency = getDecisionLatency(decision, policy);
  const cost = getDecisionCost(decision, policy);
  const riskValue = simulation?.risk_summary ?? simulation?.risks ?? policy?.risk_summary ?? policy?.explanation?.risks ?? "-";
  const status = getPolicyStatus(artifacts, simulation, commitPolicyId);
  return (
    <div className="tj-ai-policy">
      <div className="tj-ai-policy-head">
        <div>
          <span>策略工作区</span>
          <h3>{policy?.policy_id ?? commitPolicyId ?? "草案生成中"}</h3>
        </div>
        <Tag color={status.color}>{status.label}</Tag>
      </div>
      <Progress percent={Math.round(score * 100)} size="small" />
      <Descriptions
        column={1}
        data={[
          { label: "选中节点", value: formatValue(nodeId) },
          { label: "推荐说明", value: formatValue(decision.reason ?? decision.explanation ?? policy?.explanation) },
          { label: "预测时延", value: latency != null ? `${latency.toFixed(1)} ms` : "-" },
          { label: "预测成本", value: cost != null ? cost.toFixed(3) : "-" },
          { label: "风险提示", value: formatValue(riskValue) },
        ]}
      />
    </div>
  );
}
