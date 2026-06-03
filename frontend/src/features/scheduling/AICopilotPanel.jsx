import { Alert, Button, Input, Space, Tag } from "@arco-design/web-react";
import { IconCheckCircle, IconRefresh, IconRobot, IconSend } from "@arco-design/web-react/icon";
import { useMemo, useState } from "react";
import { useChatStream } from "../../hooks/useChatStream.js";
import { useControlPlaneContext } from "../../layout/ControlPlaneProvider.jsx";
import { ChatMessageList } from "./ChatMessageList.jsx";
import { CommitConfirmDialog } from "./CommitConfirmDialog.jsx";
import { PolicyWorkspace } from "./PolicyWorkspace.jsx";
import { ToolTraceTimeline } from "./ToolTraceTimeline.jsx";

const { TextArea } = Input;

export function AICopilotPanel() {
  const { refresh, state } = useControlPlaneContext();
  const [draft, setDraft] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const chat = useChatStream({ onCommitted: refresh });
  const canCommit = Boolean(chat.requiresUserButton && chat.commitPolicyId);
  const status = useMemo(() => {
    if (chat.streaming) return "streaming";
    if (canCommit) return "awaiting confirmation";
    return "ready";
  }, [canCommit, chat.streaming]);

  const submit = () => {
    void chat.sendMessage(draft);
    setDraft("");
  };

  return (
    <div className="tj-ai-console">
      <div className="tj-ai-topbar">
        <div>
          <Tag color={state.llmEnabled ? "green" : "orange"}>{state.llmEnabled ? "LLM enabled" : "rules fallback"}</Tag>
          <Tag color="arcoblue">{status}</Tag>
          {chat.sessionId ? <Tag>session {chat.sessionId}</Tag> : null}
        </div>
        <Space>
          <Button icon={<IconRefresh />} onClick={chat.reset} disabled={chat.streaming} />
          <Button type="primary" icon={<IconCheckCircle />} disabled={!canCommit} onClick={() => setConfirmOpen(true)}>Commit</Button>
        </Space>
      </div>
      {chat.error ? <Alert type="error" content={chat.error} className="tj-ai-alert" /> : null}
      <div className="tj-ai-grid">
        <section className="tj-ai-chat-panel">
          <div className="tj-ai-panel-head">
            <IconRobot />
            <div>
              <b>AI scheduling dialogue</b>
              <span>Streamed by /chat/sessions/* with React state.</span>
            </div>
          </div>
          <ChatMessageList messages={chat.messages} />
          <div className="tj-ai-composer">
            <TextArea
              value={draft}
              onChange={setDraft}
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder="Example: deploy an online inference workload in east region, P95 latency under 80ms, keep cost below 20k."
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
            />
            <Button type="primary" icon={<IconSend />} loading={chat.streaming} disabled={!draft.trim()} onClick={submit}>Send</Button>
          </div>
        </section>
        <aside className="tj-ai-side-panel">
          <PolicyWorkspace artifacts={chat.artifacts} commitPolicyId={chat.commitPolicyId} />
          <ToolTraceTimeline trace={chat.toolTrace} />
        </aside>
      </div>
      <CommitConfirmDialog
        visible={confirmOpen}
        policyId={chat.commitPolicyId}
        loading={chat.streaming}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          await chat.commitPolicy();
          setConfirmOpen(false);
        }}
      />
    </div>
  );
}
