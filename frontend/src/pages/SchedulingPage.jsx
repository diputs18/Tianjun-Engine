import { Alert, Card } from "@arco-design/web-react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { SchedulingConsole } from "../features/scheduling/SchedulingConsole.jsx";

export function SchedulingPage() {
  return (
    <div className="tj-page tj-page-scheduling">
      <PageHeader
        eyebrow="P2 / AI SCHEDULING WORKBENCH"
        title="调度工作台"
        description="AI 对话、策略草案、仿真结果和正式下发保护集中在这里。"
      />
      <Alert
        className="tj-page-note"
        type="info"
        content="当前调度台保留原有 Hermes 流式对话能力，后续可继续把 runtime 内部逻辑拆成纯 React 状态。"
      />
      <Card bordered={false} className="tj-legacy-card">
        <SchedulingConsole />
      </Card>
    </div>
  );
}
