from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import GROUP_KEYS, METRIC_KEYS, normalize_weights


@dataclass(slots=True)
class PolicyAdjustment:
    tick: int
    weights: dict[str, float]
    reasons: list[str]
    group_weights: dict[str, float] = field(default_factory=dict)
    affected_records: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "weights": {key: round(value, 4) for key, value in self.weights.items()},
            "group_weights": {
                key: round(value, 4) for key, value in self.group_weights.items()
            },
            "reasons": list(self.reasons),
            "affected_records": self.affected_records,
            "metrics": {key: round(value, 4) for key, value in self.metrics.items()},
        }


@dataclass(slots=True)
class PolicyState:
    weights: dict[str, float] = field(
        default_factory=lambda: normalize_weights(
            {
                "performance": 0.20,
                "completion": 0.16,
                "cost": 0.12,
                "reliability": 0.16,
                "balance": 0.14,
                "fragmentation": 0.07,
                "locality": 0.06,
                "network": 0.09,
                "security": 0.08,
                "carbon": 0.08,
            }
        )
    )
    group_weights: dict[str, float] = field(
        default_factory=lambda: normalize_weights(
            {
                "sla_quality": 0.30,
                "network_coordination": 0.20,
                "resource_efficiency": 0.18,
                "economic_cost": 0.12,
                "green_carbon": 0.20,
            }
        )
    )
    learning_rate: float = 0.28
    adjustment_history: list[PolicyAdjustment] = field(default_factory=list)

    def current_weights(self) -> dict[str, float]:
        complete_weights = {key: 0.0 for key in METRIC_KEYS}
        complete_weights.update(self.weights)
        return normalize_weights(complete_weights)

    def current_group_weights(self) -> dict[str, float]:
        complete_weights = {key: 0.0 for key in GROUP_KEYS}
        complete_weights.update(self.group_weights)
        return normalize_weights(complete_weights)

    def update_group_weights(self, new_weights: dict[str, float]) -> None:
        filtered = {
            key: float(value)
            for key, value in new_weights.items()
            if key in GROUP_KEYS
        }
        if not filtered:
            raise ValueError("group_weights must contain at least one known objective group")
        self.group_weights = normalize_weights({key: filtered.get(key, 0.0) for key in GROUP_KEYS})

    def update(
        self,
        tick: int,
        new_weights: dict[str, float],
        reasons: list[str],
        *,
        new_group_weights: dict[str, float] | None = None,
        affected_records: int = 0,
        metrics: dict[str, float] | None = None,
    ) -> None:
        self.weights = normalize_weights(new_weights)
        if new_group_weights is not None:
            self.update_group_weights(new_group_weights)
        self.adjustment_history.append(
            PolicyAdjustment(
                tick=tick,
                weights=self.current_weights(),
                group_weights=self.current_group_weights(),
                reasons=list(reasons),
                affected_records=affected_records,
                metrics=dict(metrics or {}),
            )
        )
