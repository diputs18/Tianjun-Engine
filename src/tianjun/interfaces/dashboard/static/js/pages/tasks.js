import { compactText, displayKey, escapeHtml, fmt, pct, statusText } from "../utils.js";

const pipelineSteps = [
  ["接收任务", "请求进入调度队列"],
  ["策略决策", "Hermes 生成调度意图"],
  ["节点分配", "控制面绑定目标节点"],
  ["镜像拉取", "执行环境准备"],
  ["执行完成", "任务进程结束"],
  ["SLA 校验", "性能目标复核"],
];

const filters = [
  ["all", "全部"],
  ["sla_miss", "SLA 未达标"],
  ["success", "执行成功"],
  ["failed", "执行失败"],
  ["inference", "推理任务"],
  ["analytics", "分析任务"],
  ["batch_cpu", "CPU 批处理"],
];

let activeFilter = "all";
let lastReport = null;
const expandedRecords = new Set();

export function initTasks() {
  document.getElementById("page-tasks").innerHTML = `
    <header class="page-head">
      <div>
        <h1 class="page-title">任务执行</h1>
        <p class="page-subtitle">执行记录、资源消耗与 SLA 异常定位。</p>
      </div>
    </header>
    <section id="taskSummary" class="task-summary" aria-label="任务执行概览"></section>
    <details class="card task-pipeline-card">
      <summary class="pipeline-summary">查看执行阶段</summary>
      <div id="taskPipeline" class="pipeline"></div>
    </details>
    <article class="card records-card-panel">
      <h2 class="card-title title-warning">执行记录</h2>
      <p class="explain sla-note">执行成功表示任务进程已完成；SLA 未达标表示任务完成后仍未满足截止时间、预算或稳定性目标。</p>
      <nav id="taskFilters" class="filter-row" aria-label="执行记录筛选"></nav>
      <div id="taskRecords" class="records-table"></div>
    </article>`;

  const filterEl = document.getElementById("taskFilters");
  filterEl.innerHTML = filters.map(([key, label]) => `<button class="filter-btn ${key === activeFilter ? "active" : ""}" data-filter="${key}" type="button">${escapeHtml(label)}</button>`).join("");
  filterEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    activeFilter = button.dataset.filter;
    filterEl.querySelectorAll(".filter-btn").forEach((item) => item.classList.toggle("active", item.dataset.filter === activeFilter));
    renderRecords(lastReport);
  });

  document.getElementById("taskRecords").addEventListener("click", (event) => {
    const button = event.target.closest("[data-record-detail]");
    if (!button) return;
    const taskId = button.dataset.recordDetail;
    if (expandedRecords.has(taskId)) {
      expandedRecords.delete(taskId);
    } else {
      expandedRecords.add(taskId);
    }
    renderRecords(lastReport);
  });
  document.getElementById("taskSummary").addEventListener("click", (event) => {
    const button = event.target.closest("[data-summary-filter]");
    if (!button) return;
    activeFilter = button.dataset.summaryFilter;
    filterEl.querySelectorAll(".filter-btn").forEach((item) => item.classList.toggle("active", item.dataset.filter === activeFilter));
    renderRecords(lastReport);
    document.querySelector(".records-card-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

export function renderTasks(report) {
  if (!report) {
    renderTasksLoading();
    return;
  }
  lastReport = report;
  renderSummary(report);
  renderPipeline(report);
  renderRecords(report);
}

function renderTasksLoading() {
  document.getElementById("taskSummary").innerHTML = `
    <article class="card metric-summary-panel loading-card">
      <div class="metric-summary-grid">
        ${Array.from({ length: 4 }, () => `
          <section class="metric-summary-group">
            <span class="summary-eyebrow">加载中</span>
            <strong class="summary-value">--</strong>
            <span class="summary-caption">正在获取执行数据</span>
          </section>`).join("")}
      </div>
    </article>`;
  document.getElementById("taskPipeline").innerHTML = `<div class="empty">执行阶段加载中...</div>`;
  document.getElementById("taskRecords").innerHTML = `<div class="empty">任务执行记录加载中...</div>`;
}

function renderSummary(report) {
  const stats = taskStats(report);
  const metrics = report.metrics ?? {};
  const completed = stats.succeeded + stats.failed;
  const slaChecked = stats.slaMet + stats.slaMiss;
  const hasMeasuredRun = Number(metrics.completed_batch_count ?? 0) > 0 || Number(metrics.average_actual_jct_seconds ?? 0) > 0;
  const slaRate = slaChecked > 0 ? pct(stats.slaMet / slaChecked, 1) : "--";
  const backlogThreshold = Math.max(5, Math.ceil(stats.total * 0.1));
  const groups = [
    {
      tone: stats.failed > 0 ? "danger" : "primary",
      eyebrow: "执行状态",
      label: "已完成 / 总任务",
      value: `${completed} / ${stats.total}`,
      unit: "",
      caption: stats.failed > 0 ? `${stats.failed} 个任务执行异常` : "当前执行链路正常",
      facts: [["待调度", stats.pending], ["运行中", stats.running], ["失败", stats.failed]],
    },
    {
      tone: stats.slaMiss > 0 ? "danger" : "success",
      eyebrow: "服务目标",
      label: "SLA 达标率",
      value: slaRate,
      unit: "",
      caption: slaChecked > 0 ? `${slaChecked} 个已完成任务完成校验` : "等待任务完成后校验",
      facts: [["达标", stats.slaMet], ["未达标", stats.slaMiss]],
    },
    {
      tone: "ink",
      eyebrow: "执行性能",
      label: "实际平均 JCT",
      value: hasMeasuredRun ? fmt(metrics.average_actual_jct_seconds, 2) : "--",
      unit: hasMeasuredRun ? "s" : "",
      caption: hasMeasuredRun ? `P95 ${fmt(metrics.p95_actual_jct_seconds, 2)} s` : "等待 Cloudlet 指标回传",
      facts: [
        ["Makespan", hasMeasuredRun ? `${fmt(metrics.actual_makespan_seconds, 2)} s` : "--"],
        ["平均耗时", stats.avgDuration ? `${fmt(stats.avgDuration, 1)} ticks` : "--"],
      ],
    },
    {
      tone: "teal",
      eyebrow: "资源成本",
      label: "CPU 利用率",
      value: pct(metrics.average_cpu_utilization ?? 0, 1),
      unit: "",
      caption: `内存利用率 ${pct(metrics.average_memory_utilization ?? 0, 1)}`,
      facts: [
        ["能耗", `${fmt(metrics.total_energy_kwh, 5)} kWh`],
        ["运行碳", `${fmt(metrics.total_operational_carbon_g, 3)} gCO₂e`],
      ],
    },
  ];
  const alerts = [];
  if (stats.failed > 0) alerts.push(`<button type="button" data-summary-filter="failed"><b>${stats.failed} 个任务执行失败</b><span>查看失败记录 →</span></button>`);
  if (stats.slaMiss > 0) alerts.push(`<button type="button" data-summary-filter="sla_miss"><b>${stats.slaMiss} 个任务 SLA 未达标</b><span>定位异常任务 →</span></button>`);
  if (stats.pending > backlogThreshold) alerts.push(`<span><b>${stats.pending} 个任务积压</b><small>已超过提示阈值 ${backlogThreshold}</small></span>`);
  document.getElementById("taskSummary").innerHTML = `
    <article class="card metric-summary-panel">
      <div class="metric-summary-grid">
        ${groups.map(renderTaskSummaryGroup).join("")}
      </div>
      ${alerts.length ? `<div class="summary-alerts" role="alert">${alerts.join("")}</div>` : ""}
    </article>`;
}

function renderTaskSummaryGroup(group) {
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

function renderPipeline(report) {
  const stats = taskStats(report);
  const avg = stats.avgDuration || 1;
  const data = [
    [0, stats.total, 0, 0.4],
    [0, stats.total - stats.pending, 0, 0.8],
    [stats.running, stats.succeeded + stats.failed, stats.failed, 1.1],
    [stats.running, stats.succeeded + stats.failed, stats.failed, Math.max(1.2, avg * 0.18)],
    [stats.running, stats.succeeded, stats.failed, Math.max(1.8, avg * 0.62)],
    [0, stats.slaMet, stats.slaMiss, Math.max(0.2, avg * 0.08)],
  ];
  document.getElementById("taskPipeline").innerHTML = pipelineSteps.map(([title, sub], index) => {
    const [current, done, abnormal, duration] = data[index];
    return `<section class="pipeline-step">
      <div class="step-marker">${index + 1}</div>
      <div class="step-body">
        <b>${escapeHtml(title)}</b>
        <span>${escapeHtml(sub)}</span>
        <div class="step-metrics">
          <em>当前 ${fmt(current, 0)}</em>
          <em>完成 ${fmt(done, 0)}</em>
          <em>异常 ${fmt(abnormal, 0)}</em>
          <em>均时 ${fmt(duration, 1)} ticks</em>
        </div>
      </div>
    </section>`;
  }).join("");
}

function renderRecords(report) {
  if (!report) {
    renderTasksLoading();
    return;
  }
  const records = recordSource(report).slice().reverse().filter(matchFilter).slice(0, 50);
  document.getElementById("taskRecords").innerHTML = records.map((record) => {
    const sla = slaBadge(record);
    const exec = executionBadge(record);
    const duration = Number(record.actual_duration ?? record.duration_seconds ?? 0);
    const predicted = Number(record.predicted_duration ?? duration);
    const type = displayKey(record.task_type ?? record.type ?? "task");
    const cpuTicks = cpuTicksOf(record, duration);
    const taskId = String(record.task_id ?? "");
    const expanded = expandedRecords.has(taskId);
    return `<article class="record-card ${record.sla_met === false ? "sla-miss-row" : ""}">
      <div class="record-main">
        <div>
          <b>${escapeHtml(compactText(record.task_id, 44))}</b>
          <p class="muted">${escapeHtml(type)} · ${escapeHtml(record.node_id ?? "未分配节点")}${record.batch_id ? ` · 批次 ${escapeHtml(record.batch_id)}` : ""}</p>
        </div>
        <div class="record-badges">
          <span class="badge ${exec.cls}">${exec.text}</span>
          <span class="badge ${sla.cls}">${sla.text}</span>
        </div>
      </div>
      <div class="run-line" title="预测时长与实际执行时长对比"><span style="width:${timelineWidth(record)}%"></span></div>
      <div class="record-grid">
        <span><label>执行耗时</label><b>${fmt(duration, 1)} ticks</b></span>
        <span><label>预测耗时</label><b>${predicted ? `${fmt(predicted, 1)} ticks` : "--"}</b></span>
        <span><label>资源消耗</label><b>${fmt(cpuTicks, 1)} CPU ticks</b></span>
        <span><label>调度方式</label><b>${escapeHtml(statusText(record.execution_mode ?? record.mode ?? "process"))}</b></span>
        <span><label>SLA 原因</label><b>${escapeHtml(slaReason(record))}</b></span>
        <span><label>能耗 / 运行碳</label><b>${fmt(record.energy_kwh, 5)} kWh / ${fmt(record.operational_carbon_g, 3)} g</b></span>
        <span><label>排队 / JCT</label><b>${fmt(record.queue_wait_seconds, 2)} s / ${fmt(record.jct_seconds, 2)} s</b></span>
        <span><label>CPU / 内存利用率</label><b>${pct(record.cpu_utilization ?? 0, 1)} / ${pct(record.memory_utilization ?? 0, 1)}</b></span>
      </div>
      <button class="btn-ghost record-detail" type="button" data-record-detail="${escapeHtml(taskId)}" aria-expanded="${expanded ? "true" : "false"}">${expanded ? "收起详情" : "查看详情"}</button>
      ${expanded ? renderRecordDetails(record) : ""}
    </article>`;
  }).join("") || "<div class=\"empty\">当前筛选条件下暂无执行记录。</div>";
}

function renderRecordDetails(record) {
  const metadata = record.metadata && Object.keys(record.metadata).length
    ? Object.entries(record.metadata).slice(0, 8).map(([key, value]) => `${key}: ${formatDetailValue(value)}`).join("\n")
    : "无";
  const rows = [
    ["任务 ID", record.task_id],
    ["批次 ID", record.batch_id ?? record.metadata?.batch_id ?? "单任务"],
    ["节点", record.node_id],
    ["开始 / 结束 tick", `${record.start_tick ?? "--"} / ${record.end_tick ?? "--"}`],
    ["预测 / 实际耗时", `${fmt(record.predicted_duration, 1)} / ${fmt(record.actual_duration, 1)} ticks`],
    ["成本", record.cost === undefined ? "--" : fmt(record.cost, 4)],
    ["预算状态", budgetText(record.within_budget)],
    ["SLA 原因", slaReason(record)],
    ["执行失败原因", record.failure_reason || "无"],
    ["重试次数", record.retry_count ?? 0],
    ["网络时延", `${fmt(record.network_delay_ticks, 0)} ticks`],
    ["网络风险", fmt(record.network_risk, 4)],
    ["有效带宽", `${fmt(record.effective_bandwidth_mbps, 1)} Mbps`],
    ["计算碳 / 网络碳", `${fmt(record.compute_carbon_g, 4)} / ${fmt(record.network_carbon_g, 4)} gCO₂e`],
    ["碳核算范围", record.carbon_scope ?? "operational_only"],
    ["排队等待 / JCT", `${fmt(record.queue_wait_seconds, 3)} / ${fmt(record.jct_seconds, 3)} s`],
    ["CPU / 内存 / 带宽 / 存储利用率", `${pct(record.cpu_utilization ?? 0, 1)} / ${pct(record.memory_utilization ?? 0, 1)} / ${pct(record.bandwidth_utilization ?? 0, 1)} / ${pct(record.storage_utilization ?? 0, 1)}`],
    ["交付概率", record.delivery_probability === undefined ? "--" : `${fmt(Number(record.delivery_probability) * 100, 1)}%`],
  ];
  return `<section class="record-details" aria-label="任务详情">
    <div class="record-detail-grid">
      ${rows.map(([label, value]) => `<span><label>${escapeHtml(label)}</label><b>${escapeHtml(value)}</b></span>`).join("")}
    </div>
    <div class="record-log-grid">
      <pre><b>标准输出</b>${escapeHtml(record.stdout_excerpt || "无")}</pre>
      <pre><b>错误输出</b>${escapeHtml(record.stderr_excerpt || "无")}</pre>
      <pre><b>元数据</b>${escapeHtml(metadata)}</pre>
    </div>
  </section>`;
}

function budgetText(value) {
  if (value === true) return "预算内";
  if (value === false) return "超预算";
  return "未设置预算";
}

function slaReason(record) {
  if (record.sla_reason) return record.sla_reason;
  if (record.sla_met === true) return "SLA 达标";
  const reasons = [];
  if (record.end_tick !== undefined && record.predicted_duration !== undefined) {
    reasons.push(`完成耗时 ${fmt(record.actual_duration, 1)} ticks，预测 ${fmt(record.predicted_duration, 1)} ticks`);
  }
  if (record.within_budget === false) reasons.push("超出预算");
  if (record.failure_reason) reasons.push(record.failure_reason);
  return reasons.join("；") || "完成但未满足 SLA 目标";
}

function formatDetailValue(value) {
  if (value === null || value === undefined) return "无";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function taskStats(report) {
  const totals = report.totals ?? {};
  const records = recordSource(report);
  const total = Number(totals.tasks ?? Object.keys(report.task_statuses ?? {}).length ?? records.length);
  const failed = Number(totals.failed ?? records.filter((item) => item.success === false).length);
  const pending = Number(totals.pending ?? countStatus(report, "pending"));
  const running = Number(totals.running ?? countStatus(report, "running"));
  const succeeded = Number(totals.succeeded ?? totals.completed ?? Math.max(0, total - failed - pending - running));
  const slaMet = Number(totals.sla_met ?? records.filter((item) => item.sla_met === true).length);
  const slaMiss = Number(totals.sla_missed ?? totals.sla_unmet ?? Math.max(0, succeeded - slaMet));
  const avgDuration = average(records.map((item) => Number(item.actual_duration ?? item.duration_seconds ?? 0)).filter(Boolean));
  return { total, failed, pending, running, succeeded, slaMet, slaMiss, avgDuration };
}

function recordSource(report) {
  return report.execution_records ?? report.recent_records ?? [];
}

function cpuTicksOf(record, duration) {
  const demand = record.demand ?? record.resources ?? {};
  const cpu = Number(record.cpu_cores ?? demand.cpu ?? demand.cpu_cores ?? record.metadata?.cpu_cores ?? 1);
  return Math.max(0, cpu * Number(duration || 0));
}

function matchFilter(record) {
  if (activeFilter === "all") return true;
  if (activeFilter === "sla_miss") return record.sla_met === false;
  if (activeFilter === "success") return record.success === true;
  if (activeFilter === "failed") return record.success === false;
  return (record.task_type ?? record.type ?? "").includes(activeFilter);
}

function countStatus(report, status) {
  return Object.values(report.task_statuses ?? {}).filter((item) => item === status).length;
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function executionBadge(record) {
  if (record.success === true) return { cls: "badge-success", text: "执行成功" };
  if (record.success === false) return { cls: "badge-danger", text: "执行失败" };
  return { cls: "badge-primary", text: displayKey(record.status ?? "running") };
}

function slaBadge(record) {
  if (record.sla_met === true) return { cls: "badge-success", text: "SLA 达标" };
  if (record.sla_met === false) return { cls: "badge-danger", text: "SLA 未达标" };
  return { cls: "badge-neutral", text: "SLA 未上报" };
}

function timelineWidth(record) {
  const predicted = Number(record.predicted_duration ?? record.actual_duration ?? 1);
  const actual = Number(record.actual_duration ?? predicted);
  return Math.max(8, Math.min(100, (predicted / Math.max(predicted, actual)) * 100));
}
