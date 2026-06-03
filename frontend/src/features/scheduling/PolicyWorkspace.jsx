import { Descriptions, Empty, Progress, Tag } from "@arco-design/web-react";

function findPolicy(artifacts) {
  return artifacts?.policy ?? artifacts?.commit?.policy ?? artifacts?.dashboard_payload?.policy ?? null;
}

function findSimulation(artifacts) {
  return artifacts?.simulation ?? null;
}

export function PolicyWorkspace({ artifacts, commitPolicyId }) {
  const policy = findPolicy(artifacts);
  const simulation = findSimulation(artifacts);
  if (!policy && !simulation && !commitPolicyId) {
    return <Empty className="tj-ai-empty" description="Policy draft will appear here" />;
  }
  const decision = policy?.decision ?? policy?.preview_decision ?? {};
  const score = Number(decision.fusion_score ?? simulation?.score ?? 0);
  return (
    <div className="tj-ai-policy">
      <div className="tj-ai-policy-head">
        <div>
          <span>Policy workspace</span>
          <h3>{policy?.policy_id ?? commitPolicyId ?? "Draft pending"}</h3>
        </div>
        <Tag color={simulation?.feasible === false ? "red" : "green"}>{simulation?.feasible === false ? "blocked" : "ready"}</Tag>
      </div>
      <Progress percent={Math.round(score * 100)} size="small" />
      <Descriptions
        column={1}
        data={[
          { label: "Selected node", value: decision.selected_node ?? "-" },
          { label: "Reason", value: decision.reason ?? policy?.explanation ?? "-" },
          { label: "Latency", value: decision.predicted_latency_ms ? `${Number(decision.predicted_latency_ms).toFixed(1)} ms` : "-" },
          { label: "Cost", value: decision.predicted_cost ? Number(decision.predicted_cost).toFixed(3) : "-" },
          { label: "Risk", value: simulation?.risk_summary ?? policy?.risk_summary ?? "-" },
        ]}
      />
    </div>
  );
}
