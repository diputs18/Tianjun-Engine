from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import round_payload


@dataclass(slots=True)
class SchedulingDecision:
    task_id: str
    node_id: str
    total_score: float
    metric_scores: dict[str, float]
    raw_metrics: dict[str, Any]
    weights: dict[str, float]
    predicted_start_tick: int
    predicted_finish_tick: int
    predicted_cost: float
    explanation: str
    network_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "node_id": self.node_id,
            "total_score": round(self.total_score, 4),
            "metric_scores": {key: round(value, 4) for key, value in self.metric_scores.items()},
            "raw_metrics": {key: round_payload(value) for key, value in self.raw_metrics.items()},
            "weights": {key: round(value, 4) for key, value in self.weights.items()},
            "predicted_start_tick": self.predicted_start_tick,
            "predicted_finish_tick": self.predicted_finish_tick,
            "predicted_cost": round(self.predicted_cost, 4),
            "explanation": self.explanation,
            "network_snapshot": {key: round_payload(value) for key, value in self.network_snapshot.items()},
        }
