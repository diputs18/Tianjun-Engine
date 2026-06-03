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
    if (chat.streaming) return "生成中";
    if (canCommit) return "待确认";
    return "就绪";
  }, [canCommit, chat.streaming]);

  const submit = () => {
    void chat.sendMessage(draft);
    setDraft("");
  };

  return (
    <div className="tj-ai-console">
      <div className="tj-ai-topbar">
        <div>
          <Tag color={state.llmEnabled ? "green" : "orange"}>{state.llmEnabled ? "LLM 已启用" : "规则回退"}</Tag>
          <Tag color="arcoblue">{status}</Tag>
          {chat.sessionId ? <Tag>会话 {chat.sessionId}</Tag> : null}
        </div>
        <Space>
          <Button onClick={chat.stop} disabled={!chat.streaming}>停止生成</Button>
          <Button icon={<IconRefresh />} onClick={chat.reset} disabled={chat.streaming} />
          <Button type="primary" icon={<IconCheckCircle />} disabled={!canCommit} onClick={() => setConfirmOpen(true)}>正式提交</Button>
        </Space>
      </div>
      {chat.error ? <Alert type="error" content={chat.error} className="tj-ai-alert" /> : null}
      <div className="tj-ai-grid">
        <section className="tj-ai-chat-panel">
          <div className="tj-ai-panel-head">
            <IconRobot />
            <div>
              <b>AI 调度对话</b>
              <span>通过 `/chat/sessions/*` 流式驱动，并由 React 状态管理。</span>
            </div>
          </div>
          <ChatMessageList messages={chat.messages} />
          <div className="tj-ai-composer">
            <TextArea
              value={draft}
              onChange={setDraft}
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder="示例：在东部区域部署在线推理业务，P95 时延低于 80ms，总成本控制在 2 万以内。"
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
            />
            <Button type="primary" icon={<IconSend />} loading={chat.streaming} disabled={!draft.trim()} onClick={submit}>发送</Button>
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
