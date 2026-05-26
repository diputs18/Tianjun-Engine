from __future__ import annotations

from dataclasses import dataclass

from .common import clamp


@dataclass(slots=True)
class NetworkPathProfile:
    latency_ms: float = 12.0
    jitter_ms: float = 2.5
    bandwidth_mbps: float = 900.0
    bandwidth_jitter_mbps: float = 80.0
    packet_loss: float = 0.002
    path_reliability: float = 0.992

    def robust_latency_ms(self, risk_factor: float = 1.3) -> float:
        jitter_penalty = risk_factor * max(0.0, self.jitter_ms)
        loss_penalty = clamp(self.packet_loss, 0.0, 0.45) * 180.0
        return max(1.0, self.latency_ms + jitter_penalty + loss_penalty)

    def guaranteed_bandwidth_mbps(self, risk_factor: float = 1.3) -> float:
        reserved = self.bandwidth_mbps - (risk_factor * max(0.0, self.bandwidth_jitter_mbps))
        return max(10.0, reserved)

    def delivery_probability(self) -> float:
        return clamp(self.path_reliability * (1.0 - clamp(self.packet_loss, 0.0, 0.45)), 0.45, 0.999)

    def uncertainty_index(self) -> float:
        latency_component = min(1.0, max(0.0, self.jitter_ms) / max(5.0, self.latency_ms))
        bandwidth_component = min(1.0, max(0.0, self.bandwidth_jitter_mbps) / max(50.0, self.bandwidth_mbps))
        loss_component = min(1.0, clamp(self.packet_loss, 0.0, 0.45) / 0.05)
        reliability_component = 1.0 - clamp(self.path_reliability, 0.45, 0.999)
        return clamp(
            (latency_component * 0.35)
            + (bandwidth_component * 0.30)
            + (loss_component * 0.20)
            + (reliability_component * 0.15)
        )

    def synthesized_latency_history_ms(self) -> list[float]:
        """Fallback latency sequence until real probing telemetry is connected."""
        base = max(1.0, self.latency_ms)
        jitter = max(0.0, self.jitter_ms)
        loss_bump = clamp(self.packet_loss, 0.0, 0.45) * 120.0
        return [
            max(1.0, base - (jitter * 0.45)),
            max(1.0, base + (jitter * 0.15)),
            max(1.0, base - (jitter * 0.10) + (loss_bump * 0.20)),
            max(1.0, base + (jitter * 0.40)),
            max(1.0, base + (jitter * 0.72) + (loss_bump * 0.35)),
        ]

    def bandwidth_utilization_estimate(self) -> float:
        """Fallback utilization estimate until live link counters are connected."""
        jitter_ratio = max(0.0, self.bandwidth_jitter_mbps) / max(50.0, self.bandwidth_mbps)
        loss_pressure = clamp(self.packet_loss, 0.0, 0.45) / 0.08
        return clamp((jitter_ratio * 0.72) + (loss_pressure * 0.20) + 0.08)

    def to_dict(self) -> dict[str, float]:
        return {
            "latency_ms": round(self.latency_ms, 4),
            "jitter_ms": round(self.jitter_ms, 4),
            "bandwidth_mbps": round(self.bandwidth_mbps, 4),
            "bandwidth_jitter_mbps": round(self.bandwidth_jitter_mbps, 4),
            "packet_loss": round(self.packet_loss, 6),
            "path_reliability": round(self.path_reliability, 6),
        }
