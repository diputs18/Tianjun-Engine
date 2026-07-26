import { updatePolicyWeights } from "../api.js";
import { emit, state } from "../state.js";
import { METRIC_KEYS, activeDecision, displayKey, escapeHtml, fmt, metricLabel, modelStatusText, pct, topWeights } from "../utils.js";

const defaultWeights = Object.fromEntries(METRIC_KEYS.map((key) => [key, 0.1]));
const GROUP_KEYS = ["sla_quality", "network_coordination", "resource_efficiency", "economic_cost", "green_carbon"];
const groupMeta = {
  sla_quality: ["SLA 与服务质量", "性能 / 完成时效 / 可靠性"],
  network_coordination: ["网络与地域协同", "网络质量 / 地域局部性"],
  resource_efficiency: ["资源效率", "负载均衡 / 未来可调度碎片"],
  economic_cost: ["经济成本", "任务执行成本"],
  green_carbon: ["绿色低碳", "运行碳排放"],
};
const defaultGroupWeights = { sla_quality: 0.3, network_coordination: 0.2, resource_efficiency: 0.18, economic_cost: 0.12, green_carbon: 0.2 };
const templates = {
  latency: ["低时延优先", { completion: 0.22, performance: 0.15, network: 0.15, reliability: 0.1, cost: 0.05, security: 0.05, balance: 0.08, fragmentation: 0.03, locality: 0.08, carbon: 0.09 }, { sla_quality: 0.5, network_coordination: 0.25, resource_efficiency: 0.1, economic_cost: 0.05, green_carbon: 0.1 }],
  cost: ["成本优先", { cost: 0.23, balance: 0.13, completion: 0.12, performance: 0.08, reliability: 0.06, network: 0.07, security: 0.05, fragmentation: 0.08, locality: 0.08, carbon: 0.1 }, { sla_quality: 0.25, network_coordination: 0.15, resource_efficiency: 0.15, economic_cost: 0.35, green_carbon: 0.1 }],
  stability: ["稳定性优先", { network: 0.2, reliability: 0.18, completion: 0.1, performance: 0.09, balance: 0.1, security: 0.08, cost: 0.05, fragmentation: 0.05, locality: 0.06, carbon: 0.09 }, { sla_quality: 0.45, network_coordination: 0.2, resource_efficiency: 0.15, economic_cost: 0.08, green_carbon: 0.12 }],
  security: ["安全优先", { security: 0.25, reliability: 0.15, network: 0.12, completion: 0.1, performance: 0.08, cost: 0.05, balance: 0.06, fragmentation: 0.04, locality: 0.06, carbon: 0.09 }, { ...defaultGroupWeights }],
  fragmentation: ["低碎片", { fragmentation: 0.25, balance: 0.16, performance: 0.1, completion: 0.1, cost: 0.06, reliability: 0.07, network: 0.06, locality: 0.05, security: 0.05, carbon: 0.1 }, { sla_quality: 0.25, network_coordination: 0.15, resource_efficiency: 0.35, economic_cost: 0.08, green_carbon: 0.17 }],
  green: ["绿色优先", { carbon: 0.3, completion: 0.12, performance: 0.08, network: 0.08, reliability: 0.09, cost: 0.07, security: 0.08, balance: 0.07, fragmentation: 0.07, locality: 0.04 }, { sla_quality: 0.2, network_coordination: 0.15, resource_efficiency: 0.15, economic_cost: 0.1, green_carbon: 0.4 }],
  balanced: ["均衡策略", { completion: 0.11, performance: 0.1, network: 0.11, reliability: 0.1, cost: 0.1, security: 0.1, balance: 0.1, fragmentation: 0.08, locality: 0.09, carbon: 0.11 }, { ...defaultGroupWeights }],
};

let draftWeights = {};
let draftGroupWeights = {};
let localTimeline = [];
let selectedTemplate = "";

export function initModel() {
  document.getElementById("page-model").innerHTML = `
    <header class="page-head">
      <div>
        <h1 class="page-title">模型配置</h1>
        <p class="page-subtitle">策略调整时间线、权重差值与调度影响预估。</p>
      </div>
    </header>
    <section class="grid model-layout">
      <article class="card model-left">
        <h2 class="card-title title-success">模型状态</h2>
        <div id="modelRuntime" class="details-grid"></div>
        <h2 class="card-title title-success model-section-title">策略调整时间线</h2>
        <div id="weightHistory" class="history-timeline"></div>
      </article>
      <article class="card model-right">
        <h2 class="card-title title-success">分层目标融合</h2>
        <p class="muted">先在五类业务目标内融合十维原子指标，再在目标组之间做 Pareto + Tchebycheff 排序；安全保留为硬约束与不可补偿风险惩罚。</p>
        <nav id="strategyTemplates" class="template-row" aria-label="策略模板"></nav>
        <section class="weight-source-panel" aria-label="权重来源分解">
          <h3>权重来源分解</h3>
          <div id="weightSourcePreview" class="weight-source-grid"></div>
        </section>
        <div id="groupWeightSliders" class="sliders group-sliders"></div>
        <details class="atomic-weight-details">
          <summary>十维原子指标（解释、单目标与双目标消融）</summary>
          <p class="muted">这里编辑组内意图权重。正式实验会分别运行单指标、双指标、单目标组、双目标组和完整分层融合。</p>
          <div id="weightSliders" class="sliders"></div>
        </details>
        <section class="impact-card">
          <h3>调整影响预估</h3>
          <div id="impactPreview" class="impact-grid"></div>
        </section>
        <div class="model-actions">
          <button id="previewWeights" class="btn-ghost">预览</button>
          <button id="commitWeights" class="btn-primary">提交</button>
        </div>
      </article>
    </section>`;

  document.getElementById("strategyTemplates").innerHTML = Object.entries(templates).map(([key, [label]]) => `<button class="template-btn" data-template="${key}" type="button">${escapeHtml(label)}</button>`).join("");
  document.getElementById("strategyTemplates").addEventListener("click", (event) => {
    const button = event.target.closest("[data-template]");
    if (!button) return;
    selectedTemplate = button.dataset.template;
    draftWeights = { ...templates[selectedTemplate][1] };
    draftGroupWeights = { ...templates[selectedTemplate][2] };
    renderModel(state.report, state.health);
  });
  document.getElementById("previewWeights").addEventListener("click", previewWeights);
  document.getElementById("commitWeights").addEventListener("click", () => void submitWeights());
}

export function renderModel(report, health) {
  if (!report) {
    renderModelLoading();
    return;
  }
  const runtime = report.model_runtime ?? health?.model_runtime ?? {};
  const decision = activeDecision(report, state.intentPayload);
  const snap = decision?.network_snapshot ?? {};
  const weights = currentWeights(report);
  const groupWeights = currentGroupWeights(report);
  document.getElementById("modelRuntime").innerHTML = [
    ["LSTM 时延预测", snap.model_prediction?.lstm_latency_ms !== undefined ? `${fmt(snap.model_prediction.lstm_latency_ms, 1)} ms` : modelStatusText(runtime)],
    ["GNN 拓扑稳定性", snap.fusion_features?.gnn_topology !== undefined ? pct(snap.fusion_features.gnn_topology, 1) : "--"],
    ["模型状态", modelStatusText(runtime)],
    ["当前策略", decision?.policy_id ?? state.hermesPolicyId ?? "--"],
  ].map(([k, v]) => `<div class="field"><label>${escapeHtml(k)}</label><b>${escapeHtml(v)}</b></div>`).join("");
  renderSliders(report, weights);
  renderGroupSliders(groupWeights);
  renderWeightSources(report);
  renderImpact(report, weights);
  renderHistory(report, runtime);
}

function renderModelLoading() {
  document.getElementById("modelRuntime").innerHTML = [
    ["LSTM 时延预测", "--"],
    ["GNN 拓扑稳定性", "--"],
    ["模型状态", "加载中"],
    ["当前策略", "--"],
  ].map(([k, v]) => `<div class="field"><label>${escapeHtml(k)}</label><b>${escapeHtml(v)}</b></div>`).join("");
  document.getElementById("weightHistory").innerHTML = `<div class="empty">策略调整时间线加载中...</div>`;
  document.getElementById("weightSliders").innerHTML = `<div class="empty">权重滑块加载中...</div>`;
  document.getElementById("groupWeightSliders").innerHTML = `<div class="empty">目标组权重加载中...</div>`;
  document.getElementById("weightSourcePreview").innerHTML = `<div class="empty">权重来源加载中...</div>`;
  document.getElementById("impactPreview").innerHTML = `<div class="empty">调整影响评估加载中...</div>`;
}

function renderWeightSources(report) {
  const sources = report?.group_weight_sources ?? {};
  const rows = [
    ["W_intent^G", sources.intent, "用户、Hermes 或批次级目标偏好"],
    ["W_SLA", sources.sla, "任务约束与紧迫度"],
    ["W_data", sources.data, sources.data_method ?? "固定历史窗口"],
    ["W_final", sources.final, "0.4 / 0.4 / 0.2 融合结果"],
  ];
  document.getElementById("weightSourcePreview").innerHTML = rows.map(([label, values, note]) => `
    <article class="weight-source-card">
      <div><b>${escapeHtml(label)}</b><small>${escapeHtml(note)}</small></div>
      <p>${values ? escapeHtml(formatTopGroupWeights(values)) : "--"}</p>
    </article>`).join("");
}

function renderGroupSliders(weights) {
  document.getElementById("groupWeightSliders").innerHTML = GROUP_KEYS.map((key) => {
    const [label, members] = groupMeta[key];
    const value = Number(weights[key] ?? 0);
    return `<label class="slider-row group-slider-row">
      <span>${escapeHtml(label)}<small>${escapeHtml(members)}</small></span>
      <input type="range" min="0" max="1" step="0.01" data-group-weight="${key}" value="${value}">
      <b>${pct(value, 0)}</b>
    </label>`;
  }).join("");
  document.querySelectorAll("[data-group-weight]").forEach((input) => input.addEventListener("input", () => {
    selectedTemplate = "";
    draftGroupWeights[input.dataset.groupWeight] = Number(input.value);
    renderModel(state.report, state.health);
  }));
}

function renderSliders(report, weights) {
  const previous = previousWeights(report);
  document.getElementById("strategyTemplates").querySelectorAll("[data-template]").forEach((button) => button.classList.toggle("active", button.dataset.template === selectedTemplate));
  document.getElementById("weightSliders").innerHTML = METRIC_KEYS.map((key) => {
    const value = Number(weights[key] ?? 0);
    const delta = value - Number(previous[key] ?? 0);
    return `<label class="slider-row">
      <span>${escapeHtml(metricLabel(key))}<small>${escapeHtml(displayKey(key))}</small></span>
      <input type="range" min="0" max="1" step="0.01" data-weight="${key}" value="${value}">
      <b>${pct(value, 0)} <em class="${delta >= 0 ? "up" : "down"}">${deltaText(delta)}</em></b>
    </label>`;
  }).join("");
  document.querySelectorAll("[data-weight]").forEach((input) => input.addEventListener("input", () => {
    selectedTemplate = "";
    draftWeights[input.dataset.weight] = Number(input.value);
    renderModel(state.report, state.health);
  }));
}

function renderImpact(report, weights) {
  const active = activeTaskCount(report);
  const batch = state.selectedBatchPlan || report?.batch_scheduling?.recent_batches?.at?.(-1)?.latest_plan;
  const impact = [
    ["预演运行碳", batch ? `${fmt(batch.predicted_carbon_g, 3)} gCO₂e` : "运行批次预演后生成"],
    ["预演能耗", batch ? `${fmt(batch.predicted_energy_kwh, 5)} kWh` : "运行批次预演后生成"],
    ["预演 SLA 违规", batch ? `${fmt(batch.predicted_sla_violations, 0)} 个任务` : "运行批次预演后生成"],
    ["影响活跃任务数", `${active} 条正在执行 / 调度中任务`],
  ];
  document.getElementById("impactPreview").innerHTML = impact.map(([label, value]) => `<div class="impact-item"><label>${escapeHtml(label)}</label><b>${escapeHtml(value)}</b></div>`).join("");
}

function renderHistory(report, runtime) {
  const source = report.adjustment_history ?? runtime.adjustment_history ?? report.policy_history ?? [];
  const normalized = normalizeHistory([...source, ...localTimeline]);
  const recent = normalized.slice(-5).reverse();
  document.getElementById("weightHistory").innerHTML = recent.map((item, index) => {
    const top = formatTopWeights(item.weights ?? {});
    const affected = item.affected_records ?? item.affected_tasks ?? 0;
    const metrics = adjustmentMetrics(item.metrics);
    const order = normalized.length - index;
    return `<article class="timeline-item">
      <div class="timeline-head"><b>调整 #${escapeHtml(order)} · tick ${escapeHtml(item.tick ?? "--")}</b><span class="badge badge-success">${escapeHtml(item.scope ?? "自动调整")}</span></div>
      <p>${escapeHtml(item.reason)}</p>
      <div class="timeline-detail"><span>调整内容</span><b>${escapeHtml(item.change)}</b></div>
      <div class="timeline-detail"><span>影响指标</span><b>${escapeHtml(top || item.impact || "暂无权重变化")}</b></div>
      ${metrics ? `<div class="timeline-detail"><span>观测指标</span><b>${escapeHtml(metrics)}</b></div>` : ""}
      <div class="timeline-detail impact-count"><span>依据样本</span><b>${fmt(affected, 0)} 条执行记录</b></div>
    </article>`;
  }).join("") || "<div class=\"empty\">暂无权重调整历史。</div>";
}

function normalizeHistory(items) {
  const result = [];
  const seen = new Set();
  for (const item of items) {
    const reason = translateReason(item);
    const weights = item.weights ?? {};
    const top = topWeights(weights, 3);
    const change = item.change ?? (top.length ? `当前最高权重：${top.map(([key]) => metricLabel(key)).join("、")}` : "保持当前策略权重");
    const fingerprint = `${item.tick ?? ""}:${reason}:${change}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    result.push({ ...item, reason, change, weights, impact: top.map(([key]) => metricLabel(key)).join("、") });
  }
  return result;
}

function translateReason(item) {
  const raw = Array.isArray(item.reasons) ? item.reasons.join("；") : item.reason ?? item.status ?? "";
  const text = String(raw).toLowerCase();
  if (text.includes("sla")) return "检测到 SLA 达标率下降，系统提高完成时效、性能与可靠性权重。";
  if (text.includes("cost")) return "检测到成本超预算，系统提高成本权重并降低跨区域调度倾向。";
  if (text.includes("load")) return "检测到集群负载不均衡，系统提高负载均衡权重。";
  if (text.includes("latency") || text.includes("delay")) return "检测到稳健时延波动，系统提高完成时效与网络质量权重。";
  return raw || "控制面根据最近任务回放结果完成一次权重闭环调整。";
}

function formatTopWeights(weights) {
  return topWeights(weights, 3).map(([key, value]) => `${metricLabel(key)} ${pct(value, 0)}`).join(" / ");
}

function formatTopGroupWeights(weights) {
  return Object.entries(weights).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, 3)
    .map(([key, value]) => `${groupMeta[key]?.[0] ?? key} ${pct(value, 0)}`).join(" / ");
}

function adjustmentMetrics(metrics = {}) {
  const parts = [];
  if (metrics.sla_rate !== undefined) parts.push(`SLA ${pct(metrics.sla_rate, 0)}`);
  if (metrics.failure_rate !== undefined) parts.push(`失败 ${pct(metrics.failure_rate, 0)}`);
  if (metrics.budget_violation_rate !== undefined) parts.push(`预算违规 ${pct(metrics.budget_violation_rate, 0)}`);
  if (metrics.load_imbalance !== undefined) parts.push(`负载不均衡 ${fmt(metrics.load_imbalance, 3)}`);
  return parts.join(" / ");
}

function currentWeights(report) {
  const decision = activeDecision(report, state.intentPayload);
  return { ...defaultWeights, ...(report?.policy_weights ?? {}), ...(decision?.weights ?? {}), ...draftWeights };
}

function currentGroupWeights(report) {
  return { ...defaultGroupWeights, ...(report?.policy_group_weights ?? {}), ...draftGroupWeights };
}

function previousWeights(report) {
  const history = report?.policy_history ?? report?.adjustment_history ?? [];
  return history.length ? history.at(-2)?.weights ?? history.at(-1)?.weights ?? {} : report?.policy_weights ?? {};
}

function activeTaskCount(report) {
  return Object.values(report?.task_statuses ?? {}).filter((status) => ["pending", "running", "scheduling", "assigned"].includes(status)).length;
}

function deltaText(delta) {
  if (Math.abs(delta) < 0.005) return "0%";
  return `${delta > 0 ? "+" : ""}${pct(delta, 0)}`;
}

function previewWeights() {
  const banner = document.getElementById("alertBanner");
  const weights = currentWeights(state.report);
    banner.textContent = `目标组优先级：${formatTopGroupWeights(currentGroupWeights(state.report))}；组内前三项：${formatTopWeights(weights) || "暂无修改"}`;
  banner.hidden = false;
}

async function submitWeights() {
  const banner = document.getElementById("alertBanner");
  try {
    const submittedWeights = currentWeights(state.report);
    await updatePolicyWeights({
      confirmed_by_user_button: true,
      weights: submittedWeights,
      group_weights: currentGroupWeights(state.report),
      reason: "用户手动提交多维策略权重。",
    });
    localTimeline.push({
      tick: "manual",
      scope: "人工提交",
      reason: "用户手动提交多维策略权重。",
      change: `提交 ${topWeights(submittedWeights, 3).map(([key]) => metricLabel(key)).join("、")} 优先策略`,
      affected_tasks: activeTaskCount(state.report),
      weights: submittedWeights,
    });
    banner.textContent = "策略提交成功，控制面将在下一次刷新后展示最新结果。";
    banner.hidden = false;
    draftWeights = {};
    draftGroupWeights = {};
    selectedTemplate = "";
    emit("report:refresh");
  } catch (error) {
    banner.textContent = `策略提交失败：${error.message}`;
    banner.hidden = false;
  }
}
