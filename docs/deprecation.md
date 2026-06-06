# 弃用计划

Tianjun 保持兼容路由可用，同时引导所有新客户端使用官方的基于会话的聊天 API。

## 已弃用的路由

| 已弃用路由 | 替代方案 | 备注 |
| --- | --- | --- |
| `POST /intent` | `POST /chat/sessions` 后跟明确提交 | 旧版一次性网关；为旧 Dashboard 和演示保留 |
| `POST /chat` | `POST /chat/sessions` | 旧的非会话风格聊天入口 |
| `POST /hermes/chat` | `POST /chat/sessions` | 旧的 Hermes 包装器响应格式 |
| `POST /hermes/chat/stream` | `POST /chat/sessions/stream` | 旧的 SSE 事件格式 |
| `GET /hermes/status` | `GET /health` | 状态兼容别名 |

## 迁移规则

- 新的 Dashboard 代码必须只调用 `/chat/sessions*`。
- MCP 工具必须使用官方 HTTP 路由。
- 遗留路由必须保留在遗留适配器中并且必须经过测试。
- 只有在下游脚本和演示不再调用已弃用路径后才能移除。

Safety note: `/intent` defaults to preview. If a legacy caller sends `dry_run=false`, the request must also include `confirmed=true` or `confirmed_by_user_button=true`; otherwise the server returns 403 and does not commit a policy.
