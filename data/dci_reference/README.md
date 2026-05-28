# DCI Topology-Aware GNN Dataset

This directory contains simulation observations and a derived labeled dataset
for the Tianjun topology-aware GNN path.

## Provenance Boundary

| Item | Status | Basis |
| --- | --- | --- |
| `DC1 -> Border1 -> PE1 -> IPCORE -> PE3 -> Border2 -> DC2` | Case-derived structure | `D:\QQ_DownloadFile\算力网络 应用解决案例.pptx`, slides 2-3 |
| `PE3 -> Border3 -> DC3` | Simulation extension | Added to support one simulated access point per Hermes deployment zone |
| `User-Access -> PE3` | Case-derived structure | Same presentation, slide 3 |
| Site geography | Not asserted | The slides name `DC1` and `DC2`; `DC3` and the six named cities are simulation placement labels only |
| VM/host CPU, RAM and storage | Simulated inventory | CloudSim Plus objects, not discovered physical servers |
| Link delay, bandwidth, jitter, loss and fault amplitudes | Calibrated experimental parameters | BRITE topology and reproducible scenario formulas, not Huawei telemetry |

This dataset is therefore suitable for repeatable topology-aware scheduling
experiments. It must not be represented as Huawei production monitoring data
or a verified physical node inventory.

The current generated corpus observes 24 simulated VMs in each topology
snapshot. Hermes exposes three simulation deployment zones with eight VMs
each: `east` (Beijing/Hangzhou) attached to `DC1`, `west`
(Chengdu/Chongqing) attached to `DC2`, and `south` (Guangzhou/Shenzhen)
attached to `DC3` in the simulation graph.

## Contents

- `raw/*.jsonl`: raw CloudSim Plus topology snapshots from independent
  `normal` and transition-`fault` runs.
- `dci_graph_samples.jsonl`: GNN samples built from raw snapshots.
- `dci_graph_samples.manifest.json`: label definition, feature names and
  provenance boundary.
- `validation/*.jsonl`: held-out online validation snapshots for normal and
  already-degraded (`fault-active`) operation.

Each labeled sample uses the registered physical topology to obtain reachable
compute neighbors and weights their feature aggregation by inverse shortest
propagation delay. Its label is the mean future-window QoS stability score
formed from observed latency, jitter, bandwidth, packet loss and path
reliability; it is not copied from the scenario fault flag.

## Regeneration

After producing raw snapshots with
`org.cloudsimplus.examples.HuaweiDciTianjunExperiment`, run:

```powershell
$raw = Get-ChildItem data\dci_reference\raw\*.jsonl | Select-Object -ExpandProperty FullName
python scripts\build_dci_graph_dataset.py @raw `
  --output data\dci_reference\dci_graph_samples.jsonl --future-window 3

python scripts\train_dci_graphsage.py data\dci_reference\dci_graph_samples.jsonl `
  --output-dir data\trained_models\dci_reference --epochs 100
```

Load the DCI-specific model when starting Tianjun:

```powershell
python -B main.py serve --offline --model-dir data\trained_models\dci_reference `
  --require-model --default-execution-mode simulation
```
