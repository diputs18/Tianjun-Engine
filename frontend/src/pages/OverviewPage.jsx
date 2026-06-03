import { Alert, Card, Empty, Tag } from "@arco-design/web-react";
import {
  IconCalendarClock,
  IconCheckCircle,
  IconCodeSandbox,
  IconCommand,
  IconDashboard,
  IconHeart,
  IconMindMapping,
} from "@arco-design/web-react/icon";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { SlaChart } from "../features/charts/SlaChart.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { num, pct, statusLabel } from "../utils/format.js";

function HeroMetric({ icon, title, value, detail, tone = "blue" }) {
  return (
    <div className={`tj-hero-metric tone-${tone}`}>
      <span className="tj-hero-icon">{icon}</span>
      <div>
        <label>{title}</label>
        <b>{value}</b>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function SummaryItem({ icon, title, tag, tagColor, detail }) {
  return (
    <div className="tj-summary-item">
      <span>{icon}</span>
      <div>
        <b>{title}</b>
        <Tag color={tagColor}>{tag}</Tag>
        {detail ? <p>{detail}</p> : null}
      </div>
    </div>
  );
}

export function OverviewPage() {
  const { error, report, state } = useControlPlaneContext();
  const decisions = (report?.recent_decisions ?? []).slice().reverse().slice(0, 5);

  return (
    <div className="tj-page tj-overview-page page-standard">
      <PageHeader eyebrow="P1 / OPERATIONS OVERVIEW" title="系统健康总览" />
      {error ? <Alert type="error" content={`后端控制面暂不可用：${error.message}`} /> : null}

      <div className="tj-overview-grid">
        <HeroMetric
          icon={<IconHeart />}
          title="系统健康"
          value={error ? "异常" : "正常"}
          detail={`${state.onlineNodes}/${state.nodeCount} 节点在线`}
          tone="green"
        />

        <HeroMetric
          icon={<IconDashboard />}
          title="SLA 达标率"
          value={`${(state.slaRate * 100).toFixed(1)}%`}
          detail="过去 24h 服务目标"
          tone="blue"
        />

        <HeroMetric
          icon={<IconMindMapping />}
          title="模型状态"
          value={state.modelLoaded ? statusLabel("loaded") : statusLabel(state.model?.status ?? "unknown")}
          detail={(state.model?.loaded_models ?? []).join(" / ") || "lstm / gnn"}
          tone="purple"
        />

        <Card bordered={false} className="tj-panel tj-task-card tj-overview-task">
          <div>
            <h3>运行任务</h3>
            <strong>{state.runningTasks}</strong>
            <p>{state.pendingTasks} 个等待调度</p>
          </div>
          <IconCalendarClock />
        </Card>

        <Card title="SLA 与执行成功率" bordered={false} className="tj-panel tj-chart-card tj-overview-chart">
          <SlaChart slaRate={state.slaRate} successRate={state.successRate} />
        </Card>

        <Card title="控制面摘要" bordered={false} className="tj-panel tj-summary-card tj-overview-summary">
          <div className="tj-summary-top">
            <SummaryItem icon={<IconCodeSandbox />} title="API 控制面" tag={statusLabel("online")} tagColor="green" />
            <SummaryItem icon={<IconMindMapping />} title="模型运行时" tag={state.modelLoaded ? statusLabel("loaded") : statusLabel("fallback")} tagColor={state.modelLoaded ? "purple" : "orangered"} detail="Hermes LLM" />
            <SummaryItem icon={<IconCommand />} title="调度引擎" tag={statusLabel("enabled")} tagColor="arcoblue" />
          </div>
          <div className="tj-summary-metrics">
            <div><span>平均稳定时延</span><b>{num(report?.metrics?.average_stable_latency_ms, 1)} ms</b></div>
            <div><span>融合评分</span><b>{num(report?.metrics?.average_fusion_score, 3)}</b></div>
            <div><span>确定性置信</span><b>{pct(report?.metrics?.average_deterministic_confidence)}</b></div>
          </div>
        </Card>

        <Card title="最近调度决策" bordered={false} className="tj-panel tj-decisions-card tj-overview-decisions">
          {decisions.length ? (
            <div className="tj-decision-list-modern">
              {decisions.map((item) => (
                <div key={`${item.task_id}-${item.node_id}`}>
                  <IconCheckCircle />
                  <b>{item.task_id} → {item.node_id}</b>
                  <span>评分 {num(item.total_score, 3)} / 成本 {num(item.predicted_cost, 2)}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="暂无数据" />
          )}
        </Card>
      </div>
    </div>
  );
}
