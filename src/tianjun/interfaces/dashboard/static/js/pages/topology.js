import { renderTopology as renderTopologyCanvas } from "../topology.js";
import { escapeHtml, fmt } from "../utils.js";

let activeLayer = "network";
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
        <div class="topology-layer-head"><h2 class="card-title title-topology">交互式网络拓扑</h2><nav id="topologyLayers" class="layer-switch" aria-label="拓扑图层"><button class="active" data-layer="network">网络</button><button data-layer="load">负载</button><button data-layer="carbon">碳强度</button></nav></div>
        <div id="topologyCanvas" class="topology-canvas"></div>
        <section id="pathMetrics" class="grid path-metrics"></section>
      </article>
      <aside class="card">
        <h2 class="card-title title-topology">节点 / 链路详情</h2>
        <div id="topologyDetailPanel"></div>
        <div id="carbonSiteSummary" class="carbon-site-summary"></div>
      </aside>
    </section>`;
  document.getElementById("topologyLayers").addEventListener("click", (event) => {
    const button = event.target.closest("[data-layer]");
    if (!button) return;
    activeLayer = button.dataset.layer;
    document.querySelectorAll("[data-layer]").forEach((item) => item.classList.toggle("active", item.dataset.layer === activeLayer));
    renderTopology(latestReport);
  });
}

export function renderTopology(report) {
  latestReport = report;
  renderTopologyCanvas(report, document.getElementById("topologyCanvas"));
  const canvas = document.getElementById("topologyCanvas");
  canvas.dataset.layer = activeLayer;
  renderCarbonSites(report);
}

function renderCarbonSites(report) {
  const target = document.getElementById("carbonSiteSummary");
  if (!target || !report) return;
  const nodes = report.nodes || [];
  const sites = new Map();
  for (const node of nodes) {
    const key = node.site_id || node.region || "unknown";
    if (!sites.has(key)) sites.set(key, { nodes: 0, pue: 0, ci: 0, power: 0 });
    const item = sites.get(key);
    item.nodes += 1;
    item.pue += Number(node.carbon_profile?.pue || 1);
    item.ci += Number(node.carbon_profile?.carbon_intensity_g_per_kwh || 0);
    item.power += Number(node.current_power_w || 0);
  }
  target.innerHTML = `<h3>${activeLayer === "carbon" ? "站点碳强度图层" : activeLayer === "load" ? "站点负载图层" : "站点能源画像"}</h3>${Array.from(sites.entries()).map(([site, item]) => `<div><b>${escapeHtml(site)}</b><span>PUE ${fmt(item.pue / item.nodes, 2)}</span><span>CI ${fmt(item.ci / item.nodes, 1)} g/kWh</span><span>${fmt(item.power, 1)} W</span></div>`).join("") || `<p class="muted">等待节点能源遥测</p>`}`;
}
