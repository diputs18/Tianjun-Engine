# Tianjun Engine | 天钧算力网络资源调度智能体

Tianjun Engine 是一个面向算力网络资源编排的本地原型系统。它把自然语言需求理解、可解释策略生成、确定性多目标调度、可选机器学习增强、仿真/真实节点执行回传和可视化监控组织成一条闭环链路。

当前仓库采用前后端分离架构：

- 后端提供 HTTP API 与 SSE 流式接口，默认监听 `http://127.0.0.1:8024`。
- 前端是独立 Vite + React + Arco Design 工程，默认开发地址为 `http://127.0.0.1:5173`。
- 浏览器通过前端开发服务器访问后端 API，后端默认允许 `http://127.0.0.1:5173`，可通过 `TIANJUN_CORS_ALLOW_ORIGIN` 调整 CORS 来源。
- Dashboard 不再由后端内置静态页提供，而是由独立前端工程承载。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| Hermes 对话调度 | 多轮澄清需求，生成策略、仿真、解释、反馈优化和确认后提交 |
| 确定性选点 | 基于多指标归一化加权评分，不把最终状态迁移交给 LLM |
| 模型增强 | 可加载 LSTM 时延模型与 GraphSAGE 拓扑稳定性模型；未安装 PyTorch 时自动降级 |
| 控制面 API | 提供节点、任务、策略、聊天、lease 与执行结果接口 |
| Dashboard 前端 | 企业控制台展示系统状态、调度工作台、任务、基础设施、模型策略和审计设置 |
| 执行闭环 | 支持 noop、本地进程、Docker、Kubernetes Job 和配置驱动仿真模式 |
| MCP 工具服务 | 可选 FastMCP，把控制面能力暴露给支持工具调用的智能体宿主 |
| 状态持久化 | 可选 SQLite 存储节点、任务、租约、决策、执行记录和策略调整历史 |

## 工程结构

```text
Tianjun-Engine/
├─ main.py
├─ pyproject.toml
├─ requirements.txt
├─ start_tianjun.bat
├─ restart_tianjun.bat
├─ configs/
│  ├─ tianjun.example.toml
│  └─ sim_cluster.example.json
├─ frontend/
│  ├─ src/
│  │  ├─ app/          # 路由定义与应用入口
│  │  ├─ layout/       # 侧栏、顶栏、控制面数据 Provider
│  │  ├─ pages/        # 六个页面级入口
│  │  ├─ features/     # KPI、图表、拓扑、调度台等业务组件
│  │  ├─ services/     # API 封装
│  │  ├─ hooks/        # SSE、轮询与状态聚合
│  │  ├─ theme/        # ThemeProvider 与主题 token hook
│  │  ├─ styles/       # 主题 token、布局与页面样式
│  │  └─ utils/        # 格式化工具
│  ├─ package.json
│  └─ vite.config.js
├─ src/tianjun/
│  ├─ application/
│  ├─ chat/
│  ├─ domain/
│  ├─ interfaces/http/
│  ├─ policy/
│  ├─ scheduling/
│  └─ ...
└─ tests/
```

## 前端页面

前端使用 Arco Design、React Router、ECharts、dayjs 与 clsx；内置 light/dark 双主题系统，默认跟随系统偏好。页面级设计如下：

| 路由 | 页面 | 目标 |
| --- | --- | --- |
| `/` | OverviewPage | 5 秒内判断系统是否健康、SLA 是否达标、模型是否加载 |
| `/scheduling` | SchedulingPage | AI 对话、调度工作台、仿真结果和正式下发保护 |
| `/workloads` | WorkloadsPage | 任务队列、运行态与历史执行结果 |
| `/infrastructure` | InfrastructurePage | 资源池概览、区域分级拓扑、节点表格和节点详情抽屉 |
| `/model-policy` | ModelPolicyPage | 模型运行时、策略权重、策略草案与解释性历史 |
| `/audit-settings` | AuditSettingsPage | 只读审计、运行配置与安全边界 |

前端 API 统一通过 `frontend/src/services/api.js` 访问后端：

```js
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8024";
```

如需连接其他后端地址，可在 `frontend/.env` 中设置：

```dotenv
VITE_API_BASE=http://127.0.0.1:8024
```

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

终端 2：启动模拟节点后端。

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

访问：

```text
http://127.0.0.1:5173
```

Windows 下也可使用脚本：

- `start_tianjun.bat`：启动控制面、模拟后端和前端开发服务器。
- `restart_tianjun.bat`：重启完整演示闭环。

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

后端默认允许前端开发服务器访问：

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
- Dashboard 使用独立的正式下发动作完成提交，聊天文本不能绕过提交保护。
- `serve --inventory` 只校验库存配置文件，不会自动把模拟节点注册在线；节点必须由 `sim-backend`、CloudSimPlus 或真实 Agent 注册/心跳上报。

## 贡献方向

- 增加调度、策略、MCP 与 HTTP API 的单元测试和端到端测试。
- 增加 Docker Compose 或部署脚本，使控制面、模拟节点和前端可一键运行。
- 接入真实设备或控制器遥测，将案例参考拓扑和校准链路参数升级为可验证的实测数据。
- 增加认证、审计、密钥管理与多租户隔离，向生产级控制面演进。
