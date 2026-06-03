# Tianjun Engine | 天钧算力网络资源调度智能体

Tianjun Engine 是一个面向算力网络资源编排的本地原型系统。它把自然语言需求理解、可解释策略生成、确定性多目标调度、可选机器学习增强、仿真或真实节点执行回传，以及可视化监控组织成一条闭环链路。

> 当前定位：本项目是研究与演示性质的算力调度控制面，不是可直接承载生产业务的云平台。节点、价格和执行结果只来自已注册节点、仿真后端或外部系统上报，智能体不会凭空生成资源事实。

当前仓库采用前后端分离架构：

- 后端提供 HTTP API 与 SSE 流式接口，默认监听 `http://127.0.0.1:8024`。
- 前端是独立的 Vite + React 工程，默认开发地址为 `http://127.0.0.1:5173`。
- 浏览器通过前端开发服务器访问后端 API，后端默认允许 `http://127.0.0.1:5173`，可通过 `TIANJUN_CORS_ALLOW_ORIGIN` 调整 CORS 来源。
- Dashboard 不再由后端内置静态页提供，而是由独立前端工程承载。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| Hermes 对话调度 | 多轮澄清需求，生成策略、仿真、解释、反馈优化和确认后提交 |
| 确定性选点 | 基于多指标归一化加权评分，不把最终状态迁移交给 LLM |
| 模型增强 | 可加载 LSTM 时延模型与 GraphSAGE 拓扑稳定性模型；未安装 PyTorch 时自动降级 |
| 控制面 API | 提供节点、任务、策略、聊天、lease 与执行结果接口 |
| Dashboard 前端 | 展示节点、任务、策略、模型状态、评分权重、最近决策与智能体会话 |
| 执行闭环 | 支持 noop、本地进程、Docker、Kubernetes Job 和配置驱动仿真模式 |
| MCP 工具服务 | 可选 FastMCP，把控制面能力暴露给支持工具调用的智能体宿主 |
| 状态持久化 | 可选 SQLite 存储节点、任务、租约、决策、执行记录和策略调整历史 |

## 系统架构

- `ChatRuntime` 负责 Hermes 风格会话编排，`TianjunToolService` 负责唯一可信的控制面工具映射。
- `CentralControlPlane` 负责节点、任务、策略、调度、反馈和执行状态的统一管理。
- 调度器同时考虑性能、完成时间、成本、可靠性、负载均衡、碎片率、局部性、网络和安全等维度。
- `data/trained_models/` 中的 LSTM 与 GraphSAGE 模型会在依赖可用时参与评分增强；依赖缺失时回退到确定性算法。
- 前端通过 `frontend/src/api.js` 调用后端接口，默认 API 基地址为 `http://127.0.0.1:8024`。

## 目录结构

```text
Tianjun-Engine/
 main.py
 pyproject.toml
 requirements.txt
 start_tianjun.bat
 restart_tianjun.bat
 configs/
   tianjun.example.toml
   sim_cluster.example.json
 data/
   dci_reference/
   trained_models/
 docs/
 examples/
   cloudsimplus/
 frontend/
   public/
   src/
   package.json
   vite.config.js
 scripts/
 src/tianjun/
   application/
   chat/
   config/
   core/
   domain/
   execution/
   integrations/
   interfaces/
   inventory/
   llm/
   ml/
   node_agent/
   policy/
   scheduling/
   simulation/
   storage/
   tools/
 tests/
```

## 前端组件边界

Dashboard 已拆为 React 组件，入口为 `frontend/src/components/DashboardPage.jsx`：

```text
DashboardPage
 StatusHeader
 ChatPanel
 PolicyPanel
 NodePanel
 TaskPanel
 ReportPanel
```

前端统一通过 `frontend/src/api.js` 访问后端：

```js
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8024";
```

## 环境要求

- Python 3.10 或更高版本
- Node.js 与 npm，用于运行 `frontend/`
- Windows 用户可直接使用 `.bat` 脚本，其他平台可按下面命令手动启动
- 使用 DeepSeek/Hermes LLM 时需要自行配置 API key，禁止把真实 key 提交到仓库

## 安装

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[ml-runtime,mcp]"
```

仅运行最小控制面时，也可以安装基础包：

```powershell
python -m pip install -e .
```

前端：

```powershell
cd frontend
npm install
```

可先复制示例环境变量文件：

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
```

- 根目录 `.env` 会在启动时自动加载，但不会覆盖当前 shell 已有的同名环境变量。
- `frontend/.env` 可设置 `VITE_API_BASE`，让前端连接到其他后端地址。
- 根目录 `.env` 可设置 `TIANJUN_CORS_ALLOW_ORIGIN`，让后端允许新的前端 Origin。

## 启动

终端 1：启动后端控制面。

```powershell
python -B main.py serve `
  --config configs\tianjun.example.toml `
  --inventory configs\sim_cluster.example.json `
  --default-execution-mode simulation `
  --host 127.0.0.1 `
  --port 8024
```

终端 2：可选，启动模拟节点后端。

```powershell
python -B main.py sim-backend `
  --server http://127.0.0.1:8024 `
  --inventory configs\sim_cluster.example.json `
  --verbose
```

终端 3：启动前端开发服务器。

```powershell
cd frontend
npm run dev
```

访问地址：

```text
前端 Dashboard: http://127.0.0.1:5173
后端 API:      http://127.0.0.1:8024
```

Windows 下可直接双击：

- `start_tianjun.bat`：启动控制面、模拟后端和前端开发服务器
- `restart_tianjun.bat`：安全停止并重启上述完整运行时

## DCI 拓扑感知与模型

仓库已包含用于拓扑感知调度实验的模型与数据资产：

- `data/trained_models/lstm_latency_model.pt`：时延预测增强模型
- `data/trained_models/graphsage_stability_model.pt`：默认加载的 DCI 三接入点拓扑稳定性模型
- `data/dci_reference/`：DCI 案例参考仿真数据、验证样本与来源说明
- `scripts/build_dci_graph_dataset.py`：从拓扑快照构造图数据集
- `scripts/train_dci_graphsage.py`：训练 DCI GraphSAGE 模型
- `examples/cloudsimplus/`：CloudSim Plus 侧的桥接与实验示例

说明：`DC1`、`DC2` 及仿真扩展的 `DC3`、相关城市标签和链路参数用于可复现实验，不应宣称为生产网络实测事实。

## LLM 配置

推荐把密钥写入本地用户配置目录，不要写入仓库：

```powershell
python -B main.py secrets --config configs\tianjun.example.toml set deepseek --api-key "your_api_key_here"
python -B main.py llm-check --config configs\tianjun.example.toml
```

也可使用项目根目录下被 `.gitignore` 排除的 `.env`：

```dotenv
DEEPSEEK_API_KEY=your_api_key_here
TIANJUN_CORS_ALLOW_ORIGIN=http://127.0.0.1:5173
```

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8024/
Invoke-RestMethod http://127.0.0.1:8024/health
Invoke-RestMethod http://127.0.0.1:8024/report
```

预期：

- `/` 返回基础 API 状态
- `/health` 返回服务、LLM 与模型运行时状态
- `/report` 返回 Dashboard 使用的完整控制面报告

## 主要 HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | API 状态 |
| `GET` | `/health` | 服务、LLM 与模型健康信息 |
| `GET` | `/report` | 控制面完整监控报告 |
| `GET` | `/hermes/status` | 智能体运行状态 |
| `POST` | `/nodes/register` | 注册节点 |
| `POST` | `/nodes/heartbeat` | 节点心跳与资源状态上报 |
| `POST` | `/topology/register` | 注册物理拓扑与算力节点接入点映射 |
| `POST` | `/tasks` | 提交任务 |
| `POST` | `/schedule/preview` | 外部仿真桥接选点预览，不创建 lease |
| `POST` | `/schedule/commit` | 外部仿真桥接确认调度 |
| `POST` | `/chat/sessions/stream` | 新建 Hermes 流式会话 |
| `POST` | `/chat/sessions/{id}/messages/stream` | 继续 Hermes 流式会话 |
| `POST` | `/chat/sessions/{id}/commit` | Dashboard 确认正式下发 |
| `POST` | `/policies/draft` | 生成策略草稿 |
| `POST` | `/policies/simulate` | 仿真策略 |
| `POST` | `/policies/commit` | 显式确认后提交策略 |
| `POST` | `/feedback` | 记录用户反馈 |
| `POST` | `/task-runs/progress` | 执行进度回写 |
| `POST` | `/task-runs/result` | 执行结果回写 |

## CORS

后端默认允许前端开发服务器访问：

```text
Access-Control-Allow-Origin: http://127.0.0.1:5173
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Methods: GET, POST, OPTIONS
```

如需改成其他前端来源，可设置环境变量 `TIANJUN_CORS_ALLOW_ORIGIN`。

## 安全边界

- LLM 可以辅助理解意图和生成自然语言解释，但库存事实、策略状态变更和任务提交只由控制面工具执行。
- `commit_policy` 与 `schedule_pending_task` 必须有显式用户确认。
- Dashboard 通过独立的正式下发动作完成提交，聊天文本不能绕过提交保护。
- CloudSim Plus 与配置驱动的模拟节点代表仿真资源，不能等同于真实物理资源库存。
- 当前 HTTP 服务没有生产级认证、租户隔离、RBAC、限流或 TLS 终止层，不应直接暴露到公网。

## 验证

后端测试：

```powershell
python -m pytest
```

前端构建：

```powershell
cd frontend
npm run build
```

## 贡献方向

- 增加调度、策略、MCP 与 HTTP API 的单元测试和端到端测试
- 增加 Docker Compose 或部署脚本，使控制面、模拟节点和前端可一键运行
- 接入真实设备或控制器遥测，将案例参考拓扑和校准链路参数升级为可验证的实测数据
- 增加认证、审计、密钥管理与多租户隔离，向生产级控制面演进
