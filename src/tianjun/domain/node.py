from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

from .common import clamp
from .carbon import CarbonSiteProfile, PowerProfile, operational_carbon
from .execution import ExecutionRecord
from .network import NetworkPathProfile
from .resource import ResourceVector
from .task import RunningTask, Task


SERVICE_REGION_BY_LOCATION = {
    "beijing": "east",
    "hangzhou": "east",
    "shanghai": "east",
    "tianjin": "east",
    "nanjing": "east",
    "suzhou": "east",
    "wuxi": "east",
    "ningbo": "east",
    "hefei": "east",
    "jinan": "east",
    "qingdao": "east",
    "chengdu": "west",
    "chongqing": "west",
    "xian": "west",
    "kunming": "west",
    "guiyang": "west",
    "lanzhou": "west",
    "urumqi": "west",
    "guangzhou": "south",
    "shenzhen": "south",
    "dongguan": "south",
    "huizhou": "south",
    "zhuhai": "south",
    "foshan": "south",
    "zhongshan": "south",
    "xiamen": "south",
    "fuzhou": "south",
    "nanning": "south",
    "haikou": "south",
    "wuhan": "wuhan",
}


@dataclass(slots=True)
class Node:
    node_id: str
    capacity: ResourceVector
    region: str
    location: str | None = None
    service_region: str | None = None
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
    site_id: str | None = None
    power_profile: PowerProfile = field(default_factory=PowerProfile)
    carbon_profile: CarbonSiteProfile = field(default_factory=CarbonSiteProfile)
    trust_level: str = "high"
    isolation_levels: set[str] = field(default_factory=lambda: {"none", "process", "container", "namespace"})
    encrypted_transport: bool = True
    resource_version: int = 0
    current_power_w: float = 0.0
    # Host-level totals come only from heartbeat telemetry. Task-attributed totals
    # are kept separately to avoid charging the same energy twice.
    energy_kwh_total: float = 0.0
    operational_carbon_g_total: float = 0.0
    task_energy_kwh_total: float = 0.0
    task_operational_carbon_g_total: float = 0.0
    carbon_signal_timestamp: float | None = None
    runtime_telemetry: dict[str, float] = field(default_factory=dict)
    telemetry_source: str | None = None
    simulation_tick: float | None = None

    def __post_init__(self) -> None:
        self.location = self.location or self.region
        self.service_region = (
            self.service_region
            or SERVICE_REGION_BY_LOCATION.get(str(self.location).lower())
            or self.location
        )
        self.site_id = self.site_id or self.carbon_profile.site_id or f"{self.region}-site"
        self.carbon_profile.site_id = self.site_id
        if self.carbon_profile.region == "default":
            self.carbon_profile.region = self.region
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
        self.runtime_telemetry = {
            str(key): clamp(float(value))
            for key, value in self.runtime_telemetry.items()
            if value is not None
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
        if task.allowed_regions and not any(self.matches_deployment_region(region) for region in task.allowed_regions):
            return False
        if not task.allow_region_shift and task.network_source() and not self.matches_deployment_region(task.network_source() or ""):
            return False
        if task.preferred_labels and not task.preferred_labels.issubset(self.labels):
            return False
        trust_rank = {"low": 0, "medium": 1, "high": 2}
        if trust_rank.get(self.trust_level, 0) < trust_rank.get(task.security_level, 1):
            return False
        if task.isolation_level not in self.isolation_levels:
            return False
        if task.require_encrypted_transport and not self.encrypted_transport:
            return False
        return task.demand.fits_in(self.available())

    def predict_operational_carbon(self, task: Task, duration_seconds: float, tick: int) -> dict[str, float | str]:
        cpu_share = (
            clamp(float(task.expected_cpu_utilization))
            if task.expected_cpu_utilization is not None
            else task.demand.cpu / max(1.0, self.capacity.cpu)
        )
        gpu_share = task.demand.gpu / max(1.0, self.capacity.gpu) if self.capacity.gpu > 0 else 0.0
        power_w = self.power_profile.incremental_power_w(cpu_share, gpu_share)
        network_energy = task.estimated_input_size_gb() * self.power_profile.network_kwh_per_gb
        result = operational_carbon(
            power_w=power_w,
            duration_seconds=duration_seconds,
            pue=self.carbon_profile.pue,
            carbon_intensity_g_per_kwh=self.carbon_profile.intensity_at(tick),
            network_energy_kwh=network_energy,
        )
        result["power_w"] = power_w
        result["carbon_intensity_g_per_kwh"] = self.carbon_profile.intensity_at(tick)
        result["pue"] = self.carbon_profile.pue
        return result

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
            score = 1.0 if self.matches_deployment_region(task.data_region) else 0.2
        if task.preferred_labels:
            matched = len(task.preferred_labels.intersection(self.labels)) / len(task.preferred_labels)
            score = (score + matched) / 2.0
        return clamp(score)

    def matches_deployment_region(self, region: str) -> bool:
        return region in {self.service_region, self.location, self.region}

    def path_profile_for(self, source_region: str | None) -> NetworkPathProfile:
        if source_region and source_region in self.network_paths:
            return self.network_paths[source_region]
        if source_region is not None and source_region == self.region:
            return NetworkPathProfile()
        if source_region is None and self.network_paths:
            return min(self.network_paths.values(), key=lambda profile: profile.robust_latency_ms())
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
            "location": self.location,
            "service_region": self.service_region,
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
            "site_id": self.site_id,
            "power_profile": self.power_profile.to_dict(),
            "carbon_profile": self.carbon_profile.to_dict(tick=self.telemetry_tick),
            "trust_level": self.trust_level,
            "isolation_levels": sorted(self.isolation_levels),
            "encrypted_transport": self.encrypted_transport,
            "resource_version": self.resource_version,
            "current_power_w": round(self.current_power_w, 6),
            "energy_kwh_total": round(self.energy_kwh_total, 8),
            "operational_carbon_g_total": round(self.operational_carbon_g_total, 6),
            "task_energy_kwh_total": round(self.task_energy_kwh_total, 8),
            "task_operational_carbon_g_total": round(self.task_operational_carbon_g_total, 6),
            "carbon_signal_timestamp": self.carbon_signal_timestamp,
            "runtime_telemetry": {
                key: round(value, 6)
                for key, value in sorted(self.runtime_telemetry.items())
            },
            "telemetry_source": self.telemetry_source,
            "simulation_tick": self.simulation_tick,
        }
