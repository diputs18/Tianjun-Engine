import { Alert, Card, Grid, List, Space, Tag, Typography } from "@arco-design/web-react";
import { IconCheckCircle, IconExclamationCircle } from "@arco-design/web-react/icon";
import { KpiCard } from "../features/common/KpiCard.jsx";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { SlaChart } from "../features/charts/SlaChart.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { num, pct, regionLabel } from "../utils/format.js";

const { Row, Col } = Grid;

export function OverviewPage() {
  const { error, report, state } = useControlPlaneContext();
  const decisions = (report?.recent_decisions ?? []).slice().reverse().slice(0, 5);
  const onlineRatio = state.nodeCount ? state.onlineNodes / state.nodeCount : 0;

  return (
    <div className="tj-page">
      <PageHeader
        eyebrow="P1 / OPERATIONS OVERVIEW"
        title="系统健康总览"
        description="5 秒内回答三个问题：系统是否健康、SLA 是否达标、模型是否加载。"
      />
      {error ? (
        <Alert type="error" content={`后端控制面暂不可用：${error.message}`} />
      ) : null}
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <KpiCard
            title="系统健康"
            value={error ? "异常" : "正常"}
            trend={`${state.onlineNodes}/${state.nodeCount} 节点在线`}
            progress={onlineRatio}
            tone={error ? "red" : "green"}
          />
        </Col>
        <Col span={6}>
          <KpiCard title="SLA 达标率" value={(state.slaRate * 100).toFixed(1)} suffix="%" progress={state.slaRate} />
        </Col>
        <Col span={6}>
          <KpiCard title="模型状态" value={state.modelLoaded ? "Loaded" : state.model?.status ?? "Unknown"} trend={(state.model?.loaded_models ?? []).join(" / ") || "fallback"} tone="ink" />
        </Col>
        <Col span={6}>
          <KpiCard title="运行任务" value={state.runningTasks} trend={`${state.pendingTasks} 个等待调度`} tone="amber" />
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="tj-section-row">
        <Col span={12}>
          <Card title="SLA 与执行成功率" bordered={false} className="tj-panel">
            <SlaChart slaRate={state.slaRate} successRate={state.successRate} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="控制面摘要" bordered={false} className="tj-panel">
            <div className="tj-health-lines">
              <div><IconCheckCircle /> API 控制面 <Tag color="green">online</Tag></div>
              <div>{state.modelLoaded ? <IconCheckCircle /> : <IconExclamationCircle />} 模型运行时 <Tag color={state.modelLoaded ? "arcoblue" : "orangered"}>{state.model?.status ?? "unknown"}</Tag></div>
              <div>{state.llmEnabled ? <IconCheckCircle /> : <IconExclamationCircle />} Hermes LLM <Tag color={state.llmEnabled ? "green" : "gray"}>{state.llmEnabled ? "enabled" : "fallback"}</Tag></div>
            </div>
            <Space className="tj-score-strip" size={10}>
              <Tag>平均稳定时延 {num(report?.metrics?.average_stable_latency_ms, 1)} ms</Tag>
              <Tag>融合评分 {num(report?.metrics?.average_fusion_score, 3)}</Tag>
              <Tag>确定性置信 {pct(report?.metrics?.average_deterministic_confidence)}</Tag>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card title="最近调度决策" bordered={false} className="tj-panel tj-section-row">
        <List
          dataSource={decisions}
          render={(item) => (
            <List.Item>
              <List.Item.Meta
                title={`${item.task_id} -> ${item.node_id}`}
                description={`评分 ${num(item.total_score, 3)} / 成本 ${num(item.predicted_cost, 2)} / 区域 ${regionLabel(item.network_snapshot?.selected_node_region)}`}
              />
              <Typography.Text type="secondary">{item.explanation || "等待解释"}</Typography.Text>
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
