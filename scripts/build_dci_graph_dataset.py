from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


FEATURE_NAMES = [
    "last_log_rt",
    "mean_log_rt",
    "std_log_rt",
    "trend_log_rt",
    "last_log_link_pressure",
    "mean_log_link_pressure",
    "std_log_link_pressure",
    "trend_log_link_pressure",
    "last_cpu_utilization",
    "mean_cpu_utilization",
    "last_memory_utilization",
    "mean_memory_utilization",
    "log_in_degree",
    "log_out_degree",
    "log_total_degree",
    "log_robust_path_latency",
]
PROBE_NETWORK_SENSITIVITY = 0.55


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def read_snapshots(paths: list[Path]) -> list[dict[str, Any]]:
    snapshots = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    snapshots.append(json.loads(line))
    return snapshots


def canonical_profile(profile: dict[str, float]) -> dict[str, float]:
    aliases = {
        "latency_ms": "latencyMs",
        "jitter_ms": "jitterMs",
        "bandwidth_mbps": "bandwidthMbps",
        "bandwidth_jitter_mbps": "bandwidthJitterMbps",
        "packet_loss": "packetLoss",
        "path_reliability": "pathReliability",
    }
    return {
        name: float(profile[name] if name in profile else profile[alias])
        for name, alias in aliases.items()
    }


def bandwidth_utilization(profile: dict[str, float]) -> float:
    jitter_ratio = max(0.0, profile["bandwidth_jitter_mbps"]) / max(50.0, profile["bandwidth_mbps"])
    loss_pressure = clamp(profile["packet_loss"], 0.0, 0.45) / 0.08
    return clamp((jitter_ratio * 0.72) + (loss_pressure * 0.20) + 0.08)


def synthesized_latency_history(profile: dict[str, float]) -> list[float]:
    base = max(1.0, profile["latency_ms"])
    jitter = max(0.0, profile["jitter_ms"])
    loss_bump = clamp(profile["packet_loss"], 0.0, 0.45) * 120.0
    return [
        max(1.0, base - jitter * 0.45),
        max(1.0, base + jitter * 0.15),
        max(1.0, base - jitter * 0.10 + loss_bump * 0.20),
        max(1.0, base + jitter * 0.40),
        max(1.0, base + jitter * 0.72 + loss_bump * 0.35),
    ]


def pressure_history(profile: dict[str, float], node_load: float) -> list[float]:
    base = max(0.0, PROBE_NETWORK_SENSITIVITY + node_load + bandwidth_utilization(profile))
    loss = clamp(profile["packet_loss"] / 0.05)
    return [
        max(0.0, base * 0.75),
        max(0.0, base * 0.92),
        max(0.0, base + loss * 0.15),
        max(0.0, base * 1.08),
        max(0.0, base * 1.15 + loss * 0.20),
    ]


def robust_latency(profile: dict[str, float]) -> float:
    return max(1.0, profile["latency_ms"] + 1.3 * profile["jitter_ms"] + clamp(profile["packet_loss"], 0.0, 0.45) * 180.0)


def feature_vector(node: dict[str, Any], profile: dict[str, float]) -> list[float]:
    profile = canonical_profile(profile)
    cpu = clamp(float(node["cpu_utilization"]))
    memory = clamp(float(node["memory_utilization"]))
    node_load = (cpu + memory) / 2.0
    rt_values = [math.log1p(value) for value in synthesized_latency_history(profile)]
    pressure_values = [math.log1p(value) for value in pressure_history(profile, node_load)]
    in_degree = float(len(node["network_paths"]))
    out_degree = 5.0
    return [
        rt_values[-1],
        mean(rt_values),
        pstdev(rt_values),
        rt_values[-1] - rt_values[0],
        pressure_values[-1],
        mean(pressure_values),
        pstdev(pressure_values),
        pressure_values[-1] - pressure_values[0],
        cpu,
        cpu,
        memory,
        memory,
        math.log1p(in_degree),
        math.log1p(out_degree),
        math.log1p(in_degree + out_degree),
        math.log1p(robust_latency(profile)),
    ]


def qos_stability(profile: dict[str, float], baseline_latency: float, baseline_bandwidth: float) -> float:
    profile = canonical_profile(profile)
    latency = 1.0 / (1.0 + max(0.0, profile["latency_ms"] - baseline_latency) / max(5.0, baseline_latency))
    jitter = 1.0 / (1.0 + profile["jitter_ms"] / max(1.0, baseline_latency))
    bandwidth = clamp(profile["bandwidth_mbps"] / max(1.0, baseline_bandwidth))
    loss = clamp(1.0 - profile["packet_loss"] / 0.05)
    reliability = clamp(profile["path_reliability"])
    return clamp(latency * 0.24 + jitter * 0.16 + bandwidth * 0.22 + loss * 0.20 + reliability * 0.18)


def neighbor_distances(snapshot: dict[str, Any], node_id: str) -> dict[str, float]:
    attachments = snapshot["compute_attachments"]
    source_anchor = attachments[node_id]
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in snapshot["topology_edges"]:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])
    distances = {source_anchor: 0.0}
    frontier = [(0.0, source_anchor)]
    while frontier:
        distance, current = min(frontier)
        frontier.remove((distance, current))
        if distance != distances[current]:
            continue
        edge_values = {
            edge["target"] if edge["source"] == current else edge["source"]: float(edge["propagation_delay_ms"])
            for edge in snapshot["topology_edges"]
            if edge["source"] == current or edge["target"] == current
        }
        for target in adjacency[current]:
            candidate = distance + edge_values[target]
            if candidate < distances.get(target, float("inf")):
                distances[target] = candidate
                frontier.append((candidate, target))
    return {
        candidate: distances[anchor]
        for candidate, anchor in attachments.items()
        if candidate != node_id and anchor in distances
    }


def build_samples(snapshots: list[dict[str, Any]], future_window: int) -> list[dict[str, Any]]:
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        by_run[str(snapshot["experiment_run_id"])].append(snapshot)
    samples: list[dict[str, Any]] = []
    for run_id, records in sorted(by_run.items()):
        records.sort(key=lambda row: float(row["tick_seconds"]))
        baseline_latency: dict[tuple[str, str], float] = {}
        baseline_bandwidth: dict[tuple[str, str], float] = {}
        for record in records:
            for node in record["compute_nodes"]:
                for region, profile in node["network_paths"].items():
                    profile = canonical_profile(profile)
                    key = (node["node_id"], region)
                    baseline_latency[key] = min(baseline_latency.get(key, float("inf")), float(profile["latency_ms"]))
                    baseline_bandwidth[key] = max(baseline_bandwidth.get(key, 0.0), float(profile["bandwidth_mbps"]))
        for index, record in enumerate(records[:-future_window]):
            future = records[index + 1 : index + future_window + 1]
            nodes = {node["node_id"]: node for node in record["compute_nodes"]}
            for node_id, node in nodes.items():
                distances = neighbor_distances(record, node_id)
                neighbor_ids = sorted(distances, key=lambda neighbor_id: (distances[neighbor_id], neighbor_id))
                for source_region, profile in node["network_paths"].items():
                    self_features = feature_vector(node, profile)
                    neighbor_features = [
                        feature_vector(nodes[neighbor_id], nodes[neighbor_id]["network_paths"][source_region])
                        for neighbor_id in neighbor_ids
                    ]
                    weights = [1.0 / max(0.1, distances[neighbor_id]) for neighbor_id in neighbor_ids]
                    weight_sum = sum(weights)
                    averaged_neighbor = [
                        sum(vector[position] * weights[index] for index, vector in enumerate(neighbor_features)) / weight_sum
                        for position in range(len(self_features))
                    ] if neighbor_features else list(self_features)
                    future_scores = []
                    for future_record in future:
                        future_nodes = {value["node_id"]: value for value in future_record["compute_nodes"]}
                        future_profile = future_nodes[node_id]["network_paths"][source_region]
                        key = (node_id, source_region)
                        future_scores.append(qos_stability(future_profile, baseline_latency[key], baseline_bandwidth[key]))
                    samples.append({
                        "run_id": run_id,
                        "scenario": record["disturbance"],
                        "tick_seconds": record["tick_seconds"],
                        "node_id": node_id,
                        "source_region": source_region,
                        "topology_id": record["topology_id"],
                        "neighbor_ids": neighbor_ids,
                        "neighbor_distance_ms": distances,
                        "self_features": self_features,
                        "neighbor_features": averaged_neighbor,
                        "target_stability": mean(future_scores),
                        "fault_active": any(bool(row["dci_degraded"]) for row in future),
                    })
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Build topology-aware GNN samples from DCI JSONL snapshots.")
    parser.add_argument("snapshots", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--future-window", type=int, default=3)
    args = parser.parse_args()
    samples = build_samples(read_snapshots(args.snapshots), max(1, args.future_window))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=True) + "\n")
    manifest = {
        "dataset": "huawei_public_case_reference_dci_cloudsimplus",
        "samples": len(samples),
        "feature_names": FEATURE_NAMES,
        "target": "future_qos_stability_score_0_to_1",
        "label_definition": "Mean future-window score composed from observed latency, jitter, bandwidth, packet loss and path reliability.",
        "future_window_snapshots": max(1, args.future_window),
        "provenance_boundary": {
            "topology_structure": "public_case_abstraction",
            "numeric_values": "calibrated_simulation_assumptions_not_vendor_telemetry",
            "compute_nodes": "cloudsimplus_vm_resources_not_physical_inventory",
            "named_locations": "simulation_placement_labels_not_vendor_disclosed_sites",
            "service_regions": "three_simulated_deployment_zones_each_bound_to_one_simulated_access_point",
            "simulated_access_points": "east_to_dc1_west_to_dc2_south_to_dc3",
        },
    }
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
