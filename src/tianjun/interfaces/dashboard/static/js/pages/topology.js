import { renderTopology as renderTopologyCanvas } from "../topology.js";
import { carbonSourceSummary, loadSourceSummary, sourceLabel } from "../topology-data.js";
import { escapeHtml, fmt } from "../utils.js";

const topologyLayers = new Set(["network", "load", "carbon"]);
const requestedLayer = new URLSearchParams(location.search).get("topologyLayer");
let activeLayer = topologyLayers.has(requestedLayer) ? requestedLayer : "network";
let latestReport = null;

export function initTopology() {
  document.getElementById("page-topology").innerHTML = `
    <div class="page-head">
      <div>
        <h1 class="page-title">网络拓扑</h1>
        <p class="page-subtitle">DCI 跨数据中心网络拓扑与数据中心内部 Spine-Leaf 结构。</p>
      </div>
    </div>
    <section class="grid topology-layout">
      <article class="card topology-map-card">
        <div class="topology-layer-head"><h2 class="card-title title-topology">交互式网络拓扑</h2><nav id="topologyLayers" class="layer-switch" aria-label="拓扑图层"><button class="active" type="button" data-layer="network" aria-pressed="true" title="查看链路、路径、时延与带宽">网络</button><button type="button" data-layer="load" aria-pressed="false" title="按实时 CPU、内存和 GPU 利用率标记资源热点">资源负载</button><button type="button" data-layer="carbon" aria-pressed="false" title="按站点碳强度标记高碳与低碳区域">碳强度</button></nav></div>
        <div id="topologyCanvas" class="topology-canvas"></div>
        <section id="pathMetrics" class="grid path-metrics"></section>
      </article>
      <aside class="card">
        <h2 class="card-title title-topology">节点 / 链路详情</h2>
        <div id="topologyDetailPanel"></div>
        <div id="topologyLayerSummary" class="topology-layer-summary"></div>
      </aside>
    </section>`;
  syncLayerButtons();
  document.getElementById("topologyLayers").addEventListener("click", (event) => {
    const button = event.target.closest("[data-layer]");
    if (!button) return;
    activeLayer = button.dataset.layer;
    syncLayerButtons();
    renderTopology(latestReport);
  });
}

function syncLayerButtons() {
  document.querySelectorAll("#topologyLayers [data-layer]").forEach((item) => {
    const selected = item.dataset.layer === activeLayer;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-pressed", String(selected));
  });
}

export function renderTopology(report) {
  latestReport = report;
  renderTopologyCanvas(report, document.getElementById("topologyCanvas"));
  const canvas = document.getElementById("topologyCanvas");
  canvas.dataset.layer = activeLayer;
  document.getElementById("pathMetrics").hidden = activeLayer !== "network";
  applyLayerVisuals(report, canvas);
  renderLayerSummary(report);
}

function renderLayerSummary(report) {
  const target = document.getElementById("topologyLayerSummary");
  if (!target || !report) return;
  if (activeLayer === "network") {
    target.innerHTML = `<div class="layer-summary-head"><div><span class="layer-summary-kicker">NETWORK LAYER</span><h3>网络状态图例</h3></div><span class="layer-summary-badge network">链路排障</span></div>
      <p class="layer-summary-copy">保留设备角色颜色，青色高亮当前任务路径；链路标签展示时延与带宽，点击节点或链路查看详细指标。</p>
      <div class="network-layer-legend">
        <span><i class="legend-line route"></i><b>当前路径</b><small>任务正在使用</small></span>
        <span><i class="legend-dot congested"></i><b>拥塞</b><small>带宽或风险异常</small></span>
        <span><i class="legend-dot fault"></i><b>故障</b><small>链路已隔离</small></span>
      </div>`;
    return;
  }
  const nodes = report.nodes ?? [];
  if (activeLayer === "load") {
    const groups = groupNodes(nodes, (node) => dcKey(node));
    target.innerHTML = `<div class="layer-summary-head"><div><span class="layer-summary-kicker">RESOURCE LAYER</span><h3>数据中心负载</h3></div><span class="layer-summary-badge load">${escapeHtml(loadSourceSummary(nodes))}</span></div>
      <p class="layer-summary-copy">优先使用节点遥测；无遥测时使用任务分配量估算。颜色取 CPU、内存、GPU 中的最高利用率，并在每个数据中心标明来源。</p>
      <div class="layer-summary-list">${["dc1", "dc2", "dc3"].map((key) => renderLoadSummary(key, groups.get(key) ?? [])).join("")}</div>
      ${renderHeatLegend("负载", "%")}`;
    return;
  }

  const sites = new Map();
  for (const node of nodes) {
    const key = node.site_id || node.region || "unknown";
    if (!sites.has(key)) sites.set(key, { nodes: 0, pue: 0, ci: 0, power: 0, dc: dcKey(node), sources: new Set() });
    const item = sites.get(key);
    item.nodes += 1;
    item.pue += Number(node.carbon_profile?.pue || 1);
    item.ci += carbonIntensity(node);
    item.power += Number(node.current_power_w || 0);
    item.sources.add(node.carbon_data_source || "configured_profile");
  }
  const sortedSites = Array.from(sites.entries()).sort((left, right) => (left[1].ci / left[1].nodes) - (right[1].ci / right[1].nodes));
  target.innerHTML = `<div class="layer-summary-head"><div><span class="layer-summary-kicker">CARBON LAYER</span><h3>站点碳强度</h3></div><span class="layer-summary-badge carbon">${escapeHtml(carbonSourceSummary(nodes))}</span></div>
    <p class="layer-summary-copy">CI 可能来自实时信号、CloudSim 模拟或配置曲线；300 g/kWh 以下为低碳，301–450 为中等，超过 450 为高碳。</p>
    <div class="layer-summary-list">${sortedSites.map(([site, item], index) => renderCarbonSummary(site, item, index === 0)).join("") || `<p class="muted">等待节点能源遥测</p>`}</div>
    ${renderHeatLegend("CI", "g/kWh")}`;
}

function renderLoadSummary(key, nodes) {
  const metrics = aggregateNodeMetrics(nodes);
  const value = Math.max(metrics.cpu, metrics.memory, metrics.gpu);
  const level = heatLevel(value, 60, 80);
  const state = { low: "容量充足", medium: "需观察", high: "资源热点" }[level];
  const source = loadSourceSummary(nodes);
  return `<article class="layer-summary-row heat-${level}">
    <div class="layer-summary-row-head"><b>${escapeHtml(key.toUpperCase())}</b><span>${escapeHtml(`${state} · ${source}`)}</span></div>
    <div class="layer-summary-metrics"><span><small>CPU</small><b>${fmt(metrics.cpu, 1)}%</b></span><span><small>内存</small><b>${fmt(metrics.memory, 1)}%</b></span><span><small>GPU</small><b>${fmt(metrics.gpu, 1)}%</b></span><span><small>任务</small><b>${metrics.tasks}</b></span></div>
  </article>`;
}

function renderCarbonSummary(site, item, recommended) {
  const ci = item.nodes ? item.ci / item.nodes : 0;
  const level = heatLevel(ci, 301, 451);
  const state = { low: "低碳", medium: "中等", high: "高碳" }[level];
  const dcLabel = item.dc && item.dc !== "unknown" ? item.dc.toUpperCase() : displayDcLabel(site);
  const source = sourceLabel(Array.from(item.sources), "carbon");
  return `<article class="layer-summary-row heat-${level}">
    <div class="layer-summary-row-head"><b>${escapeHtml(dcLabel)}</b><span>${escapeHtml(`${recommended ? "推荐 · " : ""}${state} · ${source}`)}</span></div>
    <div class="layer-summary-metrics carbon"><span><small>CI</small><b>${fmt(ci, 1)} g/kWh</b></span><span><small>PUE</small><b>${fmt(item.pue / item.nodes, 2)}</b></span><span><small>功率</small><b>${fmt(item.power, 1)} W</b></span></div>
  </article>`;
}

function displayDcLabel(site) {
  const match = String(site ?? "").match(/^site[-_\s]?(\d+)$/i);
  return match ? `DC${match[1]}` : String(site || "未知机房");
}

function renderHeatLegend(label, unit) {
  return `<div class="heat-legend" aria-label="${escapeHtml(label)}颜色图例"><span><i class="low"></i>低</span><span><i class="medium"></i>中</span><span><i class="high"></i>高</span><small>${escapeHtml(label)}分级 · ${escapeHtml(unit)}</small></div>`;
}

function applyLayerVisuals(report, canvas) {
  if (!canvas || activeLayer === "network") return;
  const nodes = report?.nodes ?? [];
  const dcGroups = groupNodes(nodes, (node) => dcKey(node));
  const locationGroups = groupNodes(nodes, (node) => String(node.location ?? "").toLowerCase());

  canvas.querySelectorAll(".network-node.dc[data-node]").forEach((element) => {
    decorateLayerTarget(element, dcGroups.get(element.dataset.node) ?? []);
  });
  canvas.querySelectorAll(".compute-card[data-node]").forEach((element) => {
    const location = locationFromText(element.dataset.node);
    decorateLayerTarget(element, locationGroups.get(location) ?? []);
  });
  canvas.querySelectorAll(".vm-node[data-vm]").forEach((element) => {
    const source = actualNodeForVm(nodes, element);
    decorateLayerTarget(element, source ? [source] : []);
  });
}

function decorateLayerTarget(element, nodes) {
  if (!nodes.length) return;
  let value;
  let label;
  let level;
  if (activeLayer === "load") {
    const metrics = aggregateNodeMetrics(nodes);
    value = Math.max(metrics.cpu, metrics.memory, metrics.gpu);
    label = `负载 ${fmt(value, 0)}%`;
    level = heatLevel(value, 60, 80);
  } else {
    value = average(nodes.map(carbonIntensity));
    label = `CI ${fmt(value, 0)}`;
    level = heatLevel(value, 301, 451);
  }
  element.classList.add("layer-heat-target", `heat-${level}`);
  element.dataset.layerValue = label;
  const source = activeLayer === "load" ? loadSourceSummary(nodes) : carbonSourceSummary(nodes);
  element.title = `${element.title || element.textContent.trim()} / ${label} / ${source}`;
}

function aggregateNodeMetrics(nodes) {
  return {
    cpu: average(nodes.map((node) => utilizationPercent(node, "cpu"))),
    memory: average(nodes.map((node) => utilizationPercent(node, "memory"))),
    gpu: average(nodes.map((node) => utilizationPercent(node, "gpu"))),
    tasks: nodes.reduce((sum, node) => sum + (node.active_task_ids?.length ?? node.running_tasks?.length ?? 0), 0),
  };
}

function utilizationPercent(node, key) {
  const runtime = node.runtime_utilization?.[key];
  const direct = node[`${key}_utilization`] ?? node[`${key}_used_ratio`];
  const raw = runtime ?? direct;
  if (raw !== undefined && Number.isFinite(Number(raw))) {
    const value = Number(raw);
    return Math.max(0, Math.min(100, value <= 1 ? value * 100 : value));
  }
  const capacity = Number(node.capacity?.[key] ?? 0);
  const available = Number(node.available?.[key] ?? capacity);
  return capacity > 0 ? Math.max(0, Math.min(100, ((capacity - available) / capacity) * 100)) : 0;
}

function carbonIntensity(node) {
  return Number(node.carbon_profile?.current_carbon_intensity_g_per_kwh ?? node.carbon_profile?.carbon_intensity_g_per_kwh ?? 0);
}

function actualNodeForVm(nodes, element) {
  if (element.dataset.nodeId) {
    const exact = nodes.find((node) => node.node_id === element.dataset.nodeId);
    if (exact) return exact;
  }
  const location = locationFromText(element.dataset.cluster);
  const vmIndex = Math.max(0, Number(String(element.dataset.name ?? "VM-00").match(/\d+/)?.[0] ?? 0));
  return nodes.find((node) => String(node.location ?? "").toLowerCase() === location && new RegExp(`vm[-_]${vmIndex}$`, "i").test(node.node_id ?? ""));
}

function locationFromText(value) {
  const text = String(value ?? "").toLowerCase();
  return ["beijing", "hangzhou", "chengdu", "chongqing", "guangzhou", "shenzhen"].find((location) => text.includes(location)) ?? text;
}

function dcKey(node) {
  const text = `${node.region ?? ""} ${node.node_id ?? ""}`.toLowerCase();
  return text.match(/dc[-_]?([123])/) ? `dc${text.match(/dc[-_]?([123])/)[1]}` : "unknown";
}

function groupNodes(nodes, keyFor) {
  const groups = new Map();
  for (const node of nodes) {
    const key = keyFor(node);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  }
  return groups;
}

function average(values) {
  const valid = values.map(Number).filter(Number.isFinite);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : 0;
}

function heatLevel(value, mediumAt, highAt) {
  if (value >= highAt) return "high";
  if (value >= mediumAt) return "medium";
  return "low";
}
