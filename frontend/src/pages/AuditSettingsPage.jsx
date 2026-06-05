import { Card, Empty, Tag } from "@arco-design/web-react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { useTheme } from "../theme/ThemeProvider.jsx";
import { API_BASE } from "../services/api.js";
import { statusLabel } from "../utils/format.js";

function ConfigTable({ rows }) {
  return (
    <div className="tj-audit-config-table">
      {rows.map((row) => (
        <div key={row.label} className="tj-audit-config-row">
          <div className="tj-audit-config-label">{row.label}</div>
          <div className="tj-audit-config-value">{row.value}</div>
        </div>
      ))}
    </div>
  );
}

function GuardrailList({ items }) {
  return (
    <div className="tj-audit-guardrail-list">
      {items.map((item) => (
        <div key={item} className="tj-audit-guardrail-item">
          <Tag color="purple">guardrail</Tag>
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

function EventList({ items }) {
  if (!items.length) {
    return (
      <div className="tj-audit-empty">
        <Empty description="暂无数据" />
      </div>
    );
  }

  return (
    <div className="tj-audit-event-list">
      {items.map((item, index) => (
        <div key={`${item.task_id ?? "event"}-${item.stage ?? "stage"}-${index}`} className="tj-audit-event-item">
          <Tag color="arcoblue">{item.stage ?? "event"}</Tag>
          <span>{item.task_id ?? "-"}</span>
          <em>{statusLabel(item.status ?? "-")}</em>
        </div>
      ))}
    </div>
  );
}

function FeedbackList({ items }) {
  if (!items.length) {
    return (
      <div className="tj-audit-empty">
        <Empty description="暂无数据" />
      </div>
    );
  }

  return (
    <div className="tj-audit-event-list">
      {items.map((item, index) => (
        <div key={`${item.policy_id ?? "feedback"}-${index}`} className="tj-audit-event-item">
          <Tag color="green">feedback</Tag>
          <span>{item.policy_id ?? "-"}</span>
          <em>{item.instruction ?? "-"}</em>
        </div>
      ))}
    </div>
  );
}

export function AuditSettingsPage() {
  const { health, report, state } = useControlPlaneContext();
  const { mode, theme } = useTheme();
  const feedback = report?.user_feedback ?? [];
  const events = report?.recent_progress_events ?? [];

  const configRows = [
    { label: "API Base", value: API_BASE },
    {
      label: "CORS Origin",
      value: health?.cors_allow_origin ?? "http://127.0.0.1:5173",
    },
    {
      label: "模型状态",
      value: statusLabel(state.model?.status ?? "unknown"),
    },
    {
      label: "Hermes LLM",
      value: statusLabel(health?.chat_runtime?.llm?.enabled ? "enabled" : "fallback"),
    },
    {
      label: "主题模式",
      value: mode === "system" ? "跟随系统" : mode === "dark" ? "暗色" : "浅色",
    },
    {
      label: "当前主题",
      value: theme,
    },
  ];

  const guardrails = [
    "策略提交必须经过显式按钮确认",
    "聊天文本不能绕过正式下发保护",
    "库存事实仅来自节点注册、心跳和执行回写",
    "密钥使用本地配置或 .env，不进入仓库",
  ];

  return (
    <div className="tj-page tj-page-audit-settings page-standard">
      <PageHeader
        eyebrow="P6 / AUDIT & SETTINGS"
        title="审计与设置"
        description="第一版只读呈现运行配置、安全边界和近期事件。"
      />

      <div className="tj-audit-grid">
        <Card title="运行配置" bordered={false} className="tj-panel tj-audit-card">
          <ConfigTable rows={configRows} />
        </Card>

        <Card title="安全边界" bordered={false} className="tj-panel tj-audit-card">
          <GuardrailList items={guardrails} />
        </Card>

        <Card title="近期进度事件" bordered={false} className="tj-panel tj-audit-card tj-audit-card-tall">
          <EventList items={events.slice().reverse().slice(0, 8)} />
        </Card>

        <Card title="用户反馈" bordered={false} className="tj-panel tj-audit-card tj-audit-card-tall">
          <FeedbackList items={feedback.slice().reverse().slice(0, 8)} />
        </Card>
      </div>
    </div>
  );
}
