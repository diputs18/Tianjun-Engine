import { Alert, Button, Input } from "@arco-design/web-react";
import {
  IconAttachment,
  IconDelete,
  IconSend,
  IconSettings,
  IconStar,
} from "@arco-design/web-react/icon";
import { useState } from "react";
import { useChatStream } from "../../hooks/useChatStream.js";
import { useControlPlaneContext } from "../../layout/ControlPlaneProvider.jsx";
import { ChatMessageList } from "./ChatMessageList.jsx";
import { CommitConfirmDialog } from "./CommitConfirmDialog.jsx";
import { PolicyWorkspace } from "./PolicyWorkspace.jsx";

const { TextArea } = Input;

export function AICopilotPanel() {
  const { refresh } = useControlPlaneContext();
  const [draft, setDraft] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const chat = useChatStream({ onCommitted: refresh });
  const canCommit = Boolean(chat.requiresUserButton && chat.commitPolicyId);

  const submit = () => {
    void chat.sendMessage(draft);
    setDraft("");
  };

  return (
    <div className="tj-ai-console">
      {chat.error ? <Alert type="error" content={chat.error} className="tj-ai-alert" /> : null}
      <div className="tj-ai-workbench-grid">
        <section className="tj-ai-chat-panel">
          <ChatMessageList messages={chat.messages} trace={chat.toolTrace} streaming={chat.streaming} />
          <div className="tj-ai-composer-shell">
            <TextArea
              value={draft}
              onChange={setDraft}
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={chat.committing}
              placeholder="请输入您的调度需求..."
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
            />
            <Button className="tj-ai-send-button" type="text" icon={<IconSend />} loading={chat.streaming} disabled={!draft.trim() || chat.committing} onClick={submit} />
            <div className="tj-ai-composer-tools">
              <Button type="text" icon={<IconAttachment />} />
              <Button type="text" icon={<IconSettings />} />
              <Button type="text" icon={<IconStar />} />
              <Button type="text" icon={<IconDelete />} onClick={chat.reset} disabled={chat.streaming || chat.committing}>清空对话</Button>
            </div>
          </div>
        </section>
        <aside className="tj-ai-side-panel">
          <PolicyWorkspace
            artifacts={chat.artifacts}
            commitPolicyId={chat.commitPolicyId}
            canCommit={canCommit && !chat.streaming && !chat.committing}
            committing={chat.committing}
            onCommit={() => setConfirmOpen(true)}
          />
        </aside>
      </div>
      <CommitConfirmDialog
        visible={confirmOpen}
        policyId={chat.commitPolicyId}
        loading={chat.committing}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          await chat.commitPolicy();
          setConfirmOpen(false);
        }}
      />
    </div>
  );
}
