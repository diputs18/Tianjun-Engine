import { fetchHealth, fetchReport } from "./api.js";
import { emit, on, state } from "./state.js";
import { modelStatusText } from "./utils.js";
import { initOverview, renderOverview } from "./pages/overview.js";
import { initScheduling, renderScheduling } from "./pages/scheduling.js";
import { initTopology, renderTopology } from "./pages/topology.js";
import { initTasks, renderTasks } from "./pages/tasks.js";
import { initModel, renderModel } from "./pages/model.js";

const PAGES = ["overview", "scheduling", "topology", "tasks", "model"];
const renderers = {
  overview: renderOverview,
  scheduling: renderScheduling,
  topology: renderTopology,
  tasks: renderTasks,
  model: renderModel,
};

function navigate(to, updateHash = true) {
  if (!PAGES.includes(to)) to = "overview";
  const current = document.querySelector(".page:not([hidden])");
  const target = document.getElementById(`page-${to}`);
  state.activePage = to;
  document.querySelectorAll(".tab-btn").forEach((button) => {
    const selected = button.dataset.page === to;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  if (updateHash && location.hash.slice(1) !== to) history.replaceState(null, "", `#${to}`);
  if (!target) {
    renderActive();
    return;
  }

  if (current === target) {
    renderActive();
    return;
  }

  if (current) {
    current.hidden = true;
    current.classList.remove("page-exit");
  }
  target.hidden = false;
  target.classList.add("page-enter");
  renderActive();
  requestAnimationFrame(() => target.classList.remove("page-enter"));
  const cached = state.pageReports[to];
  if (cached) {
    state.report = { ...(state.summaryReport ?? {}), ...cached };
    renderActive();
  }
  void refreshDashboard({ force: true });
}

function renderActive() {
  renderers[state.activePage]?.(state.report, state.health);
}

async function refreshDashboard({ force = false } = {}) {
  if (state.refreshPromise && !force) return state.refreshPromise;
  if (force) state.refreshController?.abort();
  const sequence = ++state.refreshSequence;
  const controller = new AbortController();
  state.refreshController = controller;
  const page = state.activePage;
  const pageOptions = page === "tasks" ? { limit: 50 } : {};
  state.refreshPromise = (async () => {
  try {
    const requests = [fetchReport("summary", { signal: controller.signal }), fetchHealth({ signal: controller.signal })];
    if (page !== "overview") requests.push(fetchReport(page, { ...pageOptions, signal: controller.signal }));
    const [summary, health, pageReport = summary] = await Promise.all(requests);
    if (sequence !== state.refreshSequence) return;
    const report = { ...summary, ...pageReport };
    state.summaryReport = summary;
    state.pageReports[page] = pageReport;
    state.report = report;
    state.health = health;
    emit("report", { report, health });
    emit("health", health);
    renderActive();
    updateTopnav(report, health);
    updateAlertBanner(health);
  } catch (error) {
    if (error.name === "AbortError") return;
    const dot = document.getElementById("statusDot");
    dot.className = "status-dot error";
    document.getElementById("systemStatus").textContent = "系统离线";
    document.getElementById("modelStatus").textContent = "连接失败";
    document.getElementById("hermesLlmStatus").textContent = error.message;
    document.getElementById("autoRefreshStatus").textContent = "刷新失败，正在重试";
  } finally {
    if (sequence === state.refreshSequence) {
      state.refreshController = null;
      state.refreshPromise = null;
      schedulePolling();
    }
  }
  })();
  return state.refreshPromise;
}

function updateTopnav(report, health) {
  const dot = document.getElementById("statusDot");
  dot.className = `status-dot ${health?.status === "ok" ? "ok" : "error"}`;
  document.getElementById("systemStatus").className = `badge ${health?.status === "ok" ? "badge-success" : "badge-danger"}`;
  document.getElementById("systemStatus").textContent = health?.status === "ok" ? "系统在线" : "系统异常";
  document.getElementById("modelStatus").className = "badge badge-primary";
  document.getElementById("modelStatus").textContent = modelStatusText(report?.model_runtime ?? health?.model_runtime ?? {});
  const llm = health?.chat_runtime?.llm ?? {};
  document.getElementById("hermesLlmStatus").className = `badge ${llm.enabled ? "badge-success" : "badge-neutral"}`;
  document.getElementById("hermesLlmStatus").textContent = llm.enabled ? `当前模型 ${llm.settings?.model || "LLM 已启用"}` : "本地规则";
  const toolchain = report?.toolchain_runtime ?? {};
  const mcpCall = toolchain.external_mcp_last_call;
  const mcpSuccess = toolchain.external_mcp_last_success;
  const mcpStatus = document.getElementById("mcpStatus");
  const latestCallSucceeded = mcpCall?.result_status === "success";
  mcpStatus.className = `badge ${mcpCall ? (latestCallSucceeded ? "badge-success" : "badge-danger") : "badge-neutral"}`;
  mcpStatus.textContent = mcpCall
    ? `${latestCallSucceeded ? "MCP 工具成功" : "MCP 工具失败"} · ${mcpCall.tool_name}`
    : "MCP 等待工具调用";
  if (mcpCall) {
    const callTime = new Date(mcpCall.timestamp * 1000).toLocaleString("zh-CN");
    const lastSuccess = mcpSuccess
      ? `；最近成功：${mcpSuccess.tool_name}（${new Date(mcpSuccess.timestamp * 1000).toLocaleString("zh-CN")}）`
      : "；尚无成功调用";
    mcpStatus.title = `最近带 MCP 标识的工具请求：${mcpCall.tool_name}（${callTime}），状态：${mcpCall.result_status}${lastSuccess}；成功 ${toolchain.external_mcp_success_count ?? 0}/${toolchain.external_mcp_call_count ?? 0}`;
  } else {
    mcpStatus.title = "尚未收到带工具标识的 MCP 请求；MCP 进程启动本身不计为工具调用";
  }
  document.getElementById("autoRefreshStatus").textContent = "自动刷新中";
  document.getElementById("lastSync").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function updateAlertBanner(health) {
  const banner = document.getElementById("alertBanner");
  const issues = health?.issues ?? [];
  if (issues.length) {
    banner.textContent = `警告 ${issues.join(" / ")}`;
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }
}

export function schedulePolling(intervalMs = 5000) {
  if (state.pollHandle) clearTimeout(state.pollHandle);
  if (document.hidden) {
    state.pollHandle = null;
    document.getElementById("autoRefreshStatus").textContent = "后台暂停刷新";
    return null;
  }
  state.pollHandle = setTimeout(() => void refreshDashboard(), intervalMs);
  return state.pollHandle;
}

function handleTabKeydown(event) {
  const tabs = Array.from(document.querySelectorAll(".tab-btn"));
  const index = tabs.indexOf(event.currentTarget);
  if (index < 0 || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const nextIndex = event.key === "Home"
    ? 0
    : event.key === "End"
      ? tabs.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[nextIndex].focus();
  navigate(tabs[nextIndex].dataset.page);
}

function init() {
  initOverview();
  initScheduling();
  initTopology();
  initTasks();
  initModel();
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.page));
    button.addEventListener("keydown", handleTabKeydown);
  });
  window.addEventListener("hashchange", () => navigate(location.hash.slice(1), false));
  document.getElementById("refreshButton").addEventListener("click", () => void refreshDashboard({ force: true }));
  on("report:refresh", () => void refreshDashboard({ force: true }));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (state.pollHandle) clearTimeout(state.pollHandle);
      state.pollHandle = null;
      state.refreshController?.abort();
      document.getElementById("autoRefreshStatus").textContent = "后台暂停刷新";
    } else {
      void refreshDashboard({ force: true });
    }
  });
  const initial = PAGES.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  document.querySelectorAll(".page").forEach((page) => {
    page.hidden = page.id !== `page-${initial}`;
  });
  navigate(initial, false);
  void refreshDashboard({ force: true });
}

init();
