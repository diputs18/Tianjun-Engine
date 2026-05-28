from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any

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


@dataclass(frozen=True, slots=True)
class TopologyEdge:
    source: str
    target: str
    propagation_delay_ms: float
    bandwidth_mbps: float

    def __post_init__(self) -> None:
        if not self.source or not self.target or self.source == self.target:
            raise ValueError("A topology edge requires two distinct endpoint names.")
        if self.propagation_delay_ms < 0.0 or self.bandwidth_mbps <= 0.0:
            raise ValueError("Topology edge delay must be non-negative and bandwidth must be positive.")

    def to_dict(self) -> dict[str, float | str]:
        return {
            "source": self.source,
            "target": self.target,
            "propagation_delay_ms": round(self.propagation_delay_ms, 4),
            "bandwidth_mbps": round(self.bandwidth_mbps, 4),
        }


@dataclass(slots=True)
class PhysicalTopology:
    topology_id: str
    topology_nodes: list[str]
    topology_edges: list[TopologyEdge]
    compute_attachments: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PhysicalTopology":
        nodes = [str(node) for node in payload.get("topology_nodes", [])]
        edges = [
            TopologyEdge(
                source=str(edge["source"]),
                target=str(edge["target"]),
                propagation_delay_ms=float(edge["propagation_delay_ms"]),
                bandwidth_mbps=float(edge["bandwidth_mbps"]),
            )
            for edge in payload.get("topology_edges", [])
        ]
        topology = cls(
            topology_id=str(payload.get("topology_id", "physical_topology")),
            topology_nodes=nodes,
            topology_edges=edges,
            compute_attachments={
                str(node_id): str(anchor)
                for node_id, anchor in payload.get("compute_attachments", {}).items()
            },
            provenance=dict(payload.get("provenance", {})),
        )
        topology.validate()
        return topology

    def validate(self) -> None:
        known = set(self.topology_nodes)
        if not self.topology_id or not known:
            raise ValueError("Physical topology requires an id and at least one topology node.")
        for edge in self.topology_edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"Topology edge {edge.source}->{edge.target} references an unknown endpoint.")
        for node_id, anchor in self.compute_attachments.items():
            if anchor not in known:
                raise ValueError(f"Compute node {node_id} is attached to unknown topology node {anchor}.")

    def connected_compute_neighbors(self, node_id: str, available_node_ids: set[str]) -> list[str]:
        distances = self.compute_neighbor_distances(node_id, available_node_ids)
        return sorted(distances, key=lambda other_id: (distances[other_id], other_id))

    def compute_neighbor_distances(self, node_id: str, available_node_ids: set[str]) -> dict[str, float]:
        anchor = self.compute_attachments.get(node_id)
        if anchor is None:
            return {}
        distances = self._distances_from(anchor)
        return {
            other_id: distances[other_anchor]
            for other_id, other_anchor in self.compute_attachments.items()
            if other_id != node_id and other_id in available_node_ids and other_anchor in distances
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "topology_id": self.topology_id,
            "topology_nodes": list(self.topology_nodes),
            "topology_edges": [edge.to_dict() for edge in self.topology_edges],
            "compute_attachments": dict(sorted(self.compute_attachments.items())),
            "provenance": dict(self.provenance),
        }

    def _distances_from(self, source: str) -> dict[str, float]:
        graph: dict[str, list[tuple[str, float]]] = {node: [] for node in self.topology_nodes}
        for edge in self.topology_edges:
            graph[edge.source].append((edge.target, edge.propagation_delay_ms))
            graph[edge.target].append((edge.source, edge.propagation_delay_ms))
        distances = {source: 0.0}
        frontier: list[tuple[float, str]] = [(0.0, source)]
        while frontier:
            distance, node = heapq.heappop(frontier)
            if distance != distances.get(node):
                continue
            for neighbor, edge_delay in graph.get(node, []):
                candidate = distance + edge_delay
                if candidate < distances.get(neighbor, float("inf")):
                    distances[neighbor] = candidate
                    heapq.heappush(frontier, (candidate, neighbor))
        return distances
