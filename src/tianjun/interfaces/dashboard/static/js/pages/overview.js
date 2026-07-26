import { cancelTaskRun } from "../api.js";
import { emit, state } from "../state.js";
import { activeDecision, decisionScore, displayKey, displayRegion, escapeHtml, fmt, gnnDisplayState, pct } from "../utils.js";

const DC_ORDER = ["dc1", "dc2", "dc3"];

export function initOverview() {
  document.getElementById("page-overview").innerHTML = `
    <header class="page-head">
      <div>
        <h1 class="page-title">资源调度总览</h1>
        <p class="page-subtitle">资源容量、实时队列、SLA 风险与最近调度决策。</p>
      </div>
    </header>
    <section id="overviewMetrics" class="overview-metrics" aria-label="核心调度指标"></section>
    <section class="grid overview-engine">
      <article class="card capacity-card">
        <h2 class="card-title title-primary">资源池</h2>
        <div id="capacityMatrix" class="capacity-matrix"></div>
      </article>
      <article class="card queue-card">
        <h2 class="card-title title-primary">实时调度队列</h2>
        <div id="realtimeQueue" class="queue-columns"></div>
      </article>
    </section>
    <section class="grid overview-bottom">
      <article class="card decision-wide">
        <h2 class="card-title title-primary">最近决策列表</h2>
        <div id="overviewDecision" class="list"></div>
      </article>
      <aside id="slaAlertCard" class="card sla-alert-card" role="button" tabindex="0" aria-label="跳转任务执行页查看 SLA 未达标任务"></aside>
    </section>`;

  const jump = () => {
    location.hash = "tasks";
  };
  document.getElementById("slaAlertCard").addEventListener("click", jump);
  document.getElementById("slaAlertCard").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") jump();
  });
  document.getElementById("realtimeQueue").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-cancel-run]");
    if (!button || button.disabled) return;
    button.disabled = true;
    button.textContent = "释放中";
    try {
      await cancelTaskRun(button.dataset.cancelRun);
      emit("report:refresh");
    } catch (error) {
      button.disabled = false;
      button.textContent = "失败";
      button.title = error.message;
      setTimeout(() => {
        button.textContent = "释放";
      }, 1600);
    }
  });
}

export function renderOverview(report, health) {
  if (!report) {
    renderOverviewLoading();
    return;
  }
  renderMetrics(report);
  renderCapacity(report);
  renderQueue(report);
  renderRecent(report, health);
  renderSlaAlert(report);
}

function renderOverviewLoading() {
  document.getElementById("overviewMetrics").innerHTML = `
    <article class="card metric-summary-panel loading-card">
      <div class="metric-summary-grid">
        ${Array.from({ length: 4 }, () => `
          <section class="metric-summary-group">
            <span class="summary-eyebrow">加载中</span>
            <strong class="summary-value">--</strong>
            <span class="summary-caption">正在获取调度数据</span>
          </section>`).join("")}
      </div>
    </article>`;
  document.getElementById("capacityMatrix").innerHTML = `<div class="empty">资源池数据加载中...</div>`;
  document.getElementById("realtimeQueue").innerHTML = `<div class="empty">实时调度队列加载中...</div>`;
  document.getElementById("overviewDecision").innerHTML = `<div class="empty">最近决策加载中...</div>`;
  document.getElementById("slaAlertCard").innerHTML = `
    <span class="metric-label">SLA 未达标任务</span>
    <strong class="sla-alert-number">--</strong>
    <p>正在获取任务执行与 SLA 校验结果。</p>`;
}

function renderMetrics(report) {
  const metrics = report.metrics ?? {};
  const totals = report.totals ?? {};
  const decision = activeDecision(report, state.intentPayload);
  const snap = decision?.network_snapshot ?? {};
  const gnnValue = metrics.gnn_stability_score ?? snap.fusion_features?.gnn_topology ?? report.model_runtime?.latest_prediction?.gnn_stability_score;
  const batches = report.batch_scheduling ?? {};
  const nodes = report.nodes ?? [];
  const onlineNodes = nodes.filter((node) => node.online !== false).length;
  const averageResource = (key) => nodes.length
    ? nodes.reduce((sum, node) => sum + resourceValue(node, key), 0) / nodes.length
    : 0;
  const gpuSummary = gpuCapacitySummary(nodes);
  const gpuUtilization = typeof gpuSummary === "number" ? gpuSummary : Number(gpuSummary.value ?? 0);
  const managedTasks = Number(totals.tasks ?? batches.total_batch_tasks ?? 0);
  const latencyValue = metrics.average_stable_latency_ms ?? snap.deterministic_latency_ms;
  const fusionValue = metrics.average_fusion_score ?? snap.feature_fusion_score ?? (decision ? decisionScore(decision) : undefined);
  const acceptanceValue = batches.batch_acceptance_rate;
  const groups = [
    {
      tone: "primary",
      eyebrow: "资源状态",
      label: "在线节点",
      value: String(onlineNodes),
      unit: nodes.length ? `/ ${nodes.length}` : "",
      caption: "可参与当前资源分配",
      facts: [
        ["CPU", pct(averageResource("cpu"), 1)],
        ["内存", pct(averageResource("memory"), 1)],
        ["GPU", pct(gpuUtilization, 1)],
      ],
    },
    {
      tone: "teal",
      eyebrow: "工作负载",
      label: "纳管任务",
      value: String(managedTasks),
      unit: "",
      caption: acceptanceValue === undefined ? "接纳率等待批次数据" : `批任务接纳率 ${pct(acceptanceValue, 1)}`,
      facts: [
        ["待调度", fmt(totals.pending ?? totals.pending_tasks ?? 0, 0)],
        ["运行中", fmt(totals.running ?? totals.running_tasks ?? 0, 0)],
        ["已完成", fmt(totals.completed ?? totals.completed_attempts ?? 0, 0)],
      ],
    },
    {
      tone: "ink",
      eyebrow: "调度质量",
      label: "平均时延",
      value: latencyValue === undefined ? "--" : fmt(latencyValue, 1),
      unit: latencyValue === undefined ? "" : "ms",
      caption: decision ? `最近目标节点 ${decision.node_id}` : "等待首次调度决策",
      facts: [
        ["GNN 稳定性", gnnValue === undefined ? "--" : pct(gnnValue, 1)],
        ["融合评分", fusionValue === undefined ? "--" : fmt(fusionValue, 3)],
      ],
    },
    {
      tone: "success",
      eyebrow: "绿色运行",
      label: "运行碳",
      value: fmt(metrics.total_operational_carbon_g, 3),
      unit: "gCO₂e",
      caption: "仅统计运行阶段排放",
      facts: [
        ["能耗", `${fmt(metrics.total_energy_kwh, 5)} kWh`],
        ["口径", "Operational"],
      ],
    },
  ];
  document.getElementById("overviewMetrics").innerHTML = `
    <article class="card metric-summary-panel">
      <div class="metric-summary-grid">
        ${groups.map(renderSummaryGroup).join("")}
      </div>
    </article>`;
}

function renderSummaryGroup(group) {
  return `<section class="metric-summary-group tone-${escapeHtml(group.tone)}">
    <span class="summary-eyebrow">${escapeHtml(group.eyebrow)}</span>
    <div class="summary-primary-line">
      <strong class="summary-value">${escapeHtml(group.value)}</strong>
      ${group.unit ? `<span class="summary-unit">${escapeHtml(group.unit)}</span>` : ""}
    </div>
    <span class="summary-label">${escapeHtml(group.label)}</span>
    <span class="summary-caption">${escapeHtml(group.caption)}</span>
    <div class="summary-facts">
      ${group.facts.map(([label, value]) => `<span><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b></span>`).join("")}
    </div>
  </section>`;
}

function renderCapacity(report) {
  const groups = capacityByDc(report);
  document.getElementById("capacityMatrix").innerHTML = groups.map((dc) => `
    <article class="capacity-row">
      <div class="capacity-title">
        <b>${escapeHtml(dc.label)}</b>
        <span>${dc.nodes.length} 个节点 · ${displayRegion(dc.region)}</span>
      </div>
      ${renderCapacityMetric("CPU", dc.cpu)}
      ${renderCapacityMetric("内存", dc.memory)}
      ${renderCapacityMetric("GPU", dc.gpu)}
    </article>`).join("");
}

function renderCapacityMetric(label, metric) {
  const value = typeof metric === "number" ? metric : Number(metric?.value ?? 0);
  const unavailable = Boolean(metric?.unavailable);
  const tone = unavailable ? "unavailable" : value > 0.82 ? "danger" : value > 0.62 ? "warning" : "success";
  const text = metric?.text ?? pct(value, 0);
  const detail = metric?.detail ? `<small>${escapeHtml(metric.detail)}</small>` : "";
  const title = metric?.title ? ` title="${escapeHtml(metric.title)}"` : "";
  const barWidth = value <= 0 ? 0 : Math.max(4, Math.min(100, value * 100));
  return `<div class="capacity-metric ${tone}"${title}>
    <span class="capacity-label">${escapeHtml(label)}${detail}</span>
    <div class="capacity-track"><i style="width:${barWidth}%"></i></div>
    <b>${escapeHtml(text)}</b>
  </div>`;
}

function capacityByDc(report) {
  const nodes = report.nodes ?? [];
  const buckets = new Map();
  for (const node of nodes) {
    const key = dcKey(node);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(node);
  }
  return DC_ORDER.map((key) => {
    const nodesInDc = buckets.get(key) ?? [];
    const avg = (fn) => nodesInDc.reduce((sum, node) => sum + Number(fn(node) ?? 0), 0) / Math.max(1, nodesInDc.length);
    const region = nodesInDc[0]?.service_region ?? nodesInDc[0]?.region ?? nodesInDc[0]?.location ?? key;
    return {
      key,
      label: key.toUpperCase(),
      region,
      nodes: nodesInDc,
      cpu: avg((node) => resourceValue(node, "cpu")),
      memory: avg((node) => resourceValue(node, "memory")),
      gpu: gpuCapacitySummary(nodesInDc),
    };
  });
}

function dcKey(node) {
  const text = String(node.node_id ?? node.dc ?? node.datacenter ?? "").toLowerCase();
  const match = text.match(/dc[-_]?(\d+)/);
  return match ? `dc${match[1]}` : "dc1";
}

function resourceValue(node, key) {
  const direct = node.runtime_utilization?.[key] ?? node.runtime_telemetry?.[key] ?? node[`${key}_utilization`] ?? node[`${key}_used_ratio`] ?? node[`${key}_usage`];
  if (direct !== undefined && Number.isFinite(Number(direct))) return clamp01(Number(direct));
  const cap = resourceCapacity(node, key);
  const used = resourceUsed(node, key, cap);
  if (cap > 0 && used !== null) return clamp01(used / cap);
  if (key === "gpu") return 0;
  return key === "cpu" ? nodeLoadFallback(node) : nodeLoadFallback(node) * 0.82;
}

function gpuCapacitySummary(nodes) {
  const total = nodes.reduce((sum, node) => sum + resourceCapacity(node, "gpu"), 0);
  if (total <= 0) {
    const telemetryValues = nodes
      .map((node) => node.gpu_utilization ?? node.gpu_used_ratio ?? node.gpu_usage)
      .filter((value) => value !== undefined && Number.isFinite(Number(value)))
      .map((value) => clamp01(Number(value)));
    if (telemetryValues.length) {
      const value = telemetryValues.reduce((sum, item) => sum + item, 0) / telemetryValues.length;
      return {
        value,
        text: pct(value, 0),
        detail: "遥测",
        title: "当前节点未注册 GPU 总量，使用遥测占用率展示。",
      };
    }
    return {
      value: 0,
      text: "无",
      detail: "0 / 0",
      unavailable: true,
      title: "该资源池暂未注册 GPU 容量。",
    };
  }

  const used = nodes.reduce((sum, node) => {
    const cap = resourceCapacity(node, "gpu");
    if (cap <= 0) return sum;
    const nodeUsed = resourceUsed(node, "gpu", cap);
    return sum + Math.max(0, nodeUsed ?? 0);
  }, 0);
  const value = clamp01(used / total);
  return {
    value,
    text: pct(value, 0),
    detail: `${fmt(used, 0)} / ${fmt(total, 0)}`,
    title: `GPU 已占用 ${fmt(used, 0)} / ${fmt(total, 0)}`,
  };
}

function resourceCapacity(node, key) {
  const raw = node.resources?.[key] ?? node.capacity?.[key] ?? 0;
  return Math.max(0, Number(raw) || 0);
}

function resourceUsed(node, key, cap) {
  const usedRaw = node.used_resources?.[key] ?? node.allocations?.[key];
  if (usedRaw !== undefined && Number.isFinite(Number(usedRaw))) return Math.max(0, Number(usedRaw));
  const availableRaw = node.available?.[key] ?? node.free_resources?.[key];
  if (availableRaw !== undefined && Number.isFinite(Number(availableRaw))) {
    return Math.max(0, cap - Number(availableRaw));
  }
  return null;
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function nodeLoadFallback(node) {
  const perf = node.performance_factors ?? {};
  const direct = node.load ?? node.current_load ?? perf.cpu_utilization ?? perf.memory_utilization;
  if (direct !== undefined) return Number(direct);
  const health = Number(node.health_score ?? 0.9);
  const latency = Number(node.stable_latency_ms ?? node.avg_latency_ms ?? node.network_paths?.[0]?.latency_ms ?? 2);
  return Math.max(0.08, Math.min(0.86, (1 - health) * 0.8 + latency / 18));
}

function renderQueue(report) {
  const statuses = report.task_statuses ?? {};
  const indexed = taskIndex(report);
  const groups = [
    ["pending", "等待调度", "等待进入控制面"],
    ["scheduling", "正在调度", "Hermes / 控制面生成策略"],
    ["running", "执行中", "节点侧资源占用中"],
  ].map(([key, label, hint]) => {
    const tasks = key === "running"
      ? (report.active_runs ?? []).map((run) => run.task_id)
      : Object.entries(statuses).filter(([, status]) => {
          if (key === "scheduling") return ["scheduling", "preview", "assigned"].includes(status);
          return status === key;
        }).map(([id]) => id);
    return { key, label, hint, tasks: Array.from(new Set(tasks)).slice(0, 4), count: tasks.length };
  });
  document.getElementById("realtimeQueue").innerHTML = groups.map((group) => `
    <article class="queue-column ${group.key}">
      <span>${escapeHtml(group.hint)}</span>
      <strong>${fmt(group.count, 0)}</strong>
      <b>${escapeHtml(group.label)}</b>
      <div class="queue-list">
        ${group.tasks.map((taskId) => renderQueueTask(group.key, taskId, indexed.get(taskId))).join("") || "<em>暂无代表任务</em>"}
      </div>
    </article>`).join("");
}

function renderQueueTask(groupKey, taskId, record) {
  const label = `${displayKey(record?.task_type ?? "task")} · ${taskId}`;
  const action = groupKey === "running"
    ? `<button class="queue-release-btn" type="button" data-cancel-run="${escapeHtml(taskId)}" title="释放该任务占用的节点资源">释放</button>`
    : "";
  return `<em><span>${escapeHtml(label)}</span>${action}</em>`;
}

function taskIndex(report) {
  const map = new Map();
  for (const item of report.recent_records ?? []) map.set(item.task_id, item);
  for (const item of report.recent_progress_events ?? []) map.set(item.task_id, { ...(map.get(item.task_id) ?? {}), ...item });
  for (const item of report.active_runs ?? []) map.set(item.task_id, { ...(map.get(item.task_id) ?? {}), ...(item.task ?? {}), ...item });
  return map;
}

function renderSlaAlert(report) {
  const totals = report.totals ?? {};
  const records = report.recent_records ?? [];
  const completed = Number(totals.completed ?? totals.completed_attempts ?? records.length);
  const slaMet = Number(totals.sla_met ?? records.filter((record) => record.sla_met === true).length);
  const slaMiss = Number(totals.sla_missed ?? totals.sla_unmet ?? Math.max(0, completed - slaMet));
  const card = document.getElementById("slaAlertCard");
  card.classList.toggle("has-alert", slaMiss > 0);
  card.classList.toggle("is-clear", slaMiss === 0);
  card.innerHTML = slaMiss > 0 ? `
    <span class="metric-label">SLA 未达标任务</span>
    <strong class="sla-alert-number">${fmt(slaMiss, 0)}</strong>
    <p>执行完成但未满足时延、成本或稳定性目标。点击进入任务执行页定位异常记录。</p>
    <b>查看任务执行 →</b>` : `
    <span class="metric-label">SLA 运行状态</span>
    <strong class="sla-alert-number">正常</strong>
    <p>${completed > 0 ? `${fmt(completed, 0)} 个已完成任务中暂无 SLA 异常。` : "等待任务完成后进行 SLA 校验。"}</p>
    <b>查看任务执行 →</b>`;
}

function renderRecent(report, health) {
  const issues = health?.issues ?? [];
  const decisions = (report.recent_decisions ?? []).slice().reverse();
  const rows = [
    ...issues.map((issue) => `<article class="list-item"><div class="item-row"><b>系统告警</b><span class="badge badge-danger">健康检查</span></div><p class="muted">${escapeHtml(issue)}</p></article>`),
    ...decisions.map((decision) => {
      const snap = decision.network_snapshot ?? {};
      const gnn = gnnDisplayState(snap, decision, report);
      return `<article class="list-item decision-rich">
        <div class="item-row"><b>${escapeHtml(decision.task_id ?? "-")} → ${escapeHtml(decision.node_id ?? "-")}</b><span class="badge badge-primary">后端决策</span></div>
        <div class="pill-row">
          <span class="badge badge-neutral">稳健时延 ${fmt(snap.deterministic_latency_ms ?? snap.stable_latency_ms, 1)} ms</span>
          <span class="badge badge-success">${escapeHtml(gnn.compact)}</span>
          <span class="badge badge-primary">融合评分 ${fmt(decisionScore(decision), 3)}</span>
        </div>
        <p class="muted"><b>推荐原因：</b>${escapeHtml(decision.explanation ?? "综合完成时效、网络质量、性能与可靠性后评分最高。")}</p>
      </article>`;
    }),
  ];
  document.getElementById("overviewDecision").innerHTML = rows.join("") || "<div class=\"empty\">暂无告警或调度决策。</div>";
}
