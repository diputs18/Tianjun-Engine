from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane
    from ..domain import Node

from ..domain import NetworkPathProfile


@dataclass(slots=True)
class NodeRegistry:
    """Boundary for node inventory, heartbeat, health, and topology state."""

    control_plane: CentralControlPlane

    @property
    def node_count(self) -> int:
        return len(self.control_plane.nodes)

    def register_node(self, node: Node) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            current = control.nodes.get(node.node_id)
            if current is not None:
                node.running_tasks = current.running_tasks
                node.reliability_score = current.reliability_score
                node.health_score = current.health_score
            node.online = True
            node.telemetry_tick = control.current_tick()
            control.nodes[node.node_id] = node
            control.last_heartbeat_at[node.node_id] = time.monotonic()
            control._persist_node(node)
            return node.to_dict()

    def record_heartbeat(
        self,
        node_id: str,
        *,
        health_score: float | None = None,
        online: bool | None = None,
        reliability_score: float | None = None,
        cost_per_tick: float | None = None,
        region: str | None = None,
        location: str | None = None,
        service_region: str | None = None,
        labels: set[str] | None = None,
        performance_factors: dict[str, float] | None = None,
        network_paths: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            node = control.nodes[node_id]
            node.telemetry_tick = control.current_tick()
            node.online = True if online is None else online
            if health_score is not None:
                node.health_score = health_score
            if reliability_score is not None:
                node.reliability_score = reliability_score
            if cost_per_tick is not None:
                node.cost_per_tick = cost_per_tick
            if region is not None:
                node.region = region
            if location is not None:
                node.location = location
            if service_region is not None:
                node.service_region = service_region
            if labels is not None:
                node.labels = set(labels)
            if performance_factors is not None:
                node.performance_factors.update(performance_factors)
            if network_paths is not None:
                for source_region, profile_updates in network_paths.items():
                    profile = node.network_paths.get(str(source_region))
                    if profile is None:
                        profile = NetworkPathProfile()
                        node.network_paths[str(source_region)] = profile
                    for key, value in profile_updates.items():
                        if hasattr(profile, key):
                            setattr(profile, key, float(value))
            control.last_heartbeat_at[node_id] = time.monotonic()
            heartbeat_payload = {
                "node_id": node_id,
                "tick": node.telemetry_tick,
                "running_tasks": sorted(node.running_tasks.keys()),
                "pending_tasks": len(control.pending_queue),
                "online": node.online,
                "network_paths": {
                    region: profile.to_dict()
                    for region, profile in sorted(node.network_paths.items(), key=lambda item: item[0])
                },
            }
            control._persist_node(node)
            if node.online is False:
                control._recover_leases_for_stale_nodes({node_id})
            if control.state_store is not None:
                control.state_store.record_heartbeat(node_id, heartbeat_payload)
            return heartbeat_payload
