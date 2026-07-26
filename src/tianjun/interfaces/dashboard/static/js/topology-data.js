export function loadSourceSummary(nodes) {
  return sourceLabel(nodes.map((node) => node.resource_load_source || "unavailable"), "load");
}

export function carbonSourceSummary(nodes) {
  return sourceLabel(nodes.map((node) => node.carbon_data_source || "configured_profile"), "carbon");
}

export function sourceLabel(rawKinds, layer) {
  const kinds = new Set(rawKinds.filter(Boolean));
  if (!kinds.size || (kinds.size === 1 && kinds.has("unavailable"))) return "暂无数据";
  kinds.delete("unavailable");
  if (kinds.size > 1) return "混合来源";
  const kind = Array.from(kinds)[0];
  const labels = layer === "carbon"
    ? {
        live_signal: "实时碳信号",
        simulated_signal: "CloudSim 模拟",
        simulated_profile: "模拟曲线",
        configured_profile: "配置曲线",
      }
    : {
        live_telemetry: "实时遥测",
        simulated_telemetry: "CloudSim 模拟",
        task_progress_estimate: "进度估算",
        allocation_estimate: "分配估算",
      };
  return labels[kind] || "来源未标注";
}
