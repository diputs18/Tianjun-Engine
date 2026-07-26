# HTTP API

官方 API 基于标准库 HTTP 服务器上的 JSON。除非路由是 SSE 流或 Dashboard HTML/静态内容，否则请求和响应体均为 UTF-8 JSON。

## 官方路由

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 进程健康和去敏后的依赖状态；始终返回可解析状态 |
| GET | `/ready` | 就绪检查；依赖未就绪时返回 503 |
| GET | `/report` | 完整控制平面状态，保留给 MCP 和兼容客户端 |
| GET | `/report/summary` | Dashboard 总览和顶部状态的精简报告 |
| GET | `/report/scheduling` | 调度决策页所需节点与决策报告 |
| GET | `/report/topology` | 拓扑、VM 遥测和路径报告 |
| GET | `/report/tasks?limit=50&cursor=0` | 分页任务执行报告 |
| GET | `/report/model` | 模型、权重与策略历史报告 |
| GET | `/dashboard` | 静态 Dashboard 壳页面 |
| GET | `/chat/sessions/{session_id}` | 读取聊天会话状态 |
| POST | `/chat/sessions` | 开始聊天会话 |
| POST | `/chat/sessions/stream` | 通过 SSE 开始或继续聊天 |
| POST | `/chat/sessions/{session_id}/messages` | 继续聊天会话 |
| POST | `/chat/sessions/{session_id}/messages/stream` | 通过 SSE 继续聊天会话 |
| POST | `/chat/sessions/{session_id}/commit` | 提交所选聊天策略 |
| POST | `/requirements/parse` | 解析单个需求 |
| GET | `/conversations/{session_id}` | 读取结构化需求对话 |
| POST | `/conversations/start` | 开始结构化需求对话 |
| POST | `/conversations/{session_id}/continue` | 继续结构化需求对话 |
| POST | `/conversations/{session_id}/draft` | 从需求对话起草策略 |
| GET | `/policies/{policy_id}` | 解释/读取策略 |
| POST | `/policies/draft` | 起草策略 |
| POST | `/policies/compare` | 比较策略选项 |
| POST | `/policies/simulate` | 模拟策略 |
| POST | `/policies/commit` | 提交策略；需要明确确认 |
| POST | `/policies/{policy_id}/optimize` | 根据反馈优化策略 |
| POST | `/policies/{policy_id}/resimulate` | 重新运行策略模拟 |
| POST | `/policy-weights` | 更新调度器权重；需要明确确认 |
| POST | `/feedback/parse` | 解析用户反馈 |
| POST | `/feedback` | 记录用户反馈 |
| POST | `/topology/register` | 注册物理拓扑 |
| POST | `/nodes/register` | 注册节点清单 |
| POST | `/nodes/heartbeat` | 更新节点心跳和遥测数据 |
| POST | `/tasks` | 提交任务 |
| POST | `/tasks/{task_id}/schedule` | 调度待处理任务；需要明确确认 |
| POST | `/leases/next` | 节点代理租约轮询 |
| POST | `/task-runs/progress` | 报告任务进度 |
| POST | `/task-runs/result` | 报告最终任务结果 |
| POST | `/task-runs/cancel` | 取消活动任务运行 |
| POST | `/schedule/preview` | CloudSimPlus 兼容的调度预览 |
| POST | `/schedule/commit` | CloudSimPlus 兼容的直接提交 |

## 遗留路由

这些路由为了兼容性仍然可用，但已弃用：

| 方法 | 路径 | 替代方案 |
| --- | --- | --- |
| POST | `/intent` | `/chat/sessions` 或 `/chat/sessions/stream` |
| POST | `/chat` | `/chat/sessions` |
| POST | `/hermes/chat` | `/chat/sessions` |
| POST | `/hermes/chat/stream` | `/chat/sessions/stream` |
| GET | `/hermes/status` | `/health` |

新客户端应使用官方路由。遗留路由集中在 HTTP 遗留适配器中，并由路由回归测试覆盖。

安全说明：`/intent` 默认只预览。如果遗留调用方发送 `dry_run=false`，请求必须同时包含 `confirmed=true` 或 `confirmed_by_user_button=true`，否则服务器返回 403 且不会提交策略。

## 实现边界

HTTP 路由调用 `CentralControlPlane` facade。facade 将已迁移的行为转发给应用服务：

- `NodeRegistry` 处理节点注册和心跳路由。
- `TaskLeaseService` 处理任务和租约生命周期路由。
- `RequirementDialogueService` 处理需求解析和需求会话路由。
- `PolicyWorkflowService` 处理策略起草、比较、模拟、提交和反馈路由。

本文只描述公开 API 行为；服务拆分不改变路由语义。

Dashboard 只轮询按页面拆分的报告。所有报告视图都带有 `report_version`、`resource_snapshot_version` 和 `generated_at`，客户端可据此识别跨请求快照差异。完整 `/report` 不再用于浏览器高频轮询。

CloudSimPlus 心跳中的 `telemetry.cpu_utilization`、`ram_utilization` 和 `bandwidth_utilization` 会规范化为节点的 `runtime_utilization`。未上报的指标保持 `null`，Dashboard 显示为 `--`，不会生成伪实时值。
