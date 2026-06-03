import { useEffect } from "react";
import { StatusHeader } from "./StatusHeader.jsx";
import { ChatPanel } from "./ChatPanel.jsx";
import { PolicyPanel } from "./PolicyPanel.jsx";
import { NodePanel } from "./NodePanel.jsx";
import { TaskPanel } from "./TaskPanel.jsx";
import { ReportPanel } from "./ReportPanel.jsx";

export function DashboardPage() {
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "/dashboardRuntime.js";
    script.async = false;
    document.body.appendChild(script);
    return () => {
      script.remove();
    };
  }, []);

  return (
    <main className="shell">
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
    </main>
  );
}
