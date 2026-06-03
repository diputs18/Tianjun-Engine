import { useCallback, useRef, useState } from "react";
import { commitChatSession, streamChatSession } from "../services/api.js";

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  content: "请描述业务类型、部署区域、时延目标、预算和策略约束，天钧会将你的意图整理为可调度的策略草案。",
};

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
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      const parsed = block ? parseEventBlock(block) : null;
      if (parsed) onEvent(parsed.payload.type ? parsed.payload : { ...parsed.payload, type: parsed.event });
      boundary = buffer.indexOf("\n\n");
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

function upsertToolTrace(trace, event) {
  const key = `${event.tool}-${trace.length}`;
  if (event.type === "tool_start") {
    return [...trace, { id: key, tool: event.tool, label: event.label ?? event.tool, status: "running", summary: "执行中" }];
  }
  const index = trace.findLastIndex((item) => item.tool === event.tool && item.status === "running");
  if (index < 0) {
    return [...trace, { id: key, tool: event.tool, label: event.label ?? event.tool, status: "done", summary: event.summary ?? "已完成" }];
  }
  return trace.map((item, itemIndex) => (
    itemIndex === index ? { ...item, status: "done", summary: event.summary ?? "已完成" } : item
  ));
}

export function useChatStream({ onCommitted } = {}) {
  const abortRef = useRef(null);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([welcomeMessage]);
  const [toolTrace, setToolTrace] = useState([]);
  const [artifacts, setArtifacts] = useState({});
  const [requiresUserButton, setRequiresUserButton] = useState(false);
  const [commitPolicyId, setCommitPolicyId] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = useCallback(async (text) => {
    const message = text.trim();
    if (!message || streaming) return;
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
          setToolTrace((current) => [...current, { id: messageId("llm"), tool: "llm", label: "LLM 意图解析", status: "running", summary: "正在解析需求" }]);
          return;
        }
        if (event.type === "llm_done" || event.type === "llm_fallback") {
          setToolTrace((current) => current.map((item) => (
            item.tool === "llm" && item.status === "running"
              ? { ...item, status: event.type === "llm_done" ? "done" : "error", summary: event.detail ?? event.reason ?? "已结束" }
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
      setStreaming(false);
    }
  }, [sessionId, streaming]);

  const commitPolicy = useCallback(async () => {
    if (!sessionId || !commitPolicyId) return;
    setError(null);
    setStreaming(true);
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
      setStreaming(false);
    }
  }, [commitPolicyId, onCommitted, sessionId]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(null);
    setMessages([welcomeMessage]);
    setToolTrace([]);
    setArtifacts({});
    setRequiresUserButton(false);
    setCommitPolicyId(null);
    setError(null);
    setStreaming(false);
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return {
    artifacts,
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
