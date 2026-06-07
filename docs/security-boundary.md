# 安全边界

Tianjun 是本地研究和演示控制平面。生产使用需要额外的身份验证、授权、隔离、审计和执行器加固。

## 确认边界

以下操作需要明确的确认参数或 Dashboard 按钮流程：

- `POST /policies/commit`
- `POST /tasks/{task_id}/schedule`
- `POST /policy-weights`
- MCP `commit_policy(..., confirmed=true)`
- MCP `schedule_pending_task(..., confirmed=true)`

“确认”等自然语言消息不足以绕过 API 确认边界。

## 执行器边界

默认配置保持进程、Docker 和 Kubernetes 执行器处于禁用状态。只有在具有明确的主机级隔离、命令允许列表、资源限制和审计日志的情况下才能启用它们。

## 密钥边界

不要将真实的 API 密钥写入仓库文件。推荐使用：

```powershell
python -B main.py secrets --config configs\tianjun.example.toml set deepseek --api-key "..."
```

环境变量和被忽略的本地 `.env` 文件支持 CI 或容器配置。

## LLM 边界

LLM 可以解释、总结和帮助解析用户需求。它不得捏造资源清单、提交任务、变更策略状态或创建租约，除非通过明确的工具/API 调用。

## 服务职责边界

安全敏感的状态迁移应保留在已抽取的服务中：

- `PolicyWorkflowService`：策略提交和基于反馈的策略变更。
- `TaskLeaseService`：任务调度和租约激活。
- `NodeRegistry`：节点心跳和节点状态变更。
- `RequirementDialogueService`：需求会话状态变更。

`CentralControlPlane` 为调用方暴露稳定 facade 方法，但已经迁移的服务逻辑不应复制回 facade。
