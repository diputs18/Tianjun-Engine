# CloudSim Plus 批调度核心实验

## 已接通的执行闭环

```text
Cloudlet 批次
→ POST /task-batches/import
→ POST /task-batches/{batch_id}/preview
→ POST /task-batches/{batch_id}/commit
→ 节点领取 lease
→ Cloudlet 在指定 VM 执行
→ POST /task-runs/result
→ GET /task-batches/{batch_id}/metrics
```

Python 控制面和 CloudSim 桥接层统一采用八维资源契约：

```text
cpu, memory, gpu, storage, mips, gpu_memory, storage_iops, bandwidth
```

旧四维场景仍可运行，新增维度缺省为 0。CloudSim Host 使用功耗配置中的瓦特值；Host 遥测总能耗与任务增量能耗分别记账，避免重复计碳。碳强度从独立 CSV 轨迹加载，`.brite` 仅表示网络拓扑。

## 正式绿色策略

- `B0-current`：现有串行基线。
- `B6-green-single-v1`：只激活 `green_carbon`，用于绿色单目标消融。
- `B6-green-sla-85-v1`：`green_carbon=0.85`、`sla_quality=0.15`，用于绿色与 SLA 双目标消融。

这些名称是可审计实验配置，不替代通用的 `B6-hierarchical-batch`。静态绿色权重只有在正常与故障场景都通过验证后，才能升级为默认策略。

## 预测与实测口径

CloudSim 向控制面传入 Cloudlet 的预期 CPU 利用率和估计时长。控制面据此预测任务增量功率、能耗和运行碳。实际结果回传：

- 接纳率、完成率、成功和失败任务数；
- 平均/P95 JCT、排队等待和 Makespan；
- CPU、内存、带宽和存储平均利用率；
- 任务增量能耗、计算碳、网络碳和总运行碳；
- SLA 违规数、预演值和决策时间。

碳核算范围固定为 `operational_only`，不含硬件隐含碳。当前预演 Makespan 按节点累计负载计算，而 CloudSim 会在多核、多 VM 上并行，因此预演 Makespan 是保守值；正式结论使用 CloudSim 实测 JCT 与 Makespan。

## 运行命令

运行配置中的全部核心实验：

```powershell
./scripts/run_cloudsim_core_experiments.ps1
```

中断后从已有 `*.metrics.json` 继续：

```powershell
./scripts/run_cloudsim_core_experiments.ps1 -Resume
```

只运行正式绿色验证策略：

```powershell
./scripts/run_cloudsim_core_experiments.ps1 `
  -StrategyFilter B0-current,B6-green-single-v1,B6-green-sla-85-v1
python ./scripts/report_green_validation.py
```

单种子链路验证：

```powershell
./scripts/run_cloudsim_core_experiments.ps1 `
  -StrategyFilter B0-current `
  -ScenarioFilter normal `
  -SeedLimit 1
```

配置位于 `configs/cloudsim_core_experiments.json`。每次运行会启动隔离的控制面和 SQLite 数据库，同步桥接源码、执行 Maven、保存 Cloudlet 实际指标，并生成统计结果。

## 输出目录

```text
exp_out/cloudsim_core/
├─ {strategy}/{scenario}/seed-{seed}/
│  ├─ topology-snapshots.jsonl
│  ├─ topology-snapshots.metrics.json
│  ├─ control-plane.sqlite3
│  ├─ cloudsim-maven.log
│  └─ control-plane.*.log
├─ raw_metrics.csv
├─ summary.csv
├─ paired_effects.csv
└─ summary.md

exp_out/cloudsim_green_validation/
├─ summary.csv
├─ paired_effects.csv
└─ summary.md
```

`summary.csv` 报告 Student-t 95% 置信区间，`paired_effects.csv` 按相同场景和随机种子计算策略相对 B0 的配对差值与变化率。单种子只用于链路验证，论文结论使用配置中的 10 个随机种子。
