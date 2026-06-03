import { Card, Grid, List, Table, Tag, Typography } from "@arco-design/web-react";
import { EmptyState } from "../features/common/EmptyState.jsx";
import { KpiCard } from "../features/common/KpiCard.jsx";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { WeightChart } from "../features/charts/WeightChart.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { num } from "../utils/format.js";

const { Row, Col } = Grid;

export function ModelPolicyPage() {
  const { report, state } = useControlPlaneContext();
  const policies = report?.policies ?? [];
  const history = report?.policy_history ?? [];
  return (
    <div className="tj-page">
      <PageHeader eyebrow="P5 / MODEL & POLICY" title="模型与策略" description="展示模型加载状态、调度权重、策略草案和可解释调整历史。" />
      <Row gutter={[16, 16]}>
        <Col span={6}><KpiCard title="模型运行时" value={state.model?.status ?? "unknown"} tone="ink" /></Col>
        <Col span={6}><KpiCard title="已加载模型" value={(state.model?.loaded_models ?? []).length} trend={(state.model?.loaded_models ?? []).join(" / ") || "fallback"} /></Col>
        <Col span={6}><KpiCard title="融合评分" value={num(report?.metrics?.average_fusion_score, 3)} /></Col>
        <Col span={6}><KpiCard title="确定性置信" value={num(report?.metrics?.average_deterministic_confidence, 3)} tone="green" /></Col>
      </Row>
      <Row gutter={[16, 16]} className="tj-section-row">
        <Col span={12}>
          <Card title="策略权重" bordered={false} className="tj-panel">
            <WeightChart weights={report?.policy_weights ?? {}} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="模型解释" bordered={false} className="tj-panel">
            <List
              dataSource={report?.algorithm_profile?.features ?? []}
              render={(item) => (
                <List.Item>
                  <Tag color="arcoblue">{item}</Tag>
                  <Typography.Text type="secondary">{report?.algorithm_profile?.model_status ?? "unknown"}</Typography.Text>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
      <Card title="策略草案" bordered={false} className="tj-panel tj-section-row">
        {policies.length ? (
          <Table
            rowKey="policy_id"
            data={policies}
            pagination={false}
            columns={[
              { title: "策略", dataIndex: "policy_id" },
              { title: "状态", dataIndex: "status", render: (value) => <Tag>{value}</Tag> },
              { title: "任务", dataIndex: "task_id" },
              { title: "推荐节点", render: (_, item) => item.selected_compute?.node_id ?? "-" },
            ]}
          />
        ) : <EmptyState description="暂无策略草案" />}
      </Card>
      <Card title="权重调整历史" bordered={false} className="tj-panel tj-section-row">
        {history.length ? (
          <List dataSource={history.slice().reverse().slice(0, 6)} render={(item) => <List.Item>tick {item.tick}: {(item.reasons ?? []).join(" / ")}</List.Item>} />
        ) : <EmptyState description="暂无调权历史" />}
      </Card>
    </div>
  );
}
