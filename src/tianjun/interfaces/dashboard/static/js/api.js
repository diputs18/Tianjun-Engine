import { requestJson, responseError } from "./request.js";

const BASE = "";

export async function fetchReport(view = "summary", options = {}) {
  const query = new URLSearchParams();
  if (options.cursor !== undefined) query.set("cursor", String(options.cursor));
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  const suffix = query.size ? `?${query}` : "";
  return _get(`/report/${encodeURIComponent(view)}${suffix}`, options.signal);
}
export async function fetchHealth(options = {}) { return _get("/health", options.signal); }
export async function startHermesSession(payload) { return _post("/chat/sessions", payload); }

export async function streamHermesChat(sessionId, message, signal) {
  const endpoint = sessionId
    ? `/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`
    : "/chat/sessions/stream";
  return fetch(BASE + endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
}

export async function commitHermesPolicy(sessionId, payload) {
  return _post(`/chat/sessions/${encodeURIComponent(sessionId)}/commit`, payload);
}

export async function submitFeedback(payload) { return _post("/feedback", payload); }
export async function commitPolicy(payload) { return _post("/policies/commit", payload); }
export async function updatePolicyWeights(payload) { return _post("/policy-weights", payload); }
export async function cancelTaskRun(taskId, requeue = false) { return _post("/task-runs/cancel", { task_id: taskId, requeue }); }
export async function getTaskBatch(batchId) { return _get(`/task-batches/${encodeURIComponent(batchId)}`); }
export async function getTaskBatchMetrics(batchId) { return _get(`/task-batches/${encodeURIComponent(batchId)}/metrics`); }
export async function previewTaskBatch(batchId, payload = {}) { return _post(`/task-batches/${encodeURIComponent(batchId)}/preview`, payload); }
export async function compareTaskBatch(batchId, payload = {}) { return _post(`/task-batches/${encodeURIComponent(batchId)}/compare`, payload); }
export async function commitTaskBatch(batchId, payload) { return _post(`/task-batches/${encodeURIComponent(batchId)}/commit`, payload); }

export async function importTaskBatch(file) {
  const isCsv = file.type.includes("csv") || file.name.toLowerCase().endsWith(".csv");
  const body = await file.text();
  const path = isCsv
    ? `/task-batches/import?name=${encodeURIComponent(file.name.replace(/\.csv$/i, ""))}`
    : "/task-batches/import";
  const response = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": isCsv ? "text/csv; charset=utf-8" : "application/json" },
    body,
  });
  if (!response.ok) throw await responseError(response, `POST ${path}`);
  return response.json();
}

async function _get(path, signal) {
  return requestJson(BASE + path, { signal });
}

async function _post(path, body) {
  return requestJson(BASE + path, { method: "POST", body });
}
