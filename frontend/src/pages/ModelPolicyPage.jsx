import { Card, Empty, Grid, Table, Tag } from "@arco-design/web-react";
import {
  IconBranch,
  IconMindMapping,
  IconSafe,
  IconStorage,
} from "@arco-design/web-react/icon";
import { useMemo } from "react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { num } from "../utils/format.js";

const { Row, Col } = Grid;

const weightOrder = [
  "resource_fit",
  "deadline_completion",
  "cost",
  "reliability",
  "load_balance",
  "locality",
  "jitter",
  "node_load",
  "bandwidth_utilization",
  "security_policy",
  "lstm_latency_prediction",
  "graphsage_topology_score",
];

function modelStatus(state) {
  if (state.modelLoaded) return "loaded";
  return state.model?.status ?? "unknown";
}

function PolicyMetric({ icon, title, value, detail, tone = "blue", iconSide = "left" }) {
  return (
    <Card className={`tj-model-metric tone-${tone} icon-${iconSide}`} bordered={false}>
      {iconSide === "left" ? <span className="tj-model-metric-icon">{icon}</span> : null}
      <div>
        <span>{title}</span>
        <b>{value}</b>
        {detail ? <small>{detail}</small> : null}
      </div>
      {iconSide === "right" ? <span className="tj-model-metric-icon">{icon}</span> : null}
    </Card>
  );
}

function WeightList({ weights, features }) {
  const featureSet = new Set(features ?? []);
  const keys = weightOrder.filter((key) => key in weights || featureSet.has(key));
  const fallbackKeys = Object.keys(weights ?? {});
  const rows = keys.length ? keys : fallbackKeys;

  return (
    <div className="tj-weight-list">
      {rows.map((key) => (
        <div className="tj-weight-row" key={key}>
          <span className="tj-weight-icon"><IconMindMapping /></span>
          <span className="tj-weight-name">{key}</span>
          <Tag color="green">loaded</Tag>
        </div>
      ))}
    </div>
  );
}

function HistoryPanel({ history }) {
  if (!history.length) {
    return (
      <div className="tj-model-empty tj-history-empty">
        <Empty description="暂无调权历史" />
      </div>
    );
  }

  return (
    <div className="tj-history-list">
      {history.slice().reverse().slice(0, 5).map((item) => (
        <div key={item.tick ?? JSON.stringify(item)}>
          <span>tick {item.tick ?? "-"}</span>
          <p>{(item.reasons ?? []).join(" / ") || "权重完成自动校准"}</p>
        </div>
      ))}
    </div>
  );
}

export function ModelPolicyPage() {
  const { report, state } = useControlPlaneContext();
  const policies = report?.policies ?? [];
  const history = report?.policy_history ?? [];
  const loadedModels = state.model?.loaded_models ?? [];
  const features = report?.algorithm_profile?.features ?? [];
  const policyWeights = report?.policy_weights ?? {};
  const draftRows = useMemo(() => policies.slice(0, 5), [policies]);

  return (
    <div className="tj-page tj-page-model-policy">
      <PageHeader eyebrow="P5 / MODEL & POLICY" title="模型与策略" />
      <Row gutter={[20, 20]} className="tj-model-metric-row">
        <Col span={6}>
          <PolicyMetric
            title="模型运行时"
            value={modelStatus(state)}
            detail={loadedModels.join(" / ") || "lstm / gnn"}
            icon={<IconMindMapping />}
            tone="purple"
          />
        </Col>
        <Col span={6}>
          <PolicyMetric title="已加载模型" value={loadedModels.length} icon={<IconStorage />} iconSide="right" />
        </Col>
        <Col span={6}>
          <PolicyMetric title="融合评分" value={num(report?.metrics?.average_fusion_score, 3)} icon={<IconBranch />} iconSide="right" />
        </Col>
        <Col span={6}>
          <PolicyMetric title="确定性置信" value={num(report?.metrics?.average_deterministic_confidence, 3)} icon={<IconSafe />} tone="blue" iconSide="right" />
        </Col>
      </Row>

      <div className="tj-model-main-grid">
        <Card title="策略权重" bordered={false} className="tj-panel tj-model-panel tj-weight-card">
          <WeightList weights={policyWeights} features={features} />
        </Card>
        <Card title="模型解释" bordered={false} className="tj-panel tj-model-panel tj-explain-card">
          <div className="tj-model-empty">
            <Empty description="暂无模型解释数据" />
          </div>
        </Card>
      </div>

      <div className="tj-model-bottom-grid">
        <Card title="策略草案" bordered={false} className="tj-panel tj-model-panel tj-draft-card">
          <Table
            className="tj-policy-table"
            rowKey="policy_id"
            data={draftRows}
            pagination={false}
            columns={[
              { title: "策略", dataIndex: "policy_id", width: 220 },
              { title: "状态", dataIndex: "status", width: 110, render: (value) => <Tag color={value === "committed" ? "green" : "arcoblue"}>{value}</Tag> },
              { title: "任务", dataIndex: "task_id", width: 240 },
              { title: "推荐节点", width: 150, render: (_, item) => item.selected_compute?.node_id ?? "-" },
            ]}
            noDataElement={<Empty description="暂无策略草案" />}
          />
        </Card>
        <Card title="权重调整历史" bordered={false} className="tj-panel tj-model-panel tj-history-card">
          <HistoryPanel history={history} />
        </Card>
      </div>
    </div>
  );
}
