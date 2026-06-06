# 架构

Tianjun Engine 围绕少量公共适配器和一个中央应用门面组织。

## 运行时流程

1. 用户与 Dashboard、CLI 聊天或 MCP 主机交互。
2. `ChatRuntime` 将通用聊天与调度需求分离。
3. 需求和策略工具调用 `CentralControlPlane`。
4. 控制平面协调策略生成、确定性调度、任务租约创建和执行反馈。
5. 模拟节点、CloudSimPlus 桥接器或真实节点代理注册资源清单并报告进度/结果。
6. 报告和健康数据通过 HTTP 暴露并由 Dashboard 渲染。

## 主要子系统

| 子系统 | 职责 |
| --- | --- |
| HTTP 接口 | 官方 REST/SSE API、Dashboard 静态服务、遗留兼容适配器 |
| Dashboard | 使用官方 API 的静态 HTML/CSS/JS 控制界面 |
| 聊天运行时 | Hermes 风格对话、策略选项选择、明确提交流程 |
| 控制平面门面 | HTTP、聊天、MCP 和测试使用的稳定 API |
| 调度引擎 | 确定性节点过滤和多目标评分 |
| 策略工作流 | 需求解析、策略起草、模拟、反馈优化 |
| 节点/租约流程 | 节点注册、心跳、任务生命周期、租约/结果报告 |
| MCP 适配器 | 通过 HTTP 包装器向 MCP 主机暴露工具 |

## 控制平面职责映射

| 领域 | 当前门面方法 |
| --- | --- |
| 节点和拓扑 | `register_node`、`record_heartbeat`、`register_topology`、`_node_report_payload`、陈旧节点恢复 |
| 任务和租约 | `submit_task`、`preview_task`、`schedule_pending_task`、`request_lease`、进度/结果/取消报告 |
| 需求 | `parse_requirement`、需求会话开始/继续/读取辅助方法 |
| 策略工作流 | 起草、比较、模拟、解释/获取、提交、权重更新 |
| 反馈 | 解析、记录、根据反馈优化 |
| 报告 | `build_report`、`current_tick`、活动运行负载、SLA 摘要 |
| 持久化 | SQLite 恢复和每个实体的持久化辅助方法 |

长期方向是保持 `CentralControlPlane` 作为门面，同时为节点注册、任务租约生命周期、策略工作流和需求对话提取服务。门面 API 对 HTTP、ChatRuntime、MCP 和现有测试保持稳定。
