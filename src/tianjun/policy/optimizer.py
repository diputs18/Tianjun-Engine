from __future__ import annotations

from math import exp
from statistics import mean, pstdev
from typing import Iterable

from ..domain import GROUP_KEYS, METRIC_KEYS, ExecutionRecord, Node, PolicyState, clamp, normalize_weights


class PolicyOptimizer:
    """Adapt atomic and semantic objective weights from observed scheduling outcomes."""

    def __init__(
        self,
        history_window: int = 12,
        min_history: int = 4,
        adjustment_strength: float = 1.0,
        max_weight_delta: float = 0.03,
    ) -> None:
        self.history_window = history_window
        self.min_history = min_history
        self.adjustment_strength = adjustment_strength
        self.max_weight_delta = max_weight_delta

    def update_policy(
        self,
        policy_state: PolicyState,
        recent_records: Iterable[ExecutionRecord],
        nodes: Iterable[Node],
        tick: int,
        context: dict[str, float] | None = None,
    ) -> list[str]:
        records = list(recent_records)[-self.history_window :]
        nodes = list(nodes)
        if len(records) < self.min_history:
            return []

        sla_rate = mean(1.0 if record.sla_met else 0.0 for record in records)
        failure_rate = mean(1.0 if not record.success else 0.0 for record in records)

        budget_records = [record for record in records if record.within_budget is not None]
        budget_violation_rate = (
            mean(1.0 if not record.within_budget else 0.0 for record in budget_records)
            if budget_records
            else 0.0
        )

        utilizations = [node.dominant_utilization() for node in nodes if node.online]
        imbalance = pstdev(utilizations) if len(utilizations) > 1 else 0.0
        feedback = dict(context or {})
        observed = {
            "sla_shortfall": self._shortfall_pressure(sla_rate, 0.85),
            "failure": self._excess_pressure(failure_rate, 0.12),
            "budget": self._excess_pressure(budget_violation_rate, 0.20),
            "imbalance": self._excess_pressure(imbalance, 0.18),
            "gpu_wait": self._excess_pressure(feedback.get("gpu_wait_ratio", 0.0), 0.25),
            "locality_miss": self._excess_pressure(feedback.get("locality_miss_rate", 0.0), 0.20),
            "network_instability": self._excess_pressure(
                feedback.get("network_instability", 0.0), 0.33
            ),
            "network_pressure": self._excess_pressure(
                feedback.get("network_pressure", 0.0), 0.25
            ),
            "carbon_budget": self._excess_pressure(
                feedback.get("carbon_budget_violation_rate", 0.0), 0.20
            ),
        }

        atomic_pressure = {key: 0.0 for key in METRIC_KEYS}
        atomic_pressure.update(
            {
                "performance": self._combine(
                    0.75 * observed["sla_shortfall"],
                    0.35 * observed["network_pressure"],
                ),
                "completion": self._combine(
                    observed["sla_shortfall"],
                    0.35 * observed["network_pressure"],
                ),
                "reliability": self._combine(
                    0.65 * observed["sla_shortfall"],
                    observed["failure"],
                    0.40 * observed["network_instability"],
                ),
                "cost": observed["budget"],
                "balance": observed["imbalance"],
                "fragmentation": 0.85 * observed["gpu_wait"],
                "locality": 0.80 * observed["locality_miss"],
                "network": self._combine(
                    0.90 * observed["network_instability"],
                    0.75 * observed["network_pressure"],
                ),
                "carbon": observed["carbon_budget"],
            }
        )
        group_pressure = {key: 0.0 for key in GROUP_KEYS}
        group_pressure.update(
            {
                "sla_quality": self._combine(
                    observed["sla_shortfall"],
                    0.85 * observed["failure"],
                    0.25 * observed["network_pressure"],
                ),
                "network_coordination": self._combine(
                    0.90 * observed["network_instability"],
                    0.75 * observed["network_pressure"],
                    0.70 * observed["locality_miss"],
                ),
                "resource_efficiency": self._combine(
                    0.90 * observed["imbalance"],
                    0.80 * observed["gpu_wait"],
                ),
                "economic_cost": observed["budget"],
                "green_carbon": observed["carbon_budget"],
            }
        )

        reasons = self._reasons(observed)
        if not reasons:
            return []

        current_atomic = policy_state.current_weights()
        current_groups = policy_state.current_group_weights()
        target_atomic = self._pressure_target(current_atomic, atomic_pressure)
        target_groups = self._pressure_target(current_groups, group_pressure)
        smoothed_atomic = self._smooth_and_bound(
            current_atomic, target_atomic, policy_state.learning_rate
        )
        smoothed_groups = self._smooth_and_bound(
            current_groups, target_groups, policy_state.learning_rate
        )
        policy_state.update(
            tick=tick,
            new_weights=smoothed_atomic,
            new_group_weights=smoothed_groups,
            reasons=reasons,
            affected_records=len(records),
            metrics={
                "sla_rate": sla_rate,
                "failure_rate": failure_rate,
                "budget_violation_rate": budget_violation_rate,
                "load_imbalance": imbalance,
                "gpu_wait_ratio": float(feedback.get("gpu_wait_ratio", 0.0)),
                "locality_miss_rate": float(feedback.get("locality_miss_rate", 0.0)),
                "network_instability": float(feedback.get("network_instability", 0.0)),
                "network_pressure": float(feedback.get("network_pressure", 0.0)),
                "carbon_budget_violation_rate": float(
                    feedback.get("carbon_budget_violation_rate", 0.0)
                ),
                **{f"pressure_{key}": value for key, value in observed.items()},
            },
        )
        return reasons

    @staticmethod
    def _excess_pressure(value: float, threshold: float) -> float:
        if value <= threshold:
            return 0.0
        return clamp((float(value) - threshold) / max(1e-9, 1.0 - threshold))

    @staticmethod
    def _shortfall_pressure(value: float, threshold: float) -> float:
        if value >= threshold:
            return 0.0
        return clamp((threshold - float(value)) / max(1e-9, threshold))

    @staticmethod
    def _combine(*values: float) -> float:
        return clamp(sum(max(0.0, float(value)) for value in values))

    def _pressure_target(
        self,
        current: dict[str, float],
        pressure: dict[str, float],
    ) -> dict[str, float]:
        # A tiny floor lets a manually zeroed objective recover when evidence becomes strong.
        return normalize_weights(
            {
                key: max(0.005, float(value))
                * exp(self.adjustment_strength * clamp(float(pressure.get(key, 0.0))))
                for key, value in current.items()
            }
        )

    def _smooth_and_bound(
        self,
        current: dict[str, float],
        target: dict[str, float],
        learning_rate: float,
    ) -> dict[str, float]:
        bounded: dict[str, float] = {}
        lower: dict[str, float] = {}
        upper: dict[str, float] = {}
        rate = clamp(float(learning_rate))
        for key, current_value in current.items():
            candidate = (1.0 - rate) * current_value + rate * target[key]
            lower[key] = max(0.0, current_value - self.max_weight_delta)
            upper[key] = min(1.0, current_value + self.max_weight_delta)
            bounded[key] = min(upper[key], max(lower[key], candidate))

        # Project back onto the unit simplex without undoing the per-key cap.
        for _ in range(len(bounded) + 1):
            residual = 1.0 - sum(bounded.values())
            if abs(residual) <= 1e-12:
                break
            if residual > 0:
                capacity = {key: upper[key] - value for key, value in bounded.items()}
            else:
                capacity = {key: value - lower[key] for key, value in bounded.items()}
            available = sum(value for value in capacity.values() if value > 1e-12)
            if available <= 1e-12:
                break
            for key, room in capacity.items():
                if room <= 1e-12:
                    continue
                change = min(abs(residual) * room / available, room)
                bounded[key] += change if residual > 0 else -change
        return bounded

    @staticmethod
    def _reasons(pressure: dict[str, float]) -> list[str]:
        reason_map = {
            "sla_shortfall": "SLA fulfillment is below the stable band; SLA-quality weights were increased proportionally.",
            "failure": "Execution failures exceed the stable band; reliability and SLA-quality weights were increased.",
            "budget": "Budget violations exceed the stable band; cost and economic-cost weights were increased.",
            "imbalance": "Cluster imbalance exceeds the stable band; balance and resource-efficiency weights were increased.",
            "gpu_wait": "GPU waiting pressure exceeds the stable band; fragmentation and resource-efficiency weights were increased.",
            "locality_miss": "Locality misses exceed the stable band; locality and network-coordination weights were increased.",
            "network_instability": "Network uncertainty exceeds the stable band; network, reliability and network-coordination weights were increased.",
            "network_pressure": "Network-delay pressure exceeds the stable band; network and SLA-related weights were increased.",
            "carbon_budget": "Carbon-budget violations exceed the stable band; carbon and green-carbon weights were increased.",
        }
        return [reason_map[key] for key, value in pressure.items() if value > 0.0]
