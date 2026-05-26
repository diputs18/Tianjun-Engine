from __future__ import annotations

from typing import Any

RESOURCE_FIELDS = ("cpu", "memory", "gpu", "storage")
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
)


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
