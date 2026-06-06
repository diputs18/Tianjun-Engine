# Dashboard 测试清单

Dashboard 是静态 HTML/CSS/JS，没有构建步骤。在演示前，运行冒烟测试，然后手动验证以下内容：

- `/dashboard` 加载时浏览器控制台没有错误。
- 顶部导航显示来自 `/health` 的系统状态。
- 概览页面渲染来自 `/report` 的指标。
- 当没有注册节点时，拓扑页面显示空状态。
- 调度聊天通过 `/chat/sessions/stream` 发送消息。
- 最终提交按钮通过 `/chat/sessions/{session_id}/commit` 提交。
- 模型页面权重更新需要明确确认并调用 `/policy-weights`。
- 任务取消调用 `/task-runs/cancel`。
- Dashboard 代码中没有调用 `/intent`、`/chat` 或 `/hermes/*`。
