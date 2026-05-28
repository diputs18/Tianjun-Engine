from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean

import torch
from torch import nn


class GraphSageRegressor(nn.Module):
    def __init__(self, input_size: int, hidden_size: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_size * 2, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1),
            nn.Sigmoid(),
        )

    def forward(self, self_features: torch.Tensor, neighbor_features: torch.Tensor) -> torch.Tensor:
        return self.head(self.encoder(torch.cat([self_features, neighbor_features], dim=-1))).squeeze(-1)


def load_samples(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def grouped_split(samples: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    run_ids = sorted({sample["run_id"] for sample in samples})
    rng = random.Random(seed)
    rng.shuffle(run_ids)
    split_index = max(1, int(round(len(run_ids) * 0.75)))
    test_ids = set(run_ids[split_index:] or run_ids[-1:])
    train = [sample for sample in samples if sample["run_id"] not in test_ids]
    test = [sample for sample in samples if sample["run_id"] in test_ids]
    if not train:
        train = samples[:-max(1, len(samples) // 4)]
        test = samples[len(train):]
    return train, test


def scaler(samples: list[dict]) -> tuple[list[float], list[float]]:
    values = [sample["self_features"] for sample in samples] + [sample["neighbor_features"] for sample in samples]
    width = len(values[0])
    means = [mean(row[index] for row in values) for index in range(width)]
    stds = []
    for index in range(width):
        variance = mean((row[index] - means[index]) ** 2 for row in values)
        stds.append(max(variance ** 0.5, 1e-6))
    return means, stds


def tensorize(samples: list[dict], means: list[float], stds: list[float]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    normalize = lambda row: [(value - means[index]) / stds[index] for index, value in enumerate(row)]
    self_features = torch.tensor([normalize(row["self_features"]) for row in samples], dtype=torch.float32)
    neighbor_features = torch.tensor([normalize(row["neighbor_features"]) for row in samples], dtype=torch.float32)
    targets = torch.tensor([row["target_stability"] for row in samples], dtype=torch.float32)
    return self_features, neighbor_features, targets


def metrics(model: nn.Module, data: tuple[torch.Tensor, torch.Tensor, torch.Tensor]) -> dict[str, float]:
    model.eval()
    with torch.no_grad():
        pred = model(data[0], data[1])
    errors = (pred - data[2]).abs()
    return {
        "mae_stability": float(errors.mean()),
        "rmse_stability": float(torch.sqrt(((pred - data[2]) ** 2).mean())),
        "pred_mean": float(pred.mean()),
        "target_mean": float(data[2].mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the DCI topology-aware GraphSAGE-style stability regressor.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260527)
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    samples = load_samples(args.dataset)
    if len(samples) < 8:
        raise ValueError("DCI training requires at least 8 labeled topology samples.")
    train, test = grouped_split(samples, args.seed)
    means, stds = scaler(train)
    train_data = tensorize(train, means, stds)
    test_data = tensorize(test, means, stds)
    model = GraphSageRegressor(len(means), args.hidden_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.006, weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    loss_curve = []
    for _ in range(args.epochs):
        model.train()
        optimizer.zero_grad()
        loss = loss_fn(model(train_data[0], train_data[1]), train_data[2])
        loss.backward()
        optimizer.step()
        loss_curve.append(float(loss.detach()))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state": model.state_dict(),
        "scaler": {"mean": means, "std": stds},
        "input_size": len(means),
        "hidden_size": args.hidden_size,
        "target_name": "path_stability_score",
        "feature_names": [
            "last_log_rt", "mean_log_rt", "std_log_rt", "trend_log_rt",
            "last_log_link_pressure", "mean_log_link_pressure", "std_log_link_pressure", "trend_log_link_pressure",
            "last_cpu_utilization", "mean_cpu_utilization", "last_memory_utilization", "mean_memory_utilization",
            "log_in_degree", "log_out_degree", "log_total_degree", "log_robust_path_latency",
        ],
    }
    model_path = args.output_dir / "graphsage_stability_model.pt"
    torch.save(checkpoint, model_path)
    report = {
        "dataset": "huawei_public_case_reference_dci_cloudsimplus",
        "model": "GraphSAGE-style topology-neighbor stability regressor",
        "samples": len(samples),
        "train_samples": len(train),
        "test_samples": len(test),
        "split": "experiment_run_id_group_split",
        "target": "future_qos_stability_score_0_to_1",
        "metrics": metrics(model, test_data),
        "loss_final": loss_curve[-1],
        "model_path": str(model_path),
        "provenance_boundary": {
            "topology_structure": "public_case_abstraction",
            "numeric_values": "calibrated_simulation_assumptions_not_vendor_telemetry",
            "compute_nodes": "cloudsimplus_vm_resources_not_physical_inventory",
            "named_locations": "simulation_placement_labels_not_vendor_disclosed_sites",
            "service_regions": "three_simulated_deployment_zones_each_bound_to_one_simulated_access_point",
            "simulated_access_points": "east_to_dc1_west_to_dc2_south_to_dc3",
        },
    }
    (args.output_dir / "graphsage_stability_report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
