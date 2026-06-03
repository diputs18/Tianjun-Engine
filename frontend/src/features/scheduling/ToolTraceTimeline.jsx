import { Tag } from "@arco-design/web-react";

const colors = {
  done: "green",
  error: "red",
  running: "arcoblue",
};

export function ToolTraceTimeline({ trace }) {
  const items = trace.length ? trace : [{ id: "idle", label: "Waiting", status: "idle", summary: "No tool calls yet" }];
  return (
    <div className="tj-ai-trace">
      {items.map((item) => (
        <div key={item.id} className={`tj-ai-trace-item ${item.status}`}>
          <Tag color={colors[item.status] ?? "gray"}>{item.status}</Tag>
          <b>{item.label}</b>
          <span>{item.summary}</span>
        </div>
      ))}
    </div>
  );
}
