import { initChat, updateAgentRuntimeStatus } from "../chat.js";
import { commitTaskBatch, compareTaskBatch, getTaskBatchMetrics, importTaskBatch, previewTaskBatch } from "../api.js";
import { state } from "../state.js";
import { activeDecision, compactText, decisionScore, escapeHtml, fmt, gnnDisplayState, nodeLoad, pct, stableLatencyOf } from "../utils.js";

let initialized = false;
let selectedTaskId = null;
let schedulingMode = "single";

export function initScheduling() {
  document.getElementById("page-scheduling").innerHTML = `
    <header class="page-head">
      <div>
        <h1 class="page-title">调度决策</h1>
        <p class="page-subtitle">当前决策队列、候选节点对比与资源占用预测。</p>
      </div>
    </header>
    <section class="batch-mode-shell" aria-label="调度模式">
      <div class="mode-switch" role="tablist" aria-label="单任务或批任务">
        <button class="mode-btn active" data-scheduling-mode="single" role="tab" aria-selected="true">单任务</button>
        <button class="mode-btn" data-scheduling-mode="batch" role="tab" aria-selected="false">批任务</button>
      </div>
      <article id="batchWorkbench" class="card batch-workbench" hidden>
        <div class="batch-workbench-head">
          <div><span class="eyebrow">BATCH ORCHESTRATION</span><h2 class="card-title title-teal">批任务联合调度</h2><p class="muted">JSON / CSV 原子导入，共享快照联合分配，确认后统一预留。</p></div>
          <button id="downloadBatchTemplate" class="btn-ghost" type="button">下载 CSV 模板</button>
        </div>
        <div class="batch-flow" aria-label="批调度步骤">
          <span class="active">1 导入校验</span><span>2 策略对比</span><span>3 方案预演</span><span>4 确认下发</span>
        </div>
        <label id="batchDropzone" class="batch-dropzone" tabindex="0">
          <input id="batchFile" type="file" accept=".json,.csv,application/json,text/csv" hidden>
          <b>拖拽或选择批任务文件</b><span>单批最多 1000 个任务，文件不超过 5 MB</span>
        </label>
        <div id="batchImportState" class="batch-import-state"><span class="status-beacon"></span><p>尚未导入批次</p></div>
        <div id="batchSummary" class="batch-summary" hidden></div>
        <div class="batch-actions">
          <label>在线策略<select id="batchStrategy"><option value="B6-hierarchical-batch">B6 五组分层融合</option><option value="B6-green-sla-85-v1">B6 绿色 + SLA 双目标（实验）</option><option value="B6-green-single-v1">B6 绿色单目标（实验）</option><option value="B4-pareto-tchebycheff">B4 十维扁平融合</option><option value="B3-batch-local-search">B3 贪心 + 局部优化</option><option value="B1-batch-greedy">B1 批内贪心</option><option value="B0-current">B0 当前基线</option></select></label>
          <button id="compareBatch" class="btn-ghost" type="button" disabled>对比 B0/B1/B3/B4/B6</button>
          <button id="previewBatch" class="btn-primary" type="button" disabled>生成预演方案</button>
          <button id="refreshBatchMetrics" class="btn-ghost" type="button" disabled>刷新实际指标</button>
        </div>
        <div id="batchPlanResult" class="batch-plan-result" hidden></div>
        <div id="batchActualResult" class="batch-plan-result" hidden></div>
        <div id="batchCommitBar" class="batch-commit-bar" hidden>
          <p><b>显式确认保护</b><span>提交前将再次校验资源快照版本；冲突时整批拒绝，不产生部分预留。</span></p>
          <button id="commitBatch" class="btn-danger" type="button">确认并统一预留</button>
        </div>
      </article>
    </section>
    <section class="grid scheduling-engine">
      <article class="card decision-queue-panel">
        <h2 class="card-title title-teal">当前决策队列</h2>
        <div id="decisionQueue" class="decision-queue"></div>
      </article>
      <aside class="card node-compare-panel">
        <h2 class="card-title title-teal">节点对比面板</h2>
        <div id="nodeComparePanel" class="node-compare"></div>
      </aside>
    </section>
    <button id="hermesToggle" class="hermes-fab" type="button">咨询 Hermes</button>
    <aside id="hermesDrawer" class="hermes-drawer" hidden>
      <article class="card agent-workbench">
        <div class="drawer-head">
          <h2 class="card-title title-teal">Hermes 咨询</h2>
          <button id="hermesClose" class="btn-ghost btn-sm" type="button">收起</button>
        </div>
        <div class="workbench-body">
          <section class="conversation-stack">
            <div id="chatLog" class="chat-log"></div>
            <div class="conversation-dock">
              <details class="info-panel parse-panel" id="requirementParsePanel">
                <summary><span>需求解析</span><b id="requirementParseSummary">等待输入</b></summary>
                <div id="requirementParse" class="kv-grid"></div>
              </details>
              <div class="composer">
                <textarea id="intentInput" rows="3" placeholder="输入业务需求、约束或优化反馈。"></textarea>
                <div class="composer-actions">
                  <button id="askButton" class="btn-primary">发送</button>
                  <button id="stopHermesButton" class="btn-danger" disabled>暂停回复</button>
                  <button id="submitButton" class="btn-danger" disabled>正式下发</button>
                  <button id="endTaskButton" class="btn-ghost">新会话</button>
                </div>
              </div>
            </div>
          </section>
          <aside class="assistant-side">
            <div class="details-grid hermes-runtime">
              <div class="field"><label>当前模型</label><b id="agentLlmMode">检查中</b></div>
              <div class="field"><label>当前阶段</label><b id="agentRuntimeMode">等待输入</b></div>
              <div class="field"><label>工具链状态</label><b id="agentToolMode">检查中</b></div>
              <div class="field"><label>策略状态</label><b id="intentSummaryStatus">等待需求</b></div>
            </div>
            <div id="schedulingContext" class="kv-grid context-grid"></div>
            <div id="intentSummaryBody" class="details-grid hidden-summary"></div>
            <p id="workspaceRisk" class="muted">等待策略生成后显示风险、确认要求和下发保护状态。</p>
            <section class="tool-trace-panel"><div class="tool-trace-head"><b>工具调用 / 决策过程</b><span id="toolTraceStatus">等待输入</span></div><div id="toolTraceSteps" class="tool-steps decision-steps"></div></section>
          </aside>
        </div>
      </article>
    </aside>`;

  document.getElementById("hermesToggle").addEventListener("click", () => {
    document.getElementById("hermesDrawer").hidden = false;
    document.getElementById("hermesToggle").hidden = true;
  });
  document.getElementById("hermesClose").addEventListener("click", () => {
    document.getElementById("hermesDrawer").hidden = true;
    document.getElementById("hermesToggle").hidden = false;
  });
  document.getElementById("decisionQueue").addEventListener("click", (event) => {
    const item = event.target.closest("[data-task-id]");
    if (!item) return;
    selectedTaskId = item.dataset.taskId;
    renderScheduling(state.report, state.health);
  });
  bindBatchWorkbench();
  initChat();
  initialized = true;
}

function bindBatchWorkbench() {
  document.querySelectorAll("[data-scheduling-mode]").forEach((button) => button.addEventListener("click", () => {
    schedulingMode = button.dataset.schedulingMode;
    document.querySelectorAll("[data-scheduling-mode]").forEach((item) => {
      const active = item.dataset.schedulingMode === schedulingMode;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    document.getElementById("batchWorkbench").hidden = schedulingMode !== "batch";
    document.querySelector(".scheduling-engine").hidden = schedulingMode === "batch";
  }));
  const input = document.getElementById("batchFile");
  const dropzone = document.getElementById("batchDropzone");
  input.addEventListener("change", () => input.files[0] && void handleBatchFile(input.files[0]));
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") input.click();
  });
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove("dragging"); }));
  dropzone.addEventListener("drop", (event) => event.dataTransfer.files[0] && void handleBatchFile(event.dataTransfer.files[0]));
  document.getElementById("downloadBatchTemplate").addEventListener("click", downloadBatchTemplate);
  document.getElementById("previewBatch").addEventListener("click", () => void previewSelectedBatch());
  document.getElementById("compareBatch").addEventListener("click", () => void compareSelectedBatch());
  document.getElementById("commitBatch").addEventListener("click", () => void commitSelectedBatch());
  document.getElementById("refreshBatchMetrics").addEventListener("click", () => void refreshSelectedBatchMetrics());
  if (new URLSearchParams(location.search).get("mode") === "batch") {
    document.querySelector('[data-scheduling-mode="batch"]').click();
  }
}

async function handleBatchFile(file) {
  setBatchStatus(`正在校验 ${file.name}…`, "working");
  try {
    const batch = await importTaskBatch(file);
    state.selectedBatch = batch;
    state.selectedBatchPlan = null;
    state.selectedBatchMetrics = null;
    state.batchComparison = null;
    setBatchStatus(`批次 ${batch.batch_id} 校验通过`, "success");
    renderBatchSummary(batch);
    document.getElementById("previewBatch").disabled = false;
    document.getElementById("compareBatch").disabled = false;
    document.getElementById("refreshBatchMetrics").disabled = false;
    document.getElementById("batchPlanResult").hidden = true;
    document.getElementById("batchActualResult").hidden = true;
    document.getElementById("batchCommitBar").hidden = true;
  } catch (error) {
    setBatchStatus(error.message, "error");
  }
}

function renderBatchSummary(batch) {
  const target = document.getElementById("batchSummary");
  target.hidden = false;
  target.innerHTML = [
    ["批次", batch.batch_name || batch.batch_id],
    ["状态", String(batch.status || "validated").toUpperCase()],
    ["任务数", batch.task_count ?? batch.validation?.valid_count ?? 0],
    ["内容指纹", compactText(batch.content_hash, 18)],
  ].map(([label, value]) => `<div><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`).join("");
}

async function previewSelectedBatch() {
  const batch = state.selectedBatch;
  if (!batch) return;
  setBatchStatus("正在构建统一资源快照与候选矩阵…", "working");
  try {
    const plan = await previewTaskBatch(batch.batch_id, { strategy: document.getElementById("batchStrategy").value });
    state.selectedBatchPlan = plan;
    renderBatchPlan(plan);
    setBatchStatus(`预演完成：已分配 ${plan.task_node_assignments.length} 个任务`, "success");
  } catch (error) {
    setBatchStatus(error.message, "error");
  }
}

async function compareSelectedBatch() {
  const batch = state.selectedBatch;
  if (!batch) return;
  setBatchStatus("正在使用相同快照对比 B0、B1、B3、B4、B6…", "working");
  try {
    const comparison = await compareTaskBatch(batch.batch_id, {});
    state.batchComparison = comparison;
    const plan = comparison.strategies.find((item) => item.plan_id === comparison.recommended_plan_id) || comparison.strategies[0];
    state.selectedBatchPlan = plan;
    renderBatchPlan(plan, comparison.strategies);
    setBatchStatus("策略对比完成，已选择综合结果最佳方案", "success");
  } catch (error) {
    setBatchStatus(error.message, "error");
  }
}

function renderBatchPlan(plan, strategies = []) {
  const target = document.getElementById("batchPlanResult");
  target.hidden = false;
  const metrics = [
    ["已分配", plan.task_node_assignments?.length ?? 0, "tasks"],
    ["未分配", plan.unassigned_tasks?.length ?? 0, "tasks"],
    ["Makespan", fmt(plan.predicted_makespan, 1), "ticks"],
    ["运行碳", fmt(plan.predicted_carbon_g, 3), "gCO₂e"],
    ["能耗", fmt(plan.predicted_energy_kwh, 5), "kWh"],
    ["Future-Fit", `${fmt(plan.future_fit_before, 3)} → ${fmt(plan.future_fit_after, 3)}`, ""],
    ["方案效用", fmt(plan.plan_utility, 4), "J(plan)"],
  ];
  const groupLabels = { sla_quality: "SLA 质量", network_coordination: "网络协同", resource_efficiency: "资源效率", economic_cost: "经济成本", green_carbon: "绿色低碳" };
  const groupScores = Object.entries(plan.group_objective_breakdown || {});
  target.innerHTML = `
    ${strategies.length ? `<div class="strategy-strip">${strategies.map((item) => `<button type="button" data-plan-id="${escapeHtml(item.plan_id)}" class="strategy-card ${item.plan_id === plan.plan_id ? "active" : ""}"><b>${escapeHtml(item.strategy)}</b><span>${item.task_node_assignments.length} 已分配 · ${fmt(item.predicted_carbon_g, 2)} gCO₂e</span></button>`).join("")}</div>` : ""}
    <div class="batch-kpis">${metrics.map(([label, value, unit]) => `<div><span>${label}</span><b>${escapeHtml(value)} <small>${unit}</small></b></div>`).join("")}</div>
    ${groupScores.length ? `<section class="group-score-strip" aria-label="分层目标组得分">${groupScores.map(([key, value]) => `<div><span>${escapeHtml(groupLabels[key] || key)}</span><b>${fmt(value, 3)}</b><small>组权重 ${fmt(plan.group_weights?.[key], 3)}</small></div>`).join("")}</section><p class="hierarchy-note">${escapeHtml(plan.objective_hierarchy_version || "flat-ten-v1")} · 活跃目标：${escapeHtml((plan.active_objectives || []).join(" / "))} · 安全风险惩罚 ${fmt(plan.security_risk_penalty, 4)}</p>` : ""}
    <div class="assignment-table-wrap"><table class="assignment-table"><thead><tr><th>任务</th><th>目标节点</th><th>效用</th><th>预计完成</th><th>运行碳</th></tr></thead><tbody>${(plan.task_node_assignments || []).slice(0, 100).map((item) => `<tr><td>${escapeHtml(item.task_id)}</td><td>${escapeHtml(item.node_id)}</td><td>${fmt(item.decision?.total_score, 4)}</td><td>${fmt(item.decision?.predicted_finish_tick, 0)}</td><td>${fmt(item.predicted_carbon_g, 4)} g</td></tr>`).join("") || `<tr><td colspan="5">没有可分配任务</td></tr>`}</tbody></table></div>
    ${(plan.unassigned_tasks || []).length ? `<div class="unassigned-list"><b>未分配原因</b>${plan.unassigned_tasks.map((item) => `<span>${escapeHtml(item.task_id)} · ${escapeHtml(item.reason)}</span>`).join("")}</div>` : ""}`;
  target.querySelectorAll("[data-plan-id]").forEach((button) => button.addEventListener("click", () => {
    const selected = strategies.find((item) => item.plan_id === button.dataset.planId);
    if (selected) { state.selectedBatchPlan = selected; renderBatchPlan(selected, strategies); }
  }));
  document.getElementById("batchCommitBar").hidden = false;
}

async function commitSelectedBatch() {
  const batch = state.selectedBatch;
  const plan = state.selectedBatchPlan;
  if (!batch || !plan) return;
  const button = document.getElementById("commitBatch");
  button.disabled = true;
  setBatchStatus("正在校验快照版本并原子写入预留账本…", "working");
  try {
    const result = await commitTaskBatch(batch.batch_id, { plan_id: plan.plan_id, resource_snapshot_version: plan.resource_snapshot_version, confirmed_by_user_button: true });
    setBatchStatus(`批次已提交，生成 ${result.leases?.length ?? 0} 条资源租约`, "success");
    document.getElementById("batchCommitBar").hidden = true;
    await refreshSelectedBatchMetrics();
  } catch (error) {
    setBatchStatus(error.message, "error");
    button.disabled = false;
  }
}

async function refreshSelectedBatchMetrics() {
  const batch = state.selectedBatch;
  if (!batch) return;
  const button = document.getElementById("refreshBatchMetrics");
  button.disabled = true;
  try {
    const metrics = await getTaskBatchMetrics(batch.batch_id);
    state.selectedBatchMetrics = metrics;
    renderBatchActualMetrics(metrics);
    setBatchStatus(`实际执行进度：${metrics.completed_count}/${metrics.assigned_count}，状态 ${metrics.status}`, metrics.failed_count ? "error" : "success");
  } catch (error) {
    setBatchStatus(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

function renderBatchActualMetrics(metrics) {
  const target = document.getElementById("batchActualResult");
  target.hidden = false;
  const utilization = `${pct(metrics.average_cpu_utilization ?? 0, 1)} / ${pct(metrics.average_memory_utilization ?? 0, 1)} / ${pct(metrics.average_bandwidth_utilization ?? 0, 1)}`;
  const cards = [
    ["执行状态", String(metrics.status || "running").toUpperCase(), ""],
    ["实际完成", `${metrics.completed_count ?? 0}/${metrics.assigned_count ?? 0}`, "tasks"],
    ["平均 / P95 JCT", `${fmt(metrics.average_jct_seconds, 2)} / ${fmt(metrics.p95_jct_seconds, 2)}`, "s"],
    ["实际 Makespan", fmt(metrics.makespan_seconds, 2), "s"],
    ["CPU / 内存 / 带宽", utilization, ""],
    ["实际能耗", fmt(metrics.total_energy_kwh, 6), "kWh"],
    ["实际运行碳", fmt(metrics.total_operational_carbon_g, 3), "gCO₂e"],
    ["SLA 违规", fmt(metrics.sla_violation_count, 0), "tasks"],
  ];
  target.innerHTML = `<div class="batch-workbench-head"><div><span class="eyebrow">MEASURED EXECUTION</span><h3 class="card-title title-teal">CloudSim 实际执行指标</h3><p class="muted">来自 Cloudlet 结果回传，不是预演估计值。</p></div></div><div class="batch-kpis">${cards.map(([label, value, unit]) => `<div><span>${escapeHtml(label)}</span><b>${escapeHtml(String(value))} <small>${escapeHtml(unit)}</small></b></div>`).join("")}</div>`;
}

function setBatchStatus(message, tone) {
  const target = document.getElementById("batchImportState");
  target.className = `batch-import-state ${tone || ""}`;
  target.querySelector("p").textContent = message;
}

function downloadBatchTemplate() {
  const csv = "task_id,task_type,cpu,memory,gpu,storage,estimated_duration,priority,region,max_latency_ms,security_level,carbon_budget_g,carbon_priority,allow_region_shift,allow_time_shift\nexample-001,inference,4,8,1,20,60,8,shanghai,30,medium,8,0.7,true,false\n";
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = "tianjun-task-batch-template.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

export function renderScheduling(report, health) {
  if (!initialized || !report) return;
  updateAgentRuntimeStatus();
  renderRequirement(report);
  renderContext(report, health);
  renderQueue(report);
  renderCompare(report);
}

function decisions(report) {
  const list = [
    ...state.interactionDecisions.map((entry) => entry.decision).filter(Boolean),
    ...(report.recent_decisions ?? []),
  ];
  const unique = new Map();
  for (const decision of list) unique.set(decision.task_id ?? decision.policy_id ?? decision.node_id, decision);
  return Array.from(unique.values()).sort((a, b) => decisionScore(b) - decisionScore(a));
}

function renderQueue(report) {
  const list = decisions(report).slice(0, 12);
  if (!selectedTaskId && list[0]) selectedTaskId = list[0].task_id;
  document.getElementById("decisionQueue").innerHTML = list.map((decision) => {
    const snap = decision.network_snapshot ?? {};
    const selected = decision.task_id === selectedTaskId;
    const load = predictedLoad(decision, report);
    return `<article class="decision-queue-item ${selected ? "active" : ""}" data-task-id="${escapeHtml(decision.task_id ?? "")}">
      <div class="item-row">
        <b>${escapeHtml(compactText(decision.task_id ?? "-", 42))}</b>
        <span class="badge badge-primary">评分 ${fmt(decisionScore(decision), 3)}</span>
      </div>
      <p class="muted">推荐节点 ${escapeHtml(decision.node_id ?? "-")} · 稳健时延 ${fmt(snap.deterministic_latency_ms ?? snap.stable_latency_ms, 1)}ms · ${escapeHtml(gnnDisplayState(snap, decision, report).compact)}</p>
      <div class="queue-item-foot">
        <span class="resource-forecast" tabindex="0">◌ 资源占用预测<i>执行后节点负载预计 ${pct(load.before, 0)} → ${pct(load.after, 0)}，CPU 占用约 +${pct(load.delta, 0)}</i></span>
        <span class="badge ${load.after > 0.8 ? "badge-danger" : load.after > 0.62 ? "badge-warning" : "badge-success"}">${load.after > 0.8 ? "高负载" : load.after > 0.62 ? "需观察" : "容量充足"}</span>
      </div>
    </article>`;
  }).join("") || "<div class=\"empty\">暂无决策队列。</div>";
}

function renderCompare(report) {
  const decision = decisions(report).find((item) => item.task_id === selectedTaskId) ?? activeDecision(report, state.intentPayload);
  const candidates = topCandidateNodes(report, decision).slice(0, 3);
  document.getElementById("nodeComparePanel").innerHTML = `
    <div class="compare-current">
      <span>当前任务</span>
      <b>${escapeHtml(decision?.task_id ?? "等待选择")}</b>
      <em>推荐节点 ${escapeHtml(decision?.node_id ?? "--")}</em>
    </div>
    <div class="compare-grid">
      ${candidates.map((node) => renderNodeCandidate(node, decision)).join("") || "<div class=\"empty\">暂无候选节点。</div>"}
    </div>`;
}

function renderNodeCandidate(node, decision) {
  const selected = node.node_id === decision?.node_id;
  const load = nodeLoad(node);
  const latency = stableLatencyOf(node);
  const score = selected ? decisionScore(decision) : Math.max(0, Number(node.health_score ?? 0) - load - latency / 100);
  return `<article class="node-candidate ${selected ? "recommended" : ""}">
    <div class="item-row"><b>${escapeHtml(compactText(node.node_id, 30))}</b><span class="badge ${selected ? "badge-success" : "badge-neutral"}">${selected ? "推荐" : "候选"}</span></div>
    <div class="candidate-bars">
      ${candidateBar("时延", 1 - Math.min(1, latency / 8), `${fmt(latency, 1)}ms`)}
      ${candidateBar("稳定性", Number(node.health_score ?? 0), pct(node.health_score ?? 0, 0))}
      ${candidateBar("负载", 1 - load, pct(load, 0))}
      ${candidateBar("评分", Math.min(1, score), fmt(score, 3))}
    </div>
  </article>`;
}

function candidateBar(label, value, text) {
  return `<div class="candidate-bar"><span>${escapeHtml(label)}</span><div class="track"><div class="bar teal" style="width:${Math.max(4, Math.min(100, value * 100))}%"></div></div><b>${escapeHtml(text)}</b></div>`;
}

function topCandidateNodes(report, decision) {
  return (report.nodes ?? []).slice().sort((a, b) => {
    if (a.node_id === decision?.node_id) return -1;
    if (b.node_id === decision?.node_id) return 1;
    const scoreA = Number(a.health_score ?? 0) - nodeLoad(a) - stableLatencyOf(a) / 100;
    const scoreB = Number(b.health_score ?? 0) - nodeLoad(b) - stableLatencyOf(b) / 100;
    return scoreB - scoreA;
  });
}

function predictedLoad(decision, report) {
  const node = (report.nodes ?? []).find((item) => item.node_id === decision?.node_id);
  const before = node ? nodeLoad(node) : 0.42;
  const demand = decision?.task?.demand ?? {};
  const delta = Math.min(0.22, 0.04 + Number(demand.cpu ?? demand.cpu_cores ?? 1) * 0.018);
  return { before, delta, after: Math.min(1, before + delta) };
}

function renderRequirement(report) {
  const payload = state.intentPayload ?? {};
  const task = payload.task ?? payload.submitted_task ?? {};
  const decision = activeDecision(report, state.intentPayload);
  const onlineCount = (report.nodes ?? []).filter((node) => node.online !== false).length;
  const fields = [
    ["任务类型", task.task_type ?? "等待输入"],
    ["目标区域", decision?.network_snapshot?.physical_topology?.source_location ?? "--"],
    ["时延上限", task.max_latency_ms ? `${task.max_latency_ms} ms` : "未指定"],
    ["候选节点数量", String(onlineCount)],
  ];
  const summary = document.getElementById("requirementParseSummary");
  if (summary) summary.textContent = `${task.task_type ?? "等待输入"} · ${onlineCount} 个候选节点`;
  const target = document.getElementById("requirementParse");
  if (target) target.innerHTML = fields.map(([k, v]) => `<div class="kv"><span>${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`).join("");
}

function renderContext(report, health) {
  const decision = activeDecision(report, state.intentPayload);
  const snap = decision?.network_snapshot ?? {};
  const fields = [
    ["LSTM", snap.model_prediction?.lstm_latency_ms !== undefined ? `${fmt(snap.model_prediction.lstm_latency_ms, 1)} ms` : "待预测"],
    ["GNN", gnnDisplayState(snap, decision, report).value],
    ["库存校验", `${(report.nodes ?? []).filter((node) => node.online !== false).length} 个在线节点`],
    ["指标评分", decision?.metric_scores ? "已生成" : "等待生成"],
    ["当前推荐节点", decision?.node_id ?? "等待推荐"],
    ["控制面状态", health?.status === "ok" ? "系统在线" : "检查中"],
    ["当前批次", state.selectedBatch?.batch_id ?? "未选择"],
    ["批次实际执行", state.selectedBatchMetrics ? `${state.selectedBatchMetrics.completed_count}/${state.selectedBatchMetrics.assigned_count} · JCT ${fmt(state.selectedBatchMetrics.average_jct_seconds, 2)} s` : "等待 CloudSim 回传"],
  ];
  const target = document.getElementById("schedulingContext");
  if (target) target.innerHTML = fields.map(([k, v]) => `<div class="kv"><span>${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`).join("");
}
