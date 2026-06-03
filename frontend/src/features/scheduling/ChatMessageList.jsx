import { Empty } from "@arco-design/web-react";

export function ChatMessageList({ messages }) {
  if (!messages.length) return <Empty className="tj-ai-empty" description="暂无消息" />;
  return (
    <div className="tj-ai-message-list">
      {messages.map((message) => (
        <div key={message.id} className={`tj-ai-message ${message.role}`}>
          <span>{message.role === "user" ? "操作员" : "天钧副驾"}</span>
          <p>{message.content || "正在生成..."}</p>
        </div>
      ))}
    </div>
  );
}
