import { Button, Progress, Tag } from "@arco-design/web-react";
import { IconCheckCircle } from "@arco-design/web-react/icon";

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
  if (simulation?.feasible === true && commitPolicyId) return { color: "green", label: "可下发" };
  return { color: "gray", label: "空闲" };
}

function PolicyRows({ rows }) {
  return (
    <div className="tj-ai-policy-table">
      {rows.map(([label, value]) => (
        <div key={label} className="tj-ai-policy-row">
          <label>{label}</label>
          <p>{value}</p>
        </div>
      ))}
    </div>
  );
}

export function PolicyWorkspace({ artifacts, commitPolicyId, canCommit, committing, onCommit }) {
  const policy = findPolicy(artifacts);
  const simulation = findSimulation(artifacts);
  if (!policy && !simulation && !commitPolicyId) {
    return (
      <div className="tj-ai-policy tj-ai-policy-empty">
        <div className="tj-ai-policy-head">
          <div>
            <h3>策略工作区</h3>
          </div>
          <Tag color="gray">空闲</Tag>
        </div>

        <div className="tj-ai-policy-score">
          <b>0%</b>
          <Progress percent={0} showText={false} size="small" />
        </div>

        <PolicyRows rows={[
          ["推荐节点", "-"],
          ["推荐原因", "-"],
          ["预测时延", "-"],
          ["预测成本", "-"],
          ["风险提示", "-"],
        ]} />

        <div className="tj-ai-policy-placeholder">
          <span className="tj-ai-policy-placeholder-icon">□</span>
          <p>提交调度需求后将在此显示策略结果</p>
        </div>

        <Button className="tj-ai-commit-button" type="primary" size="large" disabled>
          确认下发
        </Button>
      </div>
    );
  }

  const decision = policy?.decision ?? policy?.preview_decision ?? {};
  const nodeId = getDecisionNodeId(decision, policy);
  const score = getDecisionScore(decision, simulation);
  const latency = getDecisionLatency(decision, policy);
  const cost = getDecisionCost(decision, policy);
  const riskValue = simulation?.risk_summary ?? simulation?.risks ?? policy?.risk_summary ?? policy?.explanation?.risks ?? "-";
  const status = getPolicyStatus(artifacts, simulation, commitPolicyId);
  const rows = [
    ["推荐节点", formatValue(nodeId)],
    ["推荐原因", formatValue(decision.reason ?? decision.explanation ?? policy?.explanation)],
    ["预测时延", latency != null ? `${latency.toFixed(1)} ms` : "-"],
    ["预测成本", cost != null ? cost.toFixed(3) : "-"],
    ["风险提示", formatValue(riskValue)],
  ];

  return (
    <div className="tj-ai-policy">
      <div className="tj-ai-policy-head">
        <div>
          <h3>策略工作区</h3>
          <span>{policy?.policy_id ?? commitPolicyId ?? "草案生成中"}</span>
        </div>
        <Tag color={status.color}>{status.label}</Tag>
      </div>
      <div className="tj-ai-policy-score">
        <b>{Math.round(score * 100)}%</b>
        <Progress percent={Math.round(score * 100)} showText={false} size="small" />
      </div>
      <PolicyRows rows={rows} />
      <Button
        className="tj-ai-commit-button"
        type="primary"
        size="large"
        icon={<IconCheckCircle />}
        disabled={!canCommit}
        loading={committing}
        onClick={onCommit}
      >
        确认下发
      </Button>
    </div>
  );
}
