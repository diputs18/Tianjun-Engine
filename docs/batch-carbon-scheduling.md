# 批任务、多目标、碎片与运行碳联合调度

天钧引擎现已提供 JSON/CSV 批任务导入、联合预演、策略对比、显式确认和原子预留闭环。首期任务相互独立，一个任务只分配到一个节点；碳核算范围固定为 `operational_only`。

## 公共接口

```text
POST /task-batches/import
GET  /task-batches/{batch_id}
POST /task-batches/{batch_id}/preview
POST /task-batches/{batch_id}/compare
POST /task-batches/{batch_id}/commit
```

提交必须携带预演返回的 `plan_id`、`resource_snapshot_version` 和 `confirmed_by_user_button=true`。快照发生变化时返回 HTTP 409，并且不会创建任何部分预留。

CSV 必填列：

```text
task_id,task_type,cpu,memory,gpu,storage,estimated_duration,priority
```

布尔字段只接受 `true/false`，多值字段使用 `|` 分隔。单批最多 1000 个任务，文件不超过 5 MB，任意一行失败时整批不入队。

## 在线策略

- `B0-current`：兼容当前逐任务加权评分基线。
- `B1-batch-greedy`：按紧迫度、优先级、稀缺资源和稳定 ID 排序，分配后立即更新虚拟资源。
- `B3-batch-local-search`：在 B1 上增加节点重放、局部交换和未分配任务回填。
- `B4-pareto-tchebycheff`：每个任务先做 Pareto 候选过滤，再使用增强型 Tchebycheff 效用和 B3 联合分配。
- `B6-hierarchical-batch`：默认研究策略。先在五个业务目标组内融合原子指标，再对目标组做 Pareto 过滤、增强型 Tchebycheff 排序和批方案级局部搜索。

十项观测指标不会被无差别地一次性相加，而是分成五个语义目标组：

| 外层目标组 | 组内原子指标 | 默认组内权重 |
|---|---|---|
| SLA 与服务质量 | performance、completion、reliability | 0.20 / 0.50 / 0.30 |
| 网络与地域协同 | network、locality | 0.65 / 0.35 |
| 资源效率 | balance、fragmentation（并在方案层融合 Future-Fit） | 0.40 / 0.60 |
| 经济成本 | cost | 1.00 |
| 绿色低碳 | carbon | 1.00 |

表中的组内权重是稳定语义先验，不会覆盖项目原有参数。每个任务先计算十维的 `W_final`，再在各组内重新归一化，并与先验融合：

```text
W_inner(g) = Normalize(0.35 W_prior(g) + 0.65 Normalize(W_final restricted to group g))
```

因此，原有十维权重仍会影响组内取舍；五个目标组权重负责组间取舍。两层权重都会写入决策快照，便于消融、解释和复现。

`security` 不进入可互相补偿的外层效用：容量、地域、数据驻留、最低安全等级、隔离、加密、截止时间和强制碳预算先作为硬约束；候选节点满足硬约束后，再按安全等级扣除残余风险惩罚。这样低成本或低碳不能抵消安全违规。

最终权重按以下来源融合：

```text
W_final = Normalize(0.4 W_intent + 0.4 W_SLA + 0.2 W_data)
```

工程归一化使用固定版本边界，不再根据当前候选集合临时 Min-Max。当前 `W_data` 是固定 CRITIC 参考画像；`tianjun.experiments` 已提供离线 CRITIC、熵权、MILP Oracle 和确定性 NSGA-II 基线，但它们不进入在线默认路径。

实验策略必须显式提交 `experiment_mode=true`：

- `B2-milp-oracle`：限制为不超过 20 个任务 × 20 个节点，使用 SciPy/HiGHS 生成小规模 Oracle；
- `B5-nsga2`：离线 Pareto 基线，固定随机种子时结果可重复；
- 安装实验依赖：`pip install -e ".[experiments]"`。

统一实验矩阵可直接运行：

```powershell
python -m tianjun.experiments.runner --quick
python -m tianjun.experiments.runner --config configs/batch_experiments.json --output artifacts/batch_experiments/results.json
```

输出固定记录接纳率、Makespan、决策时间、SLA 违反、Future-Fit、能耗、运行碳及相对 B0 的差值；完整矩阵可能耗时较长，先用 `--quick` 验证环境。

### 单目标、双目标与完整融合实验

专用配置文件 `configs/objective_ablation_experiments.json` 同时定义五类证据：

```text
S1：单个原子指标（性能、时效、成本、可靠性、均衡、碎片、地域、网络、运行碳）
S2：九个可补偿原子目标的全部两两组合，共 C(9,2)=36 组
G1：单个目标组
G2：五个目标组的全部两两组合，共 C(5,2)=10 组
FULL：B4 十维扁平融合与 B6 五组分层融合
```

运行命令：

```powershell
python -m tianjun.experiments.runner --quick --config configs/objective_ablation_experiments.json --output exp_out/quick.json
python -m tianjun.experiments.runner --config configs/objective_ablation_experiments.json --output exp_out/results.json
python -m tianjun.experiments.report exp_out/results.json --csv exp_out/summary.csv --markdown exp_out/summary.md
```

每行结果除业务指标外，还记录 `experiment_label`、`objective_scope`、`active_objectives`、`objective_hierarchy_version`、五组得分、方案级效用和安全风险惩罚。正式结论应按相同拓扑/任务/随机种子进行配对比较，报告均值、标准差或 95% 置信区间，而不是只选一个最好样例。

单目标实验回答“指标方向是否正确”；双目标实验回答“目标之间如何冲突或协同”；B4 与 B6 的对照回答“分层结构是否优于十维直接融合”。三者必须同时保留，不能用完整融合结果替代消融实验。

## 运行碳口径

```text
E_IT(kWh) = P_incremental(W) × T(seconds) / 3,600,000
O_compute(g) = E_IT × PUE × CI_site(region, tick)
O_total = O_compute + O_network
```

物理 Host 空闲功耗只计算一次，任务只分摊增量功耗。站点 PUE、碳强度轨迹和 Host 功耗画像独立于 `.brite` 网络拓扑保存。允许时间平移且提供 `deferrable_until_tick` 时，调度器可在窗口内选择预测碳强度最低的 tick；禁止跨地域或禁止错峰时始终服从用户硬约束。

## Hermes 与 MCP

MCP 工具包括：

```text
import_task_batch
get_task_batch
preview_batch_schedule
compare_batch_strategies
commit_batch_schedule
```

外部 MCP 请求带调用来源头，控制面记录最近成功工具、批次、方案和时间。Dashboard 只在出现真实成功调用后显示 MCP 已调用；MCP 进程启动本身不计为连接成功。

## 研究边界

- 暂不实现 DAG、Gang 调度、跨节点 GPU 聚合和硬件隐含碳。
- 论文中的收益数字不作为本项目结果；必须在同一拓扑、任务、碳轨迹和随机种子上复跑。
- 合成碳轨迹用于可重复主实验，真实公开碳数据用于复核。
