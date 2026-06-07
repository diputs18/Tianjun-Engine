# Tianjun Engine

Tianjun Engine 是一个本地优先的算网调度控制平面原型。它把自然语言需求对话、确定性多目标调度、可选 ML 辅助预测、执行反馈、MCP 工具和静态 Dashboard 连接成一个可运行的研究系统。

本项目用于研究、演示和架构实验，并非生产级云平台。资源清单、定价、拓扑和执行事实必须来自已注册节点、CloudSimPlus 桥接器或真实节点代理；LLM 可以解释和帮助解析意图，但不能在没有明确确认路径的情况下捏造控制平面事实或提交工作。

## 快速开始

### 0. 安装依赖

需要 Python 3.10 或更新版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mcp,ml-runtime]"
```

### 1. 配置并验证 LLM

不要把真实 API Key 写入仓库文件。推荐使用本地 secrets 文件：

```powershell
python -B main.py secrets --config configs\tianjun.example.toml set deepseek --api-key "your_api_key_here"
python -B main.py llm-check --config configs\tianjun.example.toml
```

### 2. Windows 启动脚本

Windows 用户可以使用统一脚本入口，或使用后面的指令：

```cmd
tianjun.bat start
tianjun.bat restart
tianjun.bat stop
tianjun.bat open
tianjun.bat smoke
```

`tianjun.bat start` 会在 LLM 校验通过后启动控制平面、MCP server 并打开 Dashboard，不会自动启动仿真节点。`tianjun.bat smoke` 只做离线 smoke test，不代表完整启动。

### 3. 启动控制平面

在第一个终端运行：

```powershell
python -B main.py serve `
  --config configs\tianjun.example.toml `
  --default-execution-mode simulation `
  --host 127.0.0.1 `
  --port 8024
```

验证服务：

```powershell
Invoke-RestMethod http://127.0.0.1:8024/health
Invoke-RestMethod http://127.0.0.1:8024/report
```

### 4. 启动 Java CloudSimPlus 仿真节点

标准演示链路使用 Java CloudSimPlus 仿真节点。CloudSimPlus 桥接器和参考实验位于 `examples/cloudsimplus/`：

```text
examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java
examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java
examples/cloudsimplus/src/main/resources/huawei-dci-reference.brite
```

将这些文件放入本地 CloudSim Plus Examples 工程对应路径后运行实验，并把 Tianjun 控制平面地址作为第一个参数传入：

```powershell
java org.cloudsimplus.examples.HuaweiDciTianjunExperiment http://127.0.0.1:8024 normal
```

该实验会创建 24 个仿真 VM，注册 DCI 拓扑和节点，持续发送心跳，通过 Tianjun 控制平面提交调度任务，并在 CloudSimPlus 仿真完成后回传执行结果。它是当前推荐的后台常驻仿真拓扑：只要该 Java 进程持续运行，控制平面就可以实时接收待调度任务，节点会通过 `/leases/next` 领取任务，再通过 `/task-runs/progress` 和 `/task-runs/result` 推进执行状态。

当前 Java CloudSimPlus 示例已经接入控制平面的真实租约执行链路：实验启动后会先通过 `/tasks` 把 Cloudlet 对应的任务写入 `pending_queue`，随后每个仿真 VM 作为节点持续心跳并轮询 `/leases/next`。拿到租约后，示例才把对应 Cloudlet 提交给 CloudSimPlus 执行；执行期间会通过 `/task-runs/progress` 上报阶段、进度和模拟资源利用率，完成后再通过 `/task-runs/result` 回传结果。因此 Dashboard 的拓扑页可以从 `/report` 中的 `active_runs`、`recent_progress_events` 和调度决策实时高亮当前 DCI 路径。

任务下发后的状态流转如下：

1. `/tasks` 或策略提交只把任务写入控制平面并加入 `pending_queue`，此时任务会显示为“待调度”，还不会出现在执行记录。
2. CloudSimPlus 桥接器或真实节点代理持续心跳并请求 `/leases/next`，控制平面才会做调度决策并把任务租约发给目标节点。
3. 节点执行过程中回传 `/task-runs/progress`，Dashboard 的拓扑路径会根据 `/report` 中的 `active_runs`、最新进度、调度决策和节点 inventory 实时切换。
4. 节点最终回传 `/task-runs/result` 后，控制平面才写入执行记录；因此“执行记录没有这个任务”通常表示任务还在待调度队列或已发租约但尚未回传结果。

### 5. 打开 Dashboard

在浏览器打开：

```text
http://127.0.0.1:8024/dashboard
```

Dashboard 是静态 HTML/CSS/JS，无构建步骤。启动 CloudSimPlus 桥接器或真实节点代理后，节点/拓扑页面应能看到已注册节点；聊天和策略流程使用官方 `/chat/sessions*` API；任务执行由节点侧进程通过租约、进度和结果回报推进。拓扑页不再固定展示静态路径，而是优先读取 `/report` 中的 `active_runs`、`recent_progress_events`、`recent_decisions`、执行记录和待调度队列，实时高亮当前任务的全局 DCI 路径、数据中心内部 Leaf/Cluster/VM 路径以及路径时延、带宽、风险等指标。

### 6. 启动 MCP 工具服务

如果需要让 Hermes/MCP 主机调用 Tianjun 工具，在第三个终端运行：

```powershell
python -B main.py mcp-server `
  --config configs\tianjun.example.toml `
  --server http://127.0.0.1:8024
```

MCP server 会把 Tianjun HTTP API 包装为工具，包括读取集群状态、开始/继续聊天会话、起草/比较/仿真/解释策略，以及带确认边界的策略提交和任务调度。

### 7. 可选：真实节点代理

如需使用真实节点遥测代理，而不是模拟节点：

```powershell
python -B main.py real-agent `
  --config configs\tianjun.example.toml `
  --server http://127.0.0.1:8024 `
  --node-config examples\real_node_agent.example.json
```

默认不会执行真实任务。只有在确认主机隔离、命令允许列表、资源限制和审计策略后，才应使用 `--execute`。

如果希望真实节点代理也像后台拓扑一样持续消费任务，需要保持代理进程运行，并显式开启执行：

```powershell
python -B main.py real-agent `
  --config configs\tianjun.example.toml `
  --server http://127.0.0.1:8024 `
  --node-config examples\real_node_agent.example.json `
  --execute
```

### 8. 离线 smoke test

```powershell
python scripts\smoke_test.py --port 8135
```

该脚本会启动离线控制平面，检查 `/health`、`/report`、`/dashboard`，并验证 MCP 工具契约可导入。它用于快速验证，不代表完整启动。


## LLM 配置

离线模式适合本地冒烟验证。要启用 OpenAI 兼容的 Hermes 聊天层，请按“完整本地启动”的第 1 步配置并验证 LLM，并将 API 密钥存储在仓库之外。

项目 `.env` 和 `DEEPSEEK_API_KEY` 也受支持，但本地开发推荐使用 `secrets` 命令。

## 架构概览

```mermaid
flowchart LR
    User["User / Dashboard"] --> Chat["ChatRuntime"]
    MCP["MCP host"] --> MCPServer["FastMCP adapter"]
    Chat --> Tools["Tianjun tools"]
    MCPServer --> HTTP["HTTP API"]
    HTTP --> CP["CentralControlPlane facade"]
    Tools --> CP
    CP --> Scheduler["ClosedLoopAdaptiveScheduler"]
    CP --> Policy["PolicyWorkflowService"]
    CP --> Requirements["RequirementDialogueService"]
    CP --> Nodes["NodeRegistry"]
    CP --> Leases["TaskLeaseService"]
    Scheduler --> ML["Optional LSTM / GraphSAGE runtime"]
    Leases --> Agents["CloudSimPlus / real-agent"]
    Agents --> Results["Progress and results"]
    Results --> CP
```

核心入口：

- CLI：`main.py` 或安装后的 `tianjun`
- HTTP 服务器：`src/tianjun/interfaces/http/server.py`
- Dashboard 资源：`src/tianjun/interfaces/dashboard/static/`
- 控制平面门面：`src/tianjun/application/control_plane.py`
- MCP 适配器：`src/tianjun/integrations/mcp_server.py`

当前服务边界：

- `NodeRegistry`：节点注册、心跳和节点状态变更。
- `TaskLeaseService`：任务提交、预览、待调度任务、租约发放和租约激活。
- `RequirementDialogueService`：需求解析和需求会话生命周期。
- `PolicyWorkflowService`：策略起草、比较、模拟、提交、反馈解析和优化。
- `src/tianjun/cli/commands/`：CLI 命令处理器；`tianjun.cli` 只负责参数、配置和分发。

## 文档

- [文档索引](docs/README.md)
- [架构](docs/architecture.md)
- [HTTP API](docs/api.md)
- [弃用与遗留路由](docs/deprecation.md)
- [安全边界](docs/security-boundary.md)
- [DCI 实验与模型资产](docs/experiments-dci.md)
- [Dashboard 验证清单](docs/dashboard-test-checklist.md)
- [最终收敛冻结清单](docs/convergence-checklist.md)

## 仓库布局

```text
main.py                         本地源码检出用 CLI 入口
pyproject.toml                  包元数据和依赖项扩展
configs/                        最小运行配置
scripts/                        冒烟测试、收敛检查、训练辅助、Windows 辅助脚本
src/tianjun/application/        控制平面门面和应用服务
src/tianjun/chat/               Hermes 风格聊天运行时
src/tianjun/interfaces/http/    HTTP 服务器和遗留路由适配器
src/tianjun/interfaces/dashboard/static/
                                静态 HTML/CSS/JS Dashboard
src/tianjun/integrations/       MCP 集成
src/tianjun/scheduling/         确定性调度器
src/tianjun/policy/             需求解析、策略生成、反馈
data/trained_models/            可选运行时模型制品和清单
data/dci_reference/             DCI 复现用研究数据
tests/                          单元、集成、契约和冒烟测试覆盖
```

## 兼容性

官方聊天流程为 `/chat/sessions`。较早的 `/intent`、`/chat`、`/hermes/chat` 和 `/hermes/chat/stream` 端点仍作为已弃用兼容路由可用，但新客户端和 Dashboard 不应依赖它们。

请参阅 [docs/deprecation.md](docs/deprecation.md) 获取迁移指导。

## 验证

常规验证：

```powershell
python -m pytest
python scripts\smoke_test.py
python scripts\convergence_check.py
```
