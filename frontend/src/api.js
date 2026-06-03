export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8024";

export async function fetchPath(path, init) {
  const res = await fetch(`${API_BASE}${path}`, init);
  return res;
}

export async function getReport() {
  const res = await fetchPath("/report");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getHealth() {
  const res = await fetchPath("/health");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function postIntent(payload, init = {}) {
  const res = await fetchPath("/intent", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    body: JSON.stringify(payload),
    signal: init.signal,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function commitChatSession(sessionId, payload) {
  const res = await fetchPath(`/chat/sessions/${encodeURIComponent(sessionId)}/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
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
