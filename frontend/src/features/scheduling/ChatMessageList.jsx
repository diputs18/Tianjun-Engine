import { IconRobot, IconUser } from "@arco-design/web-react/icon";
import { ToolTraceTimeline } from "./ToolTraceTimeline.jsx";

export function ChatMessageList({ messages, trace, streaming }) {
  if (!messages.length) {
    return (
      <div className="tj-ai-message-list tj-ai-message-list-empty">
        <div className="tj-ai-empty-hero">
          <div className="tj-ai-empty-orb">
            <IconRobot />
          </div>
          <p>请输入调度需求，AI 将自动完成意图理解、生成策略与策略仿真。</p>
        </div>
      </div>
    );
  }

  const showTrace = trace.length > 0 || streaming;

  return (
    <div className="tj-ai-message-list">
      {messages.map((message, index) => {
        const isLastAssistant = message.role === "assistant" && index === messages.length - 1;
        const hasContent = Boolean(String(message.content ?? "").trim());

        return (
          <div key={message.id} className={`tj-ai-turn ${message.role}`}>
            <span className="tj-ai-avatar">
              {message.role === "user" ? <IconUser /> : <IconRobot />}
            </span>
            <div className={`tj-ai-message ${message.role} ${!hasContent ? "is-empty" : ""}`}>
              {isLastAssistant && showTrace ? <ToolTraceTimeline trace={trace} streaming={streaming} /> : null}
              {hasContent ? <p>{message.content}</p> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
