import { Card, Grid, Progress, Table, Tag } from "@arco-design/web-react";
import { EmptyState } from "../features/common/EmptyState.jsx";
import { KpiCard } from "../features/common/KpiCard.jsx";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";

const { Row, Col } = Grid;

export function WorkloadsPage() {
  const { report, state } = useControlPlaneContext();
  const pending = report?.pending_task_queue ?? [];
  const active = report?.active_runs ?? [];
  const records = report?.recent_records ?? [];
  const rows = [
    ...pending.map((task) => ({ key: `pending-${task.task_id}`, task_id: task.task_id, type: task.task_type, status: "pending", node: "-", progress: 0 })),
    ...active.map((run) => ({ key: `active-${run.task_id}-${run.node_id ?? "unassigned"}`, task_id: run.task_id, type: run.task?.task_type, status: run.status, node: run.node_id, progress: Number(run.progress ?? 0) })),
    ...records.map((record) => ({ key: `record-${record.task_id}-${record.node_id ?? "unknown"}`, task_id: record.task_id, type: record.task_type ?? "record", status: record.success ? "succeeded" : "failed", node: record.node_id, progress: 1 })),
  ];

  return (
    <div className="tj-page">
      <PageHeader eyebrow="P3 / WORKLOADS" title="任务执行" description="面向企业操作员的任务队列、运行态与历史执行结果。" />
      <Row gutter={[16, 16]}>
        <Col span={6}><KpiCard title="任务总数" value={state.totals.tasks ?? 0} /></Col>
        <Col span={6}><KpiCard title="等待调度" value={state.pendingTasks} tone="amber" /></Col>
        <Col span={6}><KpiCard title="运行中" value={state.runningTasks} tone="blue" /></Col>
        <Col span={6}><KpiCard title="执行成功率" value={(state.successRate * 100).toFixed(1)} suffix="%" progress={state.successRate} tone="green" /></Col>
      </Row>
      <Card title="任务管理" bordered={false} className="tj-panel tj-section-row">
        {rows.length ? (
          <Table
            rowKey="key"
            data={rows}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "任务 ID", dataIndex: "task_id" },
              { title: "类型", dataIndex: "type" },
              { title: "节点", dataIndex: "node" },
              {
                title: "状态",
                dataIndex: "status",
                render: (status) => <Tag color={status === "failed" ? "red" : status === "succeeded" ? "green" : status === "running" ? "arcoblue" : "orange"}>{status}</Tag>,
              },
              {
                title: "进度",
                dataIndex: "progress",
                render: (value) => <Progress percent={Math.round(Number(value ?? 0) * 100)} size="small" />,
              },
            ]}
          />
        ) : (
          <EmptyState description="暂无任务。启动 sim-backend 或提交策略后会出现任务。" />
        )}
      </Card>
    </div>
  );
}
