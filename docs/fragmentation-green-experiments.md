# 高负载碎片与绿色消融实验

## 实验目的

该实验不是只比较低碳，而是在相同异构节点、任务和随机种子下回答三个问题：

1. 高负载时，碎片感知能否保留更多未来任务可调度能力；
2. 绿色单目标、绿色与完成时间双目标、绿色与碎片双目标之间有何取舍；
3. B6 分层目标中的绿色权重能否从训练种子泛化到验证种子和 CloudSim 实际执行。

## Future-Fit 口径

Future-Fit 使用未来任务与节点的可行对比例：

```text
Future-Fit = 可行的任务—节点对数 / (未来任务数 × 节点数)
```

可行性同时检查八维资源、地域、安全、隔离、网络和强制碳预算。相比“任务只要能放入任意一个节点就算可行”，该指标能识别可替代节点减少和资源形状碎片。

同时报告：

```text
Future-Fit loss = Future-Fit before - Future-Fit after
FF loss / accepted task = Future-Fit loss / 已接纳任务数
carbon / accepted task = 批次预测运行碳 / 已接纳任务数
```

按任务归一化用于避免接纳任务数不同导致碎片和碳指标不可比；批次总碳仍保留，用于评估整个方案的实际环境影响。

## 实验设计

- 节点：20 个，八维异构资源；
- 任务：60 个 CPU、GPU、内存和数据密集型混合任务；
- 背景负载：85% 和 95%；
- 背景形状：CPU-heavy、memory-heavy、GPU/IO-heavy、network-heavy；
- 随机种子：5 个，其中前 3 个用于权重选择，后 2 个只用于验证。

消融组包括：

- 十维平面融合与五组分层融合；
- `carbon`、`fragmentation` 原子单目标；
- `carbon+completion`、`carbon+fragmentation` 原子双目标；
- `green_carbon`、`resource_efficiency` 分组单目标；
- `green_carbon+sla_quality`、`green_carbon+resource_efficiency` 分组双目标；
- B6 五组权重校准候选。

## B6 决策开销控制

B6 只在 `resource_efficiency` 或原子 `fragmentation` 目标处于激活状态时，为候选节点计算 Future-Fit。绿色单目标及绿色+SLA 双目标仍在最终方案阶段完整报告 Future-Fit，但候选排序阶段跳过不会参与效用计算的碎片指标。该优化不改变硬约束，也不删减最终实验输出。

## 运行命令

```powershell
python -m tianjun.experiments.runner `
  --config configs/fragmentation_green_experiments.json `
  --output exp_out/fragmentation_green/results.json

python -m tianjun.experiments.report `
  exp_out/fragmentation_green/results.json `
  --csv exp_out/fragmentation_green/summary.csv `
  --markdown exp_out/fragmentation_green/summary.md

python scripts/calibrate_b6_weights.py
```

## 输出与解释边界

结果保存到：

```text
exp_out/fragmentation_green/results.json
exp_out/fragmentation_green/summary.csv
exp_out/fragmentation_green/summary.md
exp_out/fragmentation_green/calibration.json
exp_out/fragmentation_green/calibration.md
```

合成实验只用于筛选候选权重。候选权重必须再经过 CloudSim 正常与故障场景验证；如果只在正常场景减碳、在故障场景增碳，就保留为实验配置，不能替换默认 B6。
