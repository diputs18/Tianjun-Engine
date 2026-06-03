export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8024";

export async function fetchPath(path, init) {
  return fetch(`${API_BASE}${path}`, init);
}

async function readJson(path, init) {
  const res = await fetchPath(path, init);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function getApiStatus() {
  return readJson("/");
}

export function getReport() {
  return readJson("/report");
}

export function getHealth() {
  return readJson("/health");
}

export function getHermesStatus() {
  return readJson("/hermes/status");
}

export async function postIntent(payload, init = {}) {
  return readJson("/intent", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    body: JSON.stringify(payload),
    signal: init.signal,
  });
}

export async function commitChatSession(sessionId, payload) {
  return readJson(`/chat/sessions/${encodeURIComponent(sessionId)}/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function streamChatSession(sessionId, message, signal) {
  const path = sessionId
    ? `/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`
    : "/chat/sessions/stream";
  return fetchPath(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
}
