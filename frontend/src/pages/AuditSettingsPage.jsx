import { Card, Descriptions, Grid, List, Tag } from "@arco-design/web-react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { API_BASE } from "../services/api.js";
import { statusLabel } from "../utils/format.js";

const { Row, Col } = Grid;

export function AuditSettingsPage() {
  const { health, report, state } = useControlPlaneContext();
  const feedback = report?.user_feedback ?? [];
  const events = report?.recent_progress_events ?? [];

  return (
    <div className="tj-page tj-page-audit-settings page-standard">
      <PageHeader eyebrow="P6 / AUDIT & SETTINGS" title="审计与设置" description="第一版只读呈现运行配置、安全边界和近期事件。" />
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card title="运行配置" bordered={false} className="tj-panel">
            <Descriptions
              column={1}
              data={[
                { label: "API Base", value: API_BASE },
                { label: "CORS Origin", value: health?.cors_allow_origin ?? "TIANJUN_CORS_ALLOW_ORIGIN default: http://127.0.0.1:5173" },
                { label: "模型状态", value: statusLabel(state.model?.status ?? "unknown") },
                { label: "Hermes LLM", value: statusLabel(health?.chat_runtime?.llm?.enabled ? "enabled" : "fallback") },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="安全边界" bordered={false} className="tj-panel">
            <List
              dataSource={[
                "策略提交必须经过显式按钮确认",
                "聊天文本不能绕过正式下发保护",
                "库存事实仅来自节点注册、心跳和执行回写",
                "密钥使用本地配置或 .env，不进入仓库",
              ]}
              render={(item) => <List.Item><Tag color="green">guardrail</Tag>{item}</List.Item>}
            />
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]} className="tj-section-row">
        <Col span={12}>
          <Card title="近期进度事件" bordered={false} className="tj-panel">
            <List dataSource={events.slice().reverse().slice(0, 8)} render={(item) => <List.Item>{item.task_id ?? "-"} / {item.stage ?? "-"} / {statusLabel(item.status ?? "-")}</List.Item>} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="用户反馈" bordered={false} className="tj-panel">
            <List dataSource={feedback.slice().reverse().slice(0, 8)} render={(item) => <List.Item>{item.policy_id}: {item.instruction}</List.Item>} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
