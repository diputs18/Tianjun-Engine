# Dashboard 测试清单

Dashboard 是静态 HTML/CSS/JS，没有构建步骤。在演示前，运行冒烟测试，然后手动验证以下内容：

- `/dashboard` 加载时浏览器控制台没有错误。
- 顶部导航显示来自 `/health` 的系统状态。
- 概览页面渲染来自 `/report` 的指标。
- 未启动 CloudSimPlus 桥接器或真实节点 Agent 时，拓扑页面显示空状态。
- 启动 CloudSimPlus 桥接器后，节点/拓扑页面显示 Java 仿真实验注册的节点与 DCI 拓扑。
- 调度聊天通过 `/chat/sessions/stream` 发送消息。
- 最终提交按钮通过 `/chat/sessions/{session_id}/commit` 提交。
- 任务执行结果来自 CloudSimPlus 桥接器或真实节点 Agent 的 `/task-runs/result` 回报。
- 模型页面权重更新需要明确确认并调用 `/policy-weights`。
- 任务取消调用 `/task-runs/cancel`。
- Dashboard 代码中没有调用 `/intent`、`/chat` 或 `/hermes/*`。
- 顶部标签页同步 `aria-selected`，并支持左右方向键、Home 和 End。
- 页面隐藏时自动刷新暂停，返回前台后恢复且不会出现重叠请求。
- CloudSimPlus VM 心跳遥测在拓扑节点详情中显示；未上报指标显示 `--`。
- 总览、调度、拓扑、任务和模型页面分别读取对应的精简报告视图。
