# Tianjun Engine

Tianjun Engine 是一个本地优先的算网调度控制平面原型。它把自然语言需求对话、确定性多目标调度、可选 ML 辅助预测、执行反馈、MCP 工具和静态 Dashboard 连接成一个可运行的研究系统。

本项目用于研究、演示和架构实验，并非生产级云平台。资源清单、定价、拓扑和执行事实必须来自已注册节点、仿真后端、CloudSimPlus 桥接器或真实节点代理；LLM 可以解释和帮助解析意图，但不能在没有明确确认路径的情况下捏造控制平面事实或提交工作。

## 快速开始

需要 Python 3.10 或更新版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mcp,ml-runtime]"
```

## 完整本地启动

完整启动不是离线降级模式，也不是只跑一次冒