# DCI 拓扑感知 GNN 数据集

本目录包含用于 Tianjun 拓扑感知 GNN 路径的模拟观测数据和派生的标注数据集。

## 来源边界

| 项目 | 状态 | 依据 |
| --- | --- | --- |
| `DC1 -> Border1 -> PE1 -> IPCORE -> PE3 -> Border2 -> DC2` | 案例派生结构 | `D:\QQ_DownloadFile\算力网络 应用解决案例.pptx`，幻灯片 2-3 |
| `PE3 -> Border3 -> DC3` | 模拟扩展 | 添加以支持每个 Hermes 部署区域一个模拟接入点 |
| `User-Access -> PE3` | 案例派生结构 | 同一演示文稿，幻灯片 3 |
| 站点地理位置 | 未断言 | 幻灯片中命名了 `DC1` 和 `DC2`；`DC3` 和六个命名城市仅为模拟放置标签 |
| VM/主机 CPU、内存和存储 | 模拟资源清单 | CloudSim Plus 对象，非发现的物理服务器 |
| 链路延迟、带宽、抖动、丢包和故障振幅 | 校准实验参数 | BRITE 拓扑和可复现场景公式，非华为遥测数据 |

因此，本数据集适用于可重复的拓扑感知调度实验。它不得被表述为华为生产监控数据或经过验证的物理节点清单。

当前生成的语料库在每个拓扑快照中观测 24 个模拟 VM。Hermes 暴露三个模拟部署区域，每个区域八个 VM：`east`（北京/杭州）连接到 `DC1`，`west`（成都/重庆）连接到 `DC2`，`south`（广州/深圳）在模拟图中连接到 `DC3`。

## 内容

- `raw/*.jsonl`：来自独立的 `normal` 和过渡 `fault` 运行的原始 CloudSim Plus 拓扑快照。
- `dci_graph_samples.jsonl`：从原始快照构建的 GNN 样本。
- `dci_graph_samples.manifest.json`：标签定义、特征名称和来源边界。
- `validation/*.jsonl`：用于正常和已降级（`fault-active`）运行的保留在线验证快照。

每个标注样本使用已注册的物理拓扑获取可达计算邻居，并通过最短传播延迟的倒数加权其特征聚合。其标签是由观测延迟、抖动、带宽、丢包和路径可靠性形成的未来窗口 QoS 稳定性分数的平均值；它不是从场景故障标志复制的。

## 重新生成

使用 `org.cloudsimplus.examples.HuaweiDciTianjunExperiment` 生成原始快照后，运行：

```powershell
$raw = Get-ChildItem data\dci_reference\raw\*.jsonl | Select-Object -ExpandProperty FullName
python scripts\build_dci_graph_dataset.py @raw `
  --output data\dci_reference\dci_graph_samples.jsonl --future-window 3

python scripts\train_dci_graphsage.py data\dci_reference\dci_graph_samples.jsonl `
  --output-dir data\trained_models\dci_reference --epochs 100
```

启动 Tianjun 时加载 DCI 特定模型：

```powershell
python -B main.py serve --offline --model-dir data\trained_models\dci_reference `
  --require-model --default-execution-mode simulation
```
