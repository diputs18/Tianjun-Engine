import { Card } from "@arco-design/web-react";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { SchedulingConsole } from "../features/scheduling/SchedulingConsole.jsx";

export function SchedulingPage() {
  return (
    <div className="tj-page tj-page-scheduling">
      <PageHeader
        eyebrow="P2 / AI SCHEDULING WORKBENCH"
        title="Scheduling Workbench"
        description="AI dialogue, policy draft, tool trace, simulation result, and explicit commit protection are handled in React state."
      />
      <Card bordered={false} className="tj-ai-card">
        <SchedulingConsole />
      </Card>
    </div>
  );
}
