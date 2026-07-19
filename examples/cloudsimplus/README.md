# CloudSim Plus DCI 示例

本目录归档了用于生成 `data/dci_reference/` 中 DCI 拓扑感知训练数据的 CloudSim Plus 桥接文件。

将这些文件复制到 CloudSim Plus Examples 检出项目的对应位置，或与本地实验项目进行比较：

```text
src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java
src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java
src/main/resources/huawei-dci-reference.brite
src/main/resources/tianjun-power-profiles.json
src/main/resources/tianjun-carbon-intensity-trace.csv
```

该实验创建了 24 个模拟计算 VM，并将三个 Hermes 部署区域映射到各一个模拟物理接入点：

- `east`：北京/杭州，连接到 `DC1`
- `west`：成都/重庆，连接到 `DC2`
- `south`：广州/深圳，连接到 `DC3`

`DC1/DC2` 遵循项目 README 中描述的公开案例抽象。`DC3` 是用于三区域实验的可复现模拟扩展，不是声称的生产网络站点。

## Tianjun 租约执行链路

该示例现在使用 Tianjun 控制平面的租约协议，而不是一次性批量提交调度结果：

1. `HuaweiDciTianjunExperiment` 启动后注册 DCI 物理拓扑和 24 个仿真 VM 节点。
2. 每个 Cloudlet 会转换为 Tianjun 任务并通过 `/tasks` 写入 `pending_queue`。
3. 仿真 VM 节点持续发送 `/nodes/heartbeat`，并通过 `/leases/next` 领取待执行任务。
4. 领取租约后，示例才把对应 Cloudlet 提交给 CloudSim Plus 执行，并通过 `/task-runs/progress` 上报阶段、进度和模拟资源利用率。
5. Cloudlet 完成后，示例通过 `/task-runs/result` 回传最终执行结果，控制平面再写入执行记录。

因此 Dashboard 拓扑页可以根据 `/report` 中的 `active_runs`、`recent_progress_events`、调度决策和节点 inventory 实时更新 DCI 路径与 Leaf/Cluster/VM 高亮。

## 功耗与运行碳口径

- `.brite` 仍只保存网络拓扑，不混入碳数据。
- 物理 Host 使用 `PowerModelHostSimple`；Host 空闲功耗只在站点层计算一次，任务只分摊其增量功耗。
- 心跳上报瞬时功率、增量能耗、站点碳强度和信号时间戳。
- 任务结果分别上报计算碳、网络碳和总运行碳，`carbon_scope` 固定为 `operational_only`。
- 合成碳轨迹用于可重复主实验，不能当作真实电网历史数据。
