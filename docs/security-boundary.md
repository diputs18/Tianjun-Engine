# 安全边界

Tianjun 是本地研究和演示控制平面。生产使用需要额外的身份验证、授权、隔离、审计和执行器加固。

服务默认绑定 `127.0.0.1`。当前版本没有远程访问鉴权，因此不得直接暴露到公网或不可信局域网。Dashboard 响应包含 CSP、禁止嗅探和禁止嵌入等基础安全头，但这些不能替代身份验证。CSP 允许页面现有的数据驱动内联样式，用于拓扑坐标和指标进度条；脚本仍只允许同源模块。

`/health` 返回去敏后的运行状态；`/ready` 用于依赖就绪检查。模型绝对路径、密钥来源和密钥指纹不会通过健康接口返回。

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

## MCP 状态边界

Dashboard 的 MCP 工具状态表示控制平面收到了带 `X-Tianjun-Caller: external_mcp` 和工具名的 HTTP 请求，并记录了结果。它是调用审计，不是经过身份认证的 MCP 进程在线证明。若系统需要远程或多租户使用，应增加独立的 MCP 会话身份、心跳和请求签名。
