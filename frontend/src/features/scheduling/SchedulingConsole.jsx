import { useEffect } from "react";
import { ChatPanel } from "./legacy/ChatPanel.jsx";
import { NodePanel } from "./legacy/NodePanel.jsx";
import { PolicyPanel } from "./legacy/PolicyPanel.jsx";
import { ReportPanel } from "./legacy/ReportPanel.jsx";
import { StatusHeader } from "./legacy/StatusHeader.jsx";
import { TaskPanel } from "./legacy/TaskPanel.jsx";

export function SchedulingConsole() {
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "/dashboardRuntime.js";
    script.async = false;
    document.body.appendChild(script);
    return () => script.remove();
  }, []);

  return (
    <div className="tj-scheduling-console">
      <StatusHeader />
      <section className="conversation-stage">
        <div className="interaction-stack">
          <ChatPanel />
          <PolicyPanel />
        </div>
      </section>
      <NodePanel />
      <section className="bottom-grid">
        <TaskPanel />
        <ReportPanel />
      </section>
    </div>
  );
}
