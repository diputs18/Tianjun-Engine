import { Card } from "@arco-design/web-react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { SchedulingConsole } from "../features/scheduling/SchedulingConsole.jsx";

export function SchedulingPage() {
  return (
    <div className="tj-page tj-page-scheduling">
      <PageHeader
        eyebrow="P2 / 智能调度工作台"
        title="智能调度工作台"
        description="在 React 状态中统一承载 AI 对话、策略草案、工具轨迹、仿真结果和显式提交流程。"
      />
      <Card bordered={false} className="tj-ai-card">
        <SchedulingConsole />
      </Card>
    </div>
  );
}
