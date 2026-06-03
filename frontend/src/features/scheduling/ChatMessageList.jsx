import { Empty } from "@arco-design/web-react";

export function ChatMessageList({ messages }) {
  if (!messages.length) return <Empty className="tj-ai-empty" description="No messages" />;
  return (
    <div className="tj-ai-message-list">
      {messages.map((message) => (
        <div key={message.id} className={`tj-ai-message ${message.role}`}>
          <span>{message.role === "user" ? "Operator" : "Tianjun Copilot"}</span>
          <p>{message.content || "..."}</p>
        </div>
      ))}
    </div>
  );
}
