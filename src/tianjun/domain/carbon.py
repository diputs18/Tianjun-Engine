from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import clamp


@dataclass(slots=True)
class PowerProfile:
    """Incremental IT power model used by schedulers and simulators."""

    profile_id: str = "default"
    idle_power_w: float = 80.0
    max_power_w: float = 260.0
    gpu_idle_power_w: float = 15.0
    gpu_max_power_w: float = 300.0
    network_kwh_per_gb: float = 0.00006
    curve: str = "linear"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PowerProfile":
        payload = dict(data or {})
        return cls(
            profile_id=str(payload.get("profile_id", "default")),
            idle_power_w=max(0.0, float(payload.get("idle_power_w", 80.0))),
            max_power_w=max(0.0, float(payload.get("max_power_w", 260.0))),
            gpu_idle_power_w=max(0.0, float(payload.get("gpu_idle_power_w", 15.0))),
            gpu_max_power_w=max(0.0, float(payload.get("gpu_max_power_w", 300.0))),
            network_kwh_per_gb=max(0.0, float(payload.get("network_kwh_per_gb", 0.00006))),
            curve=str(payload.get("curve", "linear")),
        )

    def incremental_power_w(self, cpu_share: float, gpu_share: float) -> float:
        cpu = clamp(cpu_share)
        gpu = clamp(gpu_share)
        cpu_dynamic = max(0.0, self.max_power_w - self.idle_power_w) * cpu
        gpu_dynamic = max(0.0, self.gpu_max_power_w - self.gpu_idle_power_w) * gpu
        if self.curve == "quadratic":
            cpu_dynamic *= cpu
            gpu_dynamic *= gpu
        return cpu_dynamic + gpu_dynamic

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "idle_power_w": self.idle_power_w,
            "max_power_w": self.max_power_w,
            "gpu_idle_power_w": self.gpu_idle_power_w,
            "gpu_max_power_w": self.gpu_max_power_w,
            "network_kwh_per_gb": self.network_kwh_per_gb,
            "curve": self.curve,
        }


@dataclass(slots=True)
class CarbonSiteProfile:
    """Site-level PUE and time-varying electricity carbon signal."""

    site_id: str = "default-site"
    region: str = "default"
    pue: float = 1.4
    carbon_intensity_g_per_kwh: float = 520.0
    carbon_intensity_trace: dict[int, float] = field(default_factory=dict)
    carbon_signal_type: str = "average"
    timezone: str = "Asia/Shanghai"
    source_version: str = "synthetic-v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, region: str = "default") -> "CarbonSiteProfile":
        payload = dict(data or {})
        trace = {
            int(tick): max(0.0, float(value))
            for tick, value in dict(payload.get("carbon_intensity_trace") or {}).items()
        }
        return cls(
            site_id=str(payload.get("site_id", f"{region}-site")),
            region=str(payload.get("region", region)),
            pue=max(1.0, float(payload.get("pue", 1.4))),
            carbon_intensity_g_per_kwh=max(
                0.0, float(payload.get("carbon_intensity_g_per_kwh", 520.0))
            ),
            carbon_intensity_trace=trace,
            carbon_signal_type=str(payload.get("carbon_signal_type", "average")),
            timezone=str(payload.get("timezone", "Asia/Shanghai")),
            source_version=str(payload.get("source_version", "synthetic-v1")),
        )

    def intensity_at(self, tick: int) -> float:
        if not self.carbon_intensity_trace:
            return self.carbon_intensity_g_per_kwh
        eligible = [key for key in self.carbon_intensity_trace if key <= tick]
        key = max(eligible) if eligible else min(self.carbon_intensity_trace)
        return self.carbon_intensity_trace[key]

    def to_dict(self, *, tick: int | None = None) -> dict[str, Any]:
        payload = {
            "site_id": self.site_id,
            "region": self.region,
            "pue": self.pue,
            "carbon_intensity_g_per_kwh": self.carbon_intensity_g_per_kwh,
            "carbon_intensity_trace": {
                str(key): value for key, value in sorted(self.carbon_intensity_trace.items())
            },
            "carbon_signal_type": self.carbon_signal_type,
            "timezone": self.timezone,
            "source_version": self.source_version,
        }
        if tick is not None:
            payload["current_carbon_intensity_g_per_kwh"] = self.intensity_at(tick)
        return payload


def operational_carbon(
    *,
    power_w: float,
    duration_seconds: float,
    pue: float,
    carbon_intensity_g_per_kwh: float,
    network_energy_kwh: float = 0.0,
) -> dict[str, float | str]:
    energy_it_kwh = max(0.0, power_w) * max(0.0, duration_seconds) / 3_600_000.0
    facility_energy_kwh = energy_it_kwh * max(1.0, pue)
    compute_carbon_g = facility_energy_kwh * max(0.0, carbon_intensity_g_per_kwh)
    network_carbon_g = max(0.0, network_energy_kwh) * max(0.0, carbon_intensity_g_per_kwh)
    return {
        "energy_it_kwh": energy_it_kwh,
        "facility_energy_kwh": facility_energy_kwh,
        "network_energy_kwh": max(0.0, network_energy_kwh),
        "compute_carbon_g": compute_carbon_g,
        "network_carbon_g": network_carbon_g,
        "operational_carbon_g": compute_carbon_g + network_carbon_g,
        "carbon_scope": "operational_only",
    }
