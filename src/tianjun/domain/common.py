from __future__ import annotations

from typing import Any

RESOURCE_FIELDS = (
    "cpu",
    "memory",
    "gpu",
    "storage",
    "mips",
    "gpu_memory",
    "storage_iops",
    "bandwidth",
)
METRIC_KEYS = (
    "performance",
    "completion",
    "cost",
    "reliability",
    "balance",
    "fragmentation",
    "locality",
    "network",
    "security",
    "carbon",
)

# The ten atomic metrics remain available for explanation and ablation.  Only
# the five semantic groups participate in the hierarchical preference layer.
# Security is intentionally excluded: mandatory security requirements are hard
# constraints and the remaining risk is applied as a non-compensable penalty.
OBJECTIVE_GROUPS: dict[str, tuple[str, ...]] = {
    "sla_quality": ("performance", "completion", "reliability"),
    "network_coordination": ("network", "locality"),
    "resource_efficiency": ("balance", "fragmentation"),
    "economic_cost": ("cost",),
    "green_carbon": ("carbon",),
}
GROUP_KEYS = tuple(OBJECTIVE_GROUPS)
GROUP_INNER_WEIGHTS: dict[str, dict[str, float]] = {
    "sla_quality": {"performance": 0.20, "completion": 0.50, "reliability": 0.30},
    "network_coordination": {"network": 0.65, "locality": 0.35},
    "resource_efficiency": {"balance": 0.40, "fragmentation": 0.60},
    "economic_cost": {"cost": 1.0},
    "green_carbon": {"carbon": 1.0},
}
METRIC_TO_GROUP = {
    metric: group
    for group, metrics in OBJECTIVE_GROUPS.items()
    for metric in metrics
}


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    positive = {key: max(0.0, value) for key, value in weights.items()}
    total = sum(positive.values())
    if total <= 0:
        even = 1.0 / len(positive)
        return {key: even for key in positive}
    return {key: value / total for key, value in positive.items()}


def round_payload(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {str(key): round_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_payload(item) for item in value]
    return value
