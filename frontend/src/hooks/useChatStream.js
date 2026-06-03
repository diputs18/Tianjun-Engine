import { useCallback, useRef, useState } from "react";
import { commitChatSession, streamChatSession } from "../services/api.js";

function parseEventBlock(block) {
  let event = "message";
  const data = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  try {
    return { event, payload: JSON.parse(data.join("\n")) };
  } catch {
    return { event, payload: { type: event, text: data.join("\n") } };
  }
}

async function readEventStream(response, onEvent) {
  if (!response.body) throw new Error("chat stream response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.search(/\r?\n\r?\n/);
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary).trim();
      const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0].length ?? 2;
      buffer = buffer.slice(boundary + separator);
      const parsed = block ? parseEventBlock(block) : null;
      if (parsed) onEvent(parsed.payload.type ? parsed.payload : { ...parsed.payload, type: parsed.event });
      boundary = buffer.search(/\r?\n\r?\n/);
    }
  }
  const trailing = buffer.trim();
  if (trailing) {
    const parsed = parseEventBlock(trailing);
    if (parsed) onEvent(parsed.payload.type ? parsed.payload : { ...parsed.payload, type: parsed.event });
  }
}

function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function appendAssistantDelta(messages, id, delta) {
  return messages.map((message) => (
    message.id === id ? { ...message, content: `${message.content}${delta}` } : message
  ));
}

function createTraceId(event) {
  return event.id ?? event.trace_id ?? event.run_id ?? `${event.tool}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertToolTrace(trace, event) {
  if (event.type === "tool_start") {
    return [...trace, { id: createTraceId(event), tool: event.tool, label: event.label ?? event.tool, status: "running", summary: event.summary ?? "" }];
  }
  const index = trace.findLastIndex((item) => item.tool === event.tool && item.status === "running");
  if (index < 0) {
    return [...trace, { id: createTraceId(event), tool: event.tool, label: event.label ?? event.tool, status: "done", summary: event.summary ?? "" }];
  }
  return trace.map((item, itemIndex) => (
    itemIndex === index ? { ...item, status: "done", summary: event.summary ?? "" } : item
  ));
}

export function useChatStream({ onCommitted } = {}) {
  const abortRef = useRef(null);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [toolTrace, setToolTrace] = useState([]);
  const [artifacts, setArtifacts] = useState({});
  const [requiresUserButton, setRequiresUserButton] = useState(false);
  const [commitPolicyId, setCommitPolicyId] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = useCallback(async (text) => {
    const message = text.trim();
    if (!message || streaming || committing) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const assistantId = messageId("assistant");
    setMessages((current) => [
      ...current,
      { id: messageId("user"), role: "user", content: message },
      { id: assistantId, role: "assistant", content: "" },
    ]);
    setToolTrace([]);
    setError(null);
    setStreaming(true);

    try {
      const response = await streamChatSession(sessionId, message, controller.signal);
      if (!response.ok) throw new Error(await response.text());
      await readEventStream(response, (event) => {
        if (event.type === "session") {
          setSessionId(event.session?.session_id ?? event.session_id ?? null);
          return;
        }
        if (event.type === "artifacts") {
          setArtifacts((current) => ({ ...current, ...(event.artifacts ?? {}) }));
          return;
        }
        if (event.type === "assistant_delta") {
          setMessages((current) => appendAssistantDelta(current, assistantId, String(event.delta ?? "")));
          return;
        }
        if (event.type === "tool_start" || event.type === "tool_done" || event.type === "tool_result") {
          setToolTrace((current) => upsertToolTrace(current, event));
          return;
        }
        if (event.type === "llm_start") {
          setToolTrace((current) => [...current, { id: messageId("llm"), tool: "llm", label: "意图理解", status: "running", summary: "" }]);
          return;
        }
        if (event.type === "llm_done" || event.type === "llm_fallback") {
          setToolTrace((current) => current.map((item) => (
            item.tool === "llm" && item.status === "running"
              ? { ...item, status: event.type === "llm_done" ? "done" : "error", summary: event.detail ?? event.reason ?? "" }
              : item
          )));
          return;
        }
        if (event.type === "error") {
          setError(event.message ?? "对话流处理失败");
          return;
        }
        if (event.type === "done" && event.result) {
          setSessionId(event.result.session?.session_id ?? null);
          setRequiresUserButton(Boolean(event.result.requires_user_button));
          setCommitPolicyId(event.result.commit_policy_id ?? null);
          setArtifacts((current) => ({ ...current, ...(event.result.artifacts ?? {}) }));
          setMessages((current) => current.map((item) => (
            item.id === assistantId && !item.content
              ? { ...item, content: event.result.message ?? "" }
              : item
          )));
        }
      });
    } catch (nextError) {
      if (nextError.name !== "AbortError") {
        setError(nextError.message);
        setMessages((current) => appendAssistantDelta(current, assistantId, `\n${nextError.message}`));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setStreaming(false);
    }
  }, [committing, sessionId, streaming]);

  const commitPolicy = useCallback(async () => {
    if (!sessionId || !commitPolicyId || committing || streaming) return;
    setError(null);
    setCommitting(true);
    try {
      const result = await commitChatSession(sessionId, { policy_id: commitPolicyId });
      setRequiresUserButton(false);
      setCommitPolicyId(null);
      setArtifacts((current) => ({ ...current, commit: result.artifacts?.commit, dashboard_payload: result.dashboard_payload }));
      setMessages((current) => [...current, { id: messageId("commit"), role: "assistant", content: result.message ?? "策略已正式提交。" }]);
      await onCommitted?.();
    } catch (nextError) {
      setError(nextError.message);
    } finally {
      setCommitting(false);
    }
  }, [commitPolicyId, committing, onCommitted, sessionId, streaming]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(null);
    setMessages([]);
    setToolTrace([]);
    setArtifacts({});
    setRequiresUserButton(false);
    setCommitPolicyId(null);
    setError(null);
    setStreaming(false);
    setCommitting(false);
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  return {
    artifacts,
    committing,
    commitPolicy,
    commitPolicyId,
    error,
    messages,
    requiresUserButton,
    reset,
    sendMessage,
    sessionId,
    stop,
    streaming,
    toolTrace,
  };
}
