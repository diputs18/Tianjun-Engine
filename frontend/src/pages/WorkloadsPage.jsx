import { Card, Grid, Progress, Table, Tag } from "@arco-design/web-react";
import {
  IconArrowRise,
  IconCalendar,
  IconClockCircle,
  IconPlayCircle,
} from "@arco-design/web-react/icon";
import { EmptyState } from "../features/common/EmptyState.jsx";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { statusLabel } from "../utils/format.js";

const { Row, Col } = Grid;

function WorkloadMetric({ title, value, suffix, icon, tone = "blue" }) {
  return (
    <Card className={`tj-workload-metric tone-${tone}`} bordered={false}>
      <div>
        <span>{title}</span>
        <b>
          {value}
          {suffix ? <em>{suffix}</em> : null}
        </b>
      </div>
      <span className="tj-workload-metric-icon">{icon}</span>
    </Card>
  );
}

function statusColor(status) {
  if (status === "failed") return "red";
  if (status === "succeeded") return "green";
  if (status === "running") return "arcoblue";
  return "orange";
}

export function WorkloadsPage() {
  const { report, state } = useControlPlaneContext();
  const pending = report?.pending_task_queue ?? [];
  const active = report?.active_runs ?? [];
  const records = report?.recent_records ?? [];

  const rows = [
    ...pending.map((task) => ({
      key: `pending-${task.task_id}`,
      task_id: task.task_id,
      type: task.task_type,
      status: "pending",
      node: "-",
      progress: 0,
    })),
    ...active.map((run) => ({
      key: `active-${run.task_id}-${run.node_id ?? "unassigned"}`,
      task_id: run.task_id,
      type: run.task?.task_type,
      status: run.status,
      node: run.node_id,
      progress: Number(run.progress ?? 0),
    })),
    ...records.map((record) => ({
      key: `record-${record.task_id}-${record.node_id ?? "unknown"}`,
      task_id: record.task_id,
      type: record.task_type ?? "record",
      status: record.success ? "succeeded" : "failed",
      node: record.node_id,
      progress: 1,
    })),
  ];

  return (
    <div className="tj-page tj-page-workloads page-wide">
      <PageHeader eyebrow="P3 / WORKLOADS" title="任务执行" />

      <div className="tj-workload-content">
        <Row gutter={[20, 20]} className="tj-workload-metric-row">
          <Col span={6}>
            <WorkloadMetric
              title="任务总数"
              value={state.totals.tasks ?? 0}
              icon={<IconCalendar />}
            />
          </Col>
          <Col span={6}>
            <WorkloadMetric
              title="等待调度"
              value={state.pendingTasks}
              icon={<IconClockCircle />}
              tone="blue"
            />
          </Col>
          <Col span={6}>
            <WorkloadMetric
              title="运行中"
              value={state.runningTasks}
              icon={<IconPlayCircle />}
              tone="green"
            />
          </Col>
          <Col span={6}>
            <WorkloadMetric
              title="执行成功率"
              value={(state.successRate * 100).toFixed(1)}
              suffix="%"
              icon={<IconArrowRise />}
              tone="green"
            />
          </Col>
        </Row>

        <Card title="任务管理" bordered={false} className="tj-panel tj-workload-table-card">
          {rows.length ? (
            <Table
              className="tj-workload-table"
              rowKey="key"
              data={rows}
              pagination={{ pageSize: 10, showTotal: true }}
              columns={[
                { title: "任务 ID", dataIndex: "task_id", width: 260 },
                { title: "类型", dataIndex: "type", width: 160 },
                { title: "节点", dataIndex: "node", width: 180 },
                {
                  title: "状态",
                  dataIndex: "status",
                  width: 160,
                  render: (status) => (
                    <Tag color={statusColor(status)}>{statusLabel(status)}</Tag>
                  ),
                },
                {
                  title: "进度",
                  dataIndex: "progress",
                  width: 260,
                  render: (value) => {
                    const percent = Math.round(Number(value ?? 0) * 100);
                    return (
                      <div className="tj-workload-progress">
                        <span>{percent}%</span>
                        <Progress percent={percent} showText={false} size="small" />
                      </div>
                    );
                  },
                },
              ]}
            />
          ) : (
            <EmptyState description="暂无任务。启动 sim-backend 或提交策略后会出现任务。" />
          )}
        </Card>
      </div>
    </div>
  );
}
