import { IconRobot, IconUser } from "@arco-design/web-react/icon";
import { ToolTraceTimeline } from "./ToolTraceTimeline.jsx";

export function ChatMessageList({ messages, trace, streaming }) {
  if (!messages.length) return <div className="tj-ai-message-list" />;
  const showTrace = trace.length > 0 || streaming;
  return (
    <div className="tj-ai-message-list">
      {messages.map((message, index) => {
        const isLastAssistant = message.role === "assistant" && index === messages.length - 1;
        return (
          <div key={message.id} className={`tj-ai-turn ${message.role}`}>
            <span className="tj-ai-avatar">{message.role === "user" ? <IconUser /> : <IconRobot />}</span>
            <div className={`tj-ai-message ${message.role}`}>
              {isLastAssistant && showTrace ? <ToolTraceTimeline trace={trace} streaming={streaming} /> : null}
              <p>{message.content || "正在生成..."}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
