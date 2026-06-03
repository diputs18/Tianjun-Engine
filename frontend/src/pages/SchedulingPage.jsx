import { Card } from "@arco-design/web-react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { SchedulingConsole } from "../features/scheduling/SchedulingConsole.jsx";

export function SchedulingPage() {
  return (
    <div className="tj-page tj-page-scheduling">
      <PageHeader
        eyebrow="P2 / SCHEDULING WORKBENCH"
        title="调度工作台"
      />
      <Card bordered={false} className="tj-ai-card">
        <SchedulingConsole />
      </Card>
    </div>
  );
}
