# Tianjun Engine | 天钧算力网络资源调度智能体

Tianjun Engine 是一个面向算力网络资源编排的本地原型系统。它把自然语言需求理解、可解释策略生成、确定性多目标调度、可选机器学习增强、仿真/真实节点执行回传和可视化监控组织成一条闭环链路。

当前工程已经完成前后端分离：

- 后端只提供 HTTP API 与 SSE 流式接口，默认监听 `http://127.0.0.1:8024`。
- 前端是独立 Vite + React 工程，默认开发地址为 `http://127.0.0.1:5173`。
- 浏览器从前端开发服务器访问后端 API，后端已为 `http://127.0.0.1:5173` 配置 CORS。
- 后端不再内置 HTML 页面，Dashboard 由独立前端工程提供。

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

## 工程结构

```text
Tianjun-Engine/
├─ main.py                         # 本地 CLI 入口
├─ pyproject.toml                  # Python 包元数据与可选依赖
├─ requirements.txt                # 最小开发/验证依赖
├─ start_tianjun.bat               # Windows 一键启动后端、仿真后端和前端
├─ restart_tianjun.bat             # Windows 安全重启完整演示闭环
├─ configs/
│  ├─ tianjun.example.toml         # 服务、LLM、MCP、执行安全配置模板
│  └─ sim_cluster.example.json     # 模拟节点、链路与工作负载画像
├─ frontend/                       # Vite + React Dashboard
│  ├─ src/
│  │  ├─ api.js                    # 前端 API 统一封装
│  │  ├─ dashboard.css             # Dashboard 样式
│  │  └─ components/               # React 页面与面板组件
│  └─ public/dashboardRuntime.js   # 迁移后的 Dashboard 运行时逻辑
├─ src/tianjun/
│  ├─ application/                 # 中央控制面和应用组装
│  ├─ chat/                        # Hermes 对话运行时与 SSE 工具轨迹
│  ├─ domain/                      # 节点、任务、网络、执行、决策等领域模型
│  ├─ scheduling/                  # 确定性多目标调度引擎
│  ├─ policy/                      # 解析、澄清、策略生成、仿真、反馈优化
│  ├─ interfaces/http/             # 纯 HTTP API 服务
│  ├─ simulation/                  # 配置驱动模拟节点运行时
│  ├─ node_agent/                  # 轻量 Agent 与真实节点探测 Agent
│  ├─ execution/                   # 执行器注册表和运行后端
│  ├─ inventory/                   # 节点与网络库存加载
│  ├─ storage/                     # SQLite 状态存储
│  ├─ llm/                         # OpenAI-compatible LLM 客户端
│  └─ config/                      # 配置、路径、dotenv 与本地密钥读取
└─ tests/                          # pytest 测试
```

## 前端组件边界

Dashboard 已拆成 React 组件，入口为 `frontend/src/components/DashboardPage.jsx`：

```text
DashboardPage
├─ StatusHeader
├─ ChatPanel
├─ PolicyPanel
├─ NodePanel
├─ TaskPanel
└─ ReportPanel
```

前端 API 统一走 `frontend/src/api.js`：

```js
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8024";
```

如需连接其他后端地址，可在前端环境中设置 `VITE_API_BASE`。

## 环境要求

- Python 3.10 或更高版本。
- Node.js 与 npm，用于运行 `frontend/`。
- Windows 用户可直接使用 `.bat` 脚本；其他平台可按下面命令手动启动。
- 使用 DeepSeek/Hermes LLM 辅助时需要自行配置 API key，禁止把真实 key 提交到仓库。

## 安装

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[ml-runtime,mcp]"
```

仅运行最小控制面时也可以安装基础包：

```powershell
python -m pip install -e .
```

前端：

```powershell
cd frontend
npm install
```

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

终端 2：启动前端开发服务器。

```powershell
cd frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

终端 3：可选，启动模拟节点后端。

```powershell
python -B main.py sim-backend `
  --server http://127.0.0.1:8024 `
  --inventory configs\sim_cluster.example.json `
  --verbose
```

Windows 下也可在配置好 API key 后双击 `start_tianjun.bat`。脚本会依次启动控制面、模拟节点后端和前端开发服务器，并打开 Dashboard。

## LLM 配置

示例配置默认使用 OpenAI-compatible 的 DeepSeek 接口。推荐把密钥写入本地用户配置目录，不要写入仓库：

```powershell
python -B main.py secrets --config configs\tianjun.example.toml set deepseek --api-key "your_api_key_here"
python -B main.py llm-check --config configs\tianjun.example.toml
```

也可使用项目根目录下被 `.gitignore` 排除的 `.env`：

```dotenv
DEEPSEEK_API_KEY=your_api_key_here
```

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8024/
Invoke-RestMethod http://127.0.0.1:8024/health
Invoke-RestMethod http://127.0.0.1:8024/report
```

预期：

- `/` 返回 `{ "name": "Tianjun Engine API", "status": "ok" }`。
- `/health` 返回服务、LLM 与模型运行时状态。
- `/report` 返回 Dashboard 使用的完整控制面报告。

## 主要 HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | API 状态 |
| `GET` | `/health` | 服务、LLM 与模型运行时健康信息 |
| `GET` | `/report` | 控制面完整监控报告 |
| `GET` | `/hermes/status` | 智能体运行状态 |
| `POST` | `/nodes/register` | 注册节点 |
| `POST` | `/nodes/heartbeat` | 节点心跳与资源状态上报 |
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

后端允许前端开发服务器访问：

```text
Access-Control-Allow-Origin: http://127.0.0.1:5173
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Methods: GET, POST, OPTIONS
```

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

## 安全边界

- LLM 可以辅助理解意图和生成自然语言解释，但库存事实、策略状态变更和任务提交只由控制面工具执行。
- Hermes 路径中的 `commit_policy` 与 `schedule_pending_task` 必须有显式用户确认。
- Dashboard 使用独立的“正式下发”按钮完成提交，聊天文本不能绕过提交保护。
- `serve --inventory` 只校验库存配置文件，不会自动把模拟节点注册在线；节点必须由 `sim-backend`、CloudSimPlus 或真实 Agent 注册/心跳上报。

## 贡献方向

- 增加调度、策略、MCP 与 HTTP API 的单元测试和端到端测试。
- 增加 Docker Compose 或部署脚本，使控制面、模拟节点和前端可一键运行。
- 接入真实设备或控制器遥测，将案例参考拓扑和校准链路参数升级为可验证的实测数据。
- 增加认证、审计、密钥管理与多租户隔离，向生产级控制面演进。
