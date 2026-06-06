# DCI Experiments And Model Assets

The DCI reference assets are research and reproduction material. They are not production measurements.

## Asset Classes

| Path | Role |
| --- | --- |
| `data/dci_reference/` | Raw, validation, and graph sample data for DCI reference experiments |
| `scripts/build_dci_graph_dataset.py` | Dataset construction helper |
| `scripts/train_dci_graphsage.py` | GraphSAGE training helper |
| `data/trained_models/` | Optional runtime artifacts loaded by the model runtime |
| `data/trained_models/MODEL_MANIFEST.json` | Model hash, source, purpose, and loading policy |
| `examples/cloudsimplus/` | CloudSimPlus bridge and reference experiment files |

## Reproduction Boundary

Runtime operation does not require the research datasets. The minimal control plane can start with:

```powershell
python -B main.py serve --config configs\tianjun.example.toml --offline
```

When trained model artifacts are present, the runtime may load LSTM latency and GraphSAGE stability models. If PyTorch or artifacts are unavailable and model loading is not required, the scheduler falls back to deterministic scoring.

## Large File Policy

Large model checkpoints, expanded datasets, and report copies should move to release artifacts or external storage when they outgrow normal repository review. Keep only the manifest, compact reference data, and scripts needed to reproduce or retrieve the assets.
