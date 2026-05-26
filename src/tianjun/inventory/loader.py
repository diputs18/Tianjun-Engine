from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain import NetworkPathProfile, Node, ResourceVector


def load_inventory_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON/TOML/YAML-like simulation inventory.

    JSON is dependency-free and preferred for reproducible local demos. YAML is
    supported when PyYAML is installed, but is intentionally optional so the core
    package does not need another runtime dependency.
    """
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".toml":
        try:
            import tomllib  # type: ignore[attr-defined]
        except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
            import tomli as tomllib  # type: ignore[no-redef]
        return tomllib.loads(text)
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("YAML inventory requires PyYAML; use .json to avoid optional dependencies.") from exc
        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    return json.loads(text)


def nodes_from_inventory(config: dict[str, Any]) -> list[Node]:
    nodes = [_node_from_inventory_item(item) for item in config.get("nodes", [])]
    _apply_links(nodes, config.get("links", []))
    return nodes


def _node_from_inventory_item(data: dict[str, Any]) -> Node:
    capacity = dict(data.get("capacity", {}))
    labels = {str(item).lower() for item in data.get("labels", [])}
    # Nodes loaded from this inventory are simulation resources. Real node agents
    # should be registered from their own node config instead of this file. The
    # Dashboard uses these labels to avoid implying that a physical machine is
    # connected.
    labels.update({"simulation", "simulated-node"})
    accelerator = dict(data.get("accelerator", {}))
    storage = dict(data.get("storage", {}))
    network = dict(data.get("network", {}))
    compliance = dict(data.get("compliance", {}))
    pricing = dict(data.get("pricing", {}))

    for key in ("vendor", "model"):
        if accelerator.get(key):
            labels.add(str(accelerator[key]).lower())
    if accelerator.get("nvlink"):
        labels.add("nvlink")
    if accelerator.get("memory_gb"):
        labels.add(f"gpu-mem-{int(float(accelerator['memory_gb']))}gb")
    if storage.get("local_nvme_gb"):
        labels.add("nvme")
    if storage.get("shared_fs"):
        labels.add(str(storage["shared_fs"]).lower())
    if network.get("public_ip"):
        labels.add("public-ip")
    else:
        labels.add("no-public-egress")
    if network.get("vpc"):
        labels.add("vpc")
        labels.add("finance-vpc")
    if network.get("allowed_ingress_ports"):
        for port in network["allowed_ingress_ports"]:
            labels.add(f"port-{port}")
    for profile in compliance.get("profiles", []):
        labels.add(str(profile).lower())
    if compliance.get("kms"):
        labels.add("kms")
    if compliance.get("crypto"):
        labels.add(str(compliance["crypto"]).lower())
    if compliance.get("sm2") or compliance.get("mtls"):
        labels.add("sm2")
    if compliance.get("encrypted_transport"):
        labels.add("encrypted-transport")

    node = Node(
        node_id=str(data["node_id"]),
        region=str(data.get("region", "default")),
        labels=labels,
        capacity=ResourceVector(
            cpu=float(capacity.get("cpu", capacity.get("cpu_cores", 0.0))),
            memory=float(capacity.get("memory", capacity.get("memory_gb", 0.0))),
            gpu=float(capacity.get("gpu", accelerator.get("count", 0.0))),
            storage=float(capacity.get("storage", storage.get("local_nvme_gb", 0.0))),
        ),
        cost_per_tick=float(data.get("cost_per_tick", pricing.get("on_demand_per_hour", 60.0)))/60.0,
        base_reliability=float(data.get("base_reliability", data.get("reliability", 0.98))),
        performance_factors={str(k): float(v) for k, v in data.get("performance_factors", {}).items()},
        health_score=float(data.get("health_score", 1.0)),
        online=bool(data.get("online", True)),
        network_paths={
            str(region): NetworkPathProfile(**profile)
            for region, profile in data.get("network_paths", {}).items()
        },
    )
    return node


def _apply_links(nodes: list[Node], links: list[dict[str, Any]]) -> None:
    by_region: dict[str, list[Node]] = {}
    for node in nodes:
        by_region.setdefault(node.region, []).append(node)
    for link in links:
        source = str(link.get("source_region") or link.get("source") or "")
        target = str(link.get("target_region") or link.get("target") or "")
        if not source or not target:
            continue
        latency = link.get("latency_ms", {})
        bandwidth = link.get("bandwidth_mbps", {})
        profile = NetworkPathProfile(
            latency_ms=float(latency.get("p50", latency.get("mean", latency if isinstance(latency, (int, float)) else 10.0))),
            jitter_ms=float(latency.get("jitter", max(1.0, latency.get("p95", 15.0) - latency.get("p50", 10.0)) if isinstance(latency, dict) else 2.0)),
            bandwidth_mbps=float(bandwidth.get("min", bandwidth.get("p50", bandwidth if isinstance(bandwidth, (int, float)) else 500.0))),
            bandwidth_jitter_mbps=float(bandwidth.get("jitter", 50.0) if isinstance(bandwidth, dict) else 50.0),
            packet_loss=float(link.get("packet_loss", 0.001)),
            path_reliability=float(link.get("path_reliability", link.get("delivery_probability", 0.995))),
        )
        for node in by_region.get(target, []):
            node.network_paths[source] = profile
