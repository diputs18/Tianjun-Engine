# 弃用计划

Tianjun 保持兼容路由可用，同时引导所有新客户端使用官方的基于会话的聊天 API。

## 已弃用的路由

| 已弃用路由 | 替代方案 | 备注 |
| --- | --- | --- |
| `POST /intent` | `POST /chat/sessions` 后跟明确提交 | 旧版一次性网关；仅为外部旧客户端和旧演示脚本保留 |
| `POST /chat` | `POST /chat/sessions` | 旧的非会话风格聊天入口 |
| `POST /hermes/chat` | `POST /chat/sessions` | 旧的 Hermes 包装器响应格式 |
| `POST /hermes/chat/stream` | `POST /chat/sessions/stream` | 旧的 SSE 事件格式 |
| `GET /hermes/status` | `GET /health` | 状态兼容别名 |

## 迁移规则

- 新的 Dashboard 代码必须只调用 `/chat/sessions*`。
- MCP 工具必须使用官方 HTTP 路由。
- 遗留路由必须保留在遗留适配器中并且必须经过测试。
- 只有在下游脚本和演示不再调用已弃用路径后才能移除。

安全说明：`/intent` 默认只预览。如果遗留调用方发送 `dry_run=false`，请求必须同时包含 `confirmed=true` 或 `confirmed_by_user_button=true`；否则服务器返回 403，且不会提交策略。

## 遗留实现边界

已弃用路由只在 `src/tianjun/interfaces/http/legacy_routes.py` 中实现。新的 Dashboard 和 CLI 代码必须使用官方路由，不应新增对 `/intent`、`/chat` 或 `/hermes/*` 的调用。
