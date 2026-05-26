from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

from .common import clamp
from .execution import ExecutionRecord
from .network import NetworkPathProfile
from .resource import ResourceVector
from .task import RunningTask, Task


@dataclass(slots=True)
class Node:
    node_id: str
    capacity: ResourceVector
    region: str
    labels: set[str] = field(default_factory=set)
    cost_per_tick: float = 1.0
    base_reliability: float = 0.98
    performance_factors: dict[str, float] = field(default_factory=dict)
    online: bool = True
    health_score: float = 1.0
    reliability_score: float | None = None
    running_tasks: dict[str, RunningTask] = field(default_factory=dict)
    telemetry_tick: int = 0
    network_paths: dict[str, NetworkPathProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.reliability_score = clamp(
            self.base_reliability if self.reliability_score is None else self.reliability_score,
            0.35,
            0.999,
        )
        self.performance_factors = {
            task_type: clamp(factor, 0.35, 3.5)
            for task_type, factor in self.performance_factors.items()
        }
        self.network_paths = {
            str(region): (
                profile if isinstance(profile, NetworkPathProfile) else NetworkPathProfile(**profile)
            )
            for region, profile in self.network_paths.items()
        }

    def used(self) -> ResourceVector:
        total = ResourceVector()
        for running in self.running_tasks.values():
            total = total + running.allocation
        return total

    def available(self) -> ResourceVector:
        return (self.capacity - self.used()).clamp_non_negative()

    def can_host_now(self, task: Task) -> bool:
        if not self.online or self.health_score < 0.3:
            return False
        if self.node_id in task.forbidden_nodes:
            return False
        if task.allowed_regions and self.region not in task.allowed_regions:
            return False
        if task.preferred_labels and not task.preferred_labels.issubset(self.labels):
            return False
        return task.demand.fits_in(self.available())

    def performance_for(self, task_type: str) -> float:
        return clamp(self.performance_factors.get(task_type, 1.0), 0.35, 3.5)

    def predict_duration(self, task: Task) -> int:
        factor = self.performance_for(task.task_type)
        return max(1, ceil(task.estimated_duration / factor))

    def dominant_utilization(self) -> float:
        return self.used().dominant_share_against(self.capacity)

    def dominant_utilization_after(self, demand: ResourceVector) -> float:
        return (self.used() + demand).dominant_share_against(self.capacity)

    def remaining_after(self, demand: ResourceVector) -> ResourceVector:
        return (self.available() - demand).clamp_non_negative()

    def fragmentation_after(self, demand: ResourceVector) -> float:
        remaining = self.remaining_after(demand)
        score = remaining.fragmentation_score_against(self.capacity)
        if demand.gpu == 0 and self.capacity.gpu > 0:
            score -= 0.25
        if demand.gpu > 0 and self.capacity.gpu >= demand.gpu:
            score += 0.08
        return clamp(score)

    def locality_score(self, task: Task) -> float:
        score = 0.75
        if task.data_region is not None:
            score = 1.0 if task.data_region == self.region else 0.2
        if task.preferred_labels:
            matched = len(task.preferred_labels.intersection(self.labels)) / len(task.preferred_labels)
            score = (score + matched) / 2.0
        return clamp(score)

    def path_profile_for(self, source_region: str | None) -> NetworkPathProfile:
        if source_region and source_region in self.network_paths:
            return self.network_paths[source_region]
        if source_region is not None and source_region == self.region:
            return NetworkPathProfile()
        return NetworkPathProfile(
            latency_ms=42.0,
            jitter_ms=10.0,
            bandwidth_mbps=280.0,
            bandwidth_jitter_mbps=120.0,
            packet_loss=0.018,
            path_reliability=0.94,
        )

    def update_after_record(self, task: Task, record: ExecutionRecord) -> None:
        observed_factor = clamp(task.estimated_duration / max(1.0, record.actual_duration), 0.35, 3.5)
        previous_factor = self.performance_for(task.task_type)
        self.performance_factors[task.task_type] = clamp(
            (previous_factor * 0.7) + (observed_factor * 0.3),
            0.35,
            3.5,
        )

        signal = 1.0 if record.success else 0.0
        self.reliability_score = clamp((self.reliability_score * 0.82) + (signal * 0.18), 0.35, 0.999)
        self.health_score = clamp((self.health_score * 0.9) + (signal * 0.1), 0.3, 1.0)
        if not record.success:
            self.health_score = clamp(self.health_score - 0.04, 0.3, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "region": self.region,
            "labels": sorted(self.labels),
            "capacity": self.capacity.to_dict(),
            "available": self.available().to_dict(),
            "cost_per_tick": self.cost_per_tick,
            "base_reliability": self.base_reliability,
            "reliability_score": round(self.reliability_score or 0.0, 4),
            "health_score": round(self.health_score, 4),
            "online": self.online,
            "telemetry_tick": self.telemetry_tick,
            "performance_factors": {key: round(value, 4) for key, value in self.performance_factors.items()},
            "running_tasks": sorted(self.running_tasks.keys()),
            "network_paths": {
                region: profile.to_dict()
                for region, profile in sorted(self.network_paths.items(), key=lambda item: item[0])
            },
        }
