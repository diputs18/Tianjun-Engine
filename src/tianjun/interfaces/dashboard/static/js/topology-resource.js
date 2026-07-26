export function latestBy(items, key) {
  return items.filter(Boolean).sort((a, b) => Number(a?.[key] ?? 0) - Number(b?.[key] ?? 0)).at(-1);
}

export function firstNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

export function percentFrom(...values) {
  const value = firstNumber(...values);
  if (value == null) return null;
  return Math.round(value <= 1 ? value * 100 : value);
}

export function ratioPercent(used, total) {
  const safeTotal = Number(total);
  if (!Number.isFinite(safeTotal) || safeTotal <= 0) return 0;
  return Math.round(Math.max(0, Number(used) || 0) / safeTotal * 100);
}

export function resourceUsed(node, key) {
  const capacity = Number(node?.capacity?.[key] ?? 0);
  const available = Number(node?.available?.[key] ?? capacity);
  return Math.max(0, capacity - available);
}

export function parseDciNode(nodeId = "", node = {}) {
  const match = String(nodeId).match(/^dci-dc(\d+)-([a-z]+)-vm-(\d+)$/i);
  const dcKey = match ? `dc${match[1]}` : String(node.region ?? "").match(/^dc\d+$/i)?.[0]?.toLowerCase();
  return {
    dcKey,
    location: String(match?.[2] ?? node.location ?? "").toLowerCase(),
    vmIndex: match ? Number(match[3]) : null,
  };
}

export function aggregateResources(nodes, scope) {
  const result = new Map();
  for (const node of nodes) {
    const parsed = parseDciNode(node.node_id, node);
    if (!parsed.dcKey || (scope === "zone" && !parsed.location)) continue;
    const key = scope === "zone" ? `${parsed.dcKey}:${parsed.location}` : parsed.dcKey;
    const bucket = result.get(key) ?? {
      nodes: 0,
      cpuUsed: 0,
      cpuTotal: 0,
      memoryUsed: 0,
      memoryTotal: 0,
      gpuUsed: 0,
      gpuTotal: 0,
      cpuTelemetry: 0,
      cpuSamples: 0,
      memoryTelemetry: 0,
      memorySamples: 0,
      gpuTelemetry: 0,
      gpuSamples: 0,
      tasks: 0,
    };
    bucket.nodes += 1;
    bucket.cpuTotal += Number(node?.capacity?.cpu ?? 0);
    bucket.cpuUsed += resourceUsed(node, "cpu");
    bucket.memoryTotal += Number(node?.capacity?.memory ?? 0);
    bucket.memoryUsed += resourceUsed(node, "memory");
    bucket.gpuTotal += Number(node?.capacity?.gpu ?? 0);
    bucket.gpuUsed += resourceUsed(node, "gpu");
    const cpuTelemetry = percentFrom(node.runtime_utilization?.cpu, node.runtime_telemetry?.cpu);
    const memoryTelemetry = percentFrom(node.runtime_utilization?.memory, node.runtime_telemetry?.memory);
    const gpuTelemetry = percentFrom(node.runtime_utilization?.gpu, node.runtime_telemetry?.gpu);
    if (cpuTelemetry != null) {
      bucket.cpuTelemetry += cpuTelemetry;
      bucket.cpuSamples += 1;
    }
    if (memoryTelemetry != null) {
      bucket.memoryTelemetry += memoryTelemetry;
      bucket.memorySamples += 1;
    }
    if (gpuTelemetry != null) {
      bucket.gpuTelemetry += gpuTelemetry;
      bucket.gpuSamples += 1;
    }
    bucket.tasks += node.active_task_ids?.length ?? (Array.isArray(node.running_tasks) ? node.running_tasks.length : 0);
    result.set(key, bucket);
  }
  for (const bucket of result.values()) {
    bucket.cpuPercent = bucket.cpuSamples ? Math.round(bucket.cpuTelemetry / bucket.cpuSamples) : ratioPercent(bucket.cpuUsed, bucket.cpuTotal);
    bucket.memoryPercent = bucket.memorySamples ? Math.round(bucket.memoryTelemetry / bucket.memorySamples) : ratioPercent(bucket.memoryUsed, bucket.memoryTotal);
    bucket.gpuUsed = Math.round(bucket.gpuUsed);
    bucket.gpuTotal = Math.round(bucket.gpuTotal);
    bucket.gpuPercent = bucket.gpuSamples ? Math.round(bucket.gpuTelemetry / bucket.gpuSamples) : ratioPercent(bucket.gpuUsed, bucket.gpuTotal);
  }
  return result;
}

export function firstOnlineNodeId(nodes) {
  return nodes.find((node) => node.online !== false)?.node_id ?? "";
}

export function zoneAggregate(nodes, report, metric) {
  const result = new Map();
  for (const node of nodes) {
    const parsed = parseDciNode(node.node_id, node);
    if (!parsed.location) continue;
    if (metric === "tasks") {
      const count = node.active_task_ids?.length ?? (Array.isArray(node.running_tasks) ? node.running_tasks.length : 0);
      result.set(parsed.location, (result.get(parsed.location) ?? 0) + count);
    } else if (metric === "cpu") {
      const value = percentFrom(node.runtime_utilization?.cpu, node.runtime_telemetry?.cpu, node.cpu_utilization, node.used_cpu_ratio);
      if (value != null) result.set(parsed.location, Math.max(result.get(parsed.location) ?? 0, value));
    } else if (metric === "memory") {
      const value = percentFrom(node.runtime_utilization?.memory, node.runtime_telemetry?.memory, node.memory_utilization, node.used_memory_ratio);
      if (value != null) result.set(parsed.location, Math.max(result.get(parsed.location) ?? 0, value));
    } else if (metric === "gpu") {
      const current = result.get(parsed.location) ?? { used: 0, total: 0, percent: 0 };
      current.used += resourceUsed(node, "gpu");
      current.total += Number(node?.capacity?.gpu ?? 0);
      current.used = Math.round(current.used);
      current.total = Math.round(current.total);
      current.percent = ratioPercent(current.used, current.total);
      result.set(parsed.location, current);
    }
  }
  for (const run of report?.active_runs ?? []) {
    const parsed = parseDciNode(run.node_id, {});
    if (parsed.location) result.set(parsed.location, Math.max(1, result.get(parsed.location) ?? 0));
  }
  return result;
}

export function normalizeGpu(value) {
  if (!value || typeof value !== "object") return { used: 0, total: 0, percent: 0 };
  const used = Math.round(Number(value.used ?? 0));
  const total = Math.round(Number(value.total ?? 0));
  return { used, total, percent: ratioPercent(used, total) };
}

export function gpuSummary(value) {
  if (value && typeof value === "object" && ("gpuUsed" in value || "gpuTotal" in value)) {
    const used = Math.round(Number(value.gpuUsed ?? 0));
    const total = Math.round(Number(value.gpuTotal ?? 0));
    return total > 0 ? `${used}/${total} (${ratioPercent(used, total)}%)` : "0/0";
  }
  const gpu = normalizeGpu(value?.gpu ?? value);
  return gpu.total > 0 ? `${gpu.used}/${gpu.total} (${gpu.percent}%)` : "0/0";
}

export function nodeName(leafId, location) {
  const suffix = leafId.endsWith("a") || leafId.endsWith("b") ? "1" : "2";
  return `Leaf-${String(location || "zone").toUpperCase()}-${suffix}`;
}
