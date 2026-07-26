# 架构

Tianjun Engine 围绕公共适配器、中央控制平面门面和可测试的应用服务组织。HTTP、Dashboard、ChatRuntime 和 MCP 都调用稳定的 `CentralControlPlane` facade；已经迁出的业务生命周期由独立服务维护。

## 运行时流程

1. 用户通过 Dashboard、CLI 聊天或 MCP 主机发起请求。
2. `ChatRuntime` 区分普通聊天、需求解析、策略选择和提交确认。
3. HTTP、聊天和 MCP 工具统一调用 `CentralControlPlane`。
4. 控制平面门面协调策略工作流、确定性调度、任务租约和执行反馈。
5. CloudSimPlus 桥接器或真实节点代理注册节点、发送心跳、领取任务并报告进度/结果。
6. `/report`、`/health` 和 Dashboard 展示节点、任务、策略、执行和模型状态。

## 主要子系统

| 子系统 | 职责 |
| --- | --- |
| HTTP 接口 | 官方 REST/SSE API、Dashboard 静态服务、遗留兼容适配器 |
| Dashboard | 使用官方 API 的静态 HTML/CSS/JS 控制界面 |
| 聊天运行时 | Hermes 风格对话、策略选项选择、明确提交流程 |
| MCP 适配器 | 通过 HTTP 包装器向 MCP 主机暴露工具 |
| 控制平面门面 | 为 HTTP、聊天、MCP 和测试提供稳定 API |
| 调度引擎 | 确定性节点过滤和多目标评分 |
| 仿真/节点代理 | 节点注册、心跳、任务领取、进度和结果回报 |

## 控制平面服务边界

| 服务 | 当前职责 |
| --- | --- |
| `NodeRegistry` | 节点注册、心跳、节点遥测变更、节点持久化 |
| `TaskLeaseService` | 任务提交、预览、pending 调度、租约发放、ACK、TTL 续期/回收和并发幂等 |
| `LifecycleSweeper` | 与用户流量解耦地回收过期节点和租约，并随 HTTP 服务安全启停 |
| `RequirementDialogueService` | 需求解析、需求会话开始/继续/读取、地域可用性载荷 |
| `PolicyWorkflowService` | 策略起草、候选比较、模拟、提交、反馈解析、反馈记录、反馈优化 |
| `src/tianjun/cli/commands/` | 所有 CLI 命令处理器 |

`CentralControlPlane` 保留 facade 方法、共享状态、拓扑注册、策略权重更新以及执行进度/结果回报等跨领域逻辑。数据库模式/迁移、控制面恢复、批输入校验、聊天模型/常量与拓扑几何已拆为独立模块；已经迁移到服务中的业务流程不应复制回门面类。

## CloudSimPlus 仿真链路

标准演示链路使用 `examples/cloudsimplus/` 中的 Java CloudSimPlus 桥接器。它会：

- 调用 `/topology/register` 注册 DCI 物理拓扑。
- 调用 `/nodes/register` 注册 CloudSimPlus 仿真 VM 节点。
- 持续调用 `/nodes/heartbeat` 上报在线状态。
- 通过 `/schedule/commit` 请求 Tianjun 控制平面做调度决策。
- 通过 `/leases/next` 和 `/leases/ack` 领取并确认带 TTL 的任务租约。
- 在 CloudSimPlus 仿真完成后通过携带 `lease_id`/`result_id` 的 `/task-runs/result` 幂等回报执行结果。

完整启动命令见 [README.md](../README.md)。

## 兼容层边界

遗留路由只应存在于 `src/tianjun/interfaces/http/legacy_routes.py`。新 Dashboard、CLI、MCP 和文档示例都应使用官方路由，尤其是 `/chat/sessions*` 聊天流程。
