import { IconCheckCircleFill, IconClockCircle, IconCloseCircleFill, IconLoading } from "@arco-design/web-react/icon";

function statusIcon(status) {
  if (status === "done") return <IconCheckCircleFill />;
  if (status === "error") return <IconCloseCircleFill />;
  if (status === "running") return <IconLoading />;
  return <IconClockCircle />;
}

function defaultSteps() {
  return [
    { id: "intent", label: "意图理解", status: "idle", summary: "等待需求输入" },
    { id: "policy", label: "生成策略", status: "idle", summary: "等待调度草案" },
    { id: "simulation", label: "策略仿真", status: "idle", summary: "等待结果校验" },
  ];
}

export function ToolTraceTimeline({ trace, streaming }) {
  const items = trace.length ? trace : defaultSteps();

  return (
    <div className="tj-ai-trace-card">
      {items.map((item) => (
        <div key={item.id} className={`tj-ai-trace-step ${item.status} ${streaming ? "is-streaming" : ""}`}>
          <span className="tj-ai-trace-icon">{statusIcon(item.status)}</span>
          <div>
            <b>{item.label}</b>
            {item.summary ? <p>{item.summary}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
