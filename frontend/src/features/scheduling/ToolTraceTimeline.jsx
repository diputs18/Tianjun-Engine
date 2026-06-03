import { Tag } from "@arco-design/web-react";

const colors = {
  done: "green",
  error: "red",
  running: "arcoblue",
};

function statusLabel(status) {
  if (status === "done") return "完成";
  if (status === "running") return "运行中";
  if (status === "error") return "异常";
  return "空闲";
}

export function ToolTraceTimeline({ trace }) {
  const items = trace.length ? trace : [{ id: "idle", label: "等待中", status: "idle", summary: "还没有工具调用" }];
  return (
    <div className="tj-ai-trace">
      {items.map((item) => (
        <div key={item.id} className={`tj-ai-trace-item ${item.status}`}>
          <Tag color={colors[item.status] ?? "gray"}>{statusLabel(item.status)}</Tag>
          <b>{item.label}</b>
          <span>{item.summary}</span>
        </div>
      ))}
    </div>
  );
}
