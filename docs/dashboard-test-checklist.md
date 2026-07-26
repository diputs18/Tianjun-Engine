# Dashboard 测试清单

Dashboard 是静态 HTML/CSS/JS，没有生产构建步骤。`npm run test:frontend` 执行纯逻辑测试，`npm run test:browser` 启动真实 Python 控制面和 Chromium，覆盖 1366 与 1920 两档 PC 视口。以下项目均应由自动化覆盖，并可在演示前抽查：

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
- 网络、资源负载、碳强度按钮同步 `aria-pressed`，并切换对应语义摘要。
- 空拓扑、健康检查失败和请求超时均呈现明确状态。
- 页面主体和拓扑画布在支持的 PC 视口内没有横向溢出。
- 拓扑 SVG、节点和链路标签保持在拓扑内容边界内。
