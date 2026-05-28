from __future__ import annotations

from tianjun.domain import NetworkPathProfile, Node, PhysicalTopology, PolicyState, ResourceVector, Task
from tianjun.ml.runtime import ModelPrediction
from tianjun.scheduling.engine import ClosedLoopAdaptiveScheduler


def topology() -> PhysicalTopology:
    return PhysicalTopology.from_dict({
        "topology_id": "dci",
        "topology_nodes": ["dc1", "core", "dc2"],
        "topology_edges": [
            {"source": "dc1", "target": "core", "propagation_delay_ms": 8.0, "bandwidth_mbps": 10000.0},
            {"source": "core", "target": "dc2", "propagation_delay_ms": 8.3, "bandwidth_mbps": 10000.0},
        ],
        "compute_attachments": {"sh-a": "dc1", "sh-b": "dc1", "sz-a": "dc2"},
    })


def node(node_id: str, region: str, location: str | None = None, service_region: str | None = None) -> Node:
    return Node(
        node_id=node_id,
        region=region,
        location=location,
        service_region=service_region,
        labels={"cloudsim"},
        capacity=ResourceVector(cpu=8, memory=32, storage=100),
        network_paths={
            "shanghai": NetworkPathProfile(latency_ms=1.0 if region == "shanghai" else 16.3),
        },
    )


def test_topology_exposes_distance_weighted_compute_neighbors() -> None:
    distances = topology().compute_neighbor_distances("sh-a", {"sh-a", "sh-b", "sz-a"})
    assert distances == {"sh-b": 0.0, "sz-a": 16.3}
    assert topology().connected_compute_neighbors("sh-a", {"sh-a", "sh-b", "sz-a"}) == ["sh-b", "sz-a"]


def test_scheduler_passes_physical_neighbors_to_model_runtime() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.neighbors = []

        def predict(self, **kwargs: object) -> ModelPrediction:
            self.neighbors = list(kwargs["neighbor_observations"])
            return ModelPrediction(enabled=False)

    runtime = Runtime()
    scheduler = ClosedLoopAdaptiveScheduler(PolicyState(), model_runtime=runtime)  # type: ignore[arg-type]
    scheduler.set_physical_topology(topology())
    nodes = [
        node("sh-a", "dc1", "hangzhou"),
        node("sh-b", "dc1", "beijing"),
        node("sz-a", "dc2", "guangzhou"),
    ]
    task = Task(
        task_id="probe",
        task_type="inference",
        demand=ResourceVector(cpu=1, memory=1, storage=1),
        estimated_duration=1,
        source_region="dc1",
    )
    decision = scheduler.select_node(task, [nodes[0]], current_tick=0, topology_nodes=nodes)
    assert decision is not None
    assert [(neighbor.node_id, distance) for neighbor, _, distance in runtime.neighbors] == [
        ("sh-b", 0.0),
        ("sz-a", 16.3),
    ]
    physical = decision.network_snapshot["physical_topology"]
    assert physical["topology_id"] == "dci"
    assert physical["selected_node_service_region"] == "east"
    assert physical["selected_node_location"] == "hangzhou"
    assert physical["source_location"] == "dc1"
    assert physical["compute_neighbor_locations"] == {"sh-b": "beijing", "sz-a": "guangzhou"}


def test_service_region_filters_nodes_without_replacing_physical_attachment() -> None:
    east_dc1 = node("hangzhou-a", "dc1", "hangzhou")
    west_dc2 = node("chengdu-a", "dc2", "chengdu")
    west_dc2_b = node("chongqing-a", "dc2", "chongqing")
    south_dc3 = node("guangzhou-a", "dc3", "guangzhou")
    task = Task(
        task_id="west-only",
        task_type="inference",
        demand=ResourceVector(cpu=1, memory=1, storage=1),
        estimated_duration=1,
        allowed_regions={"west"},
    )
    assert east_dc1.service_region == "east"
    assert west_dc2.service_region == "west"
    assert west_dc2_b.service_region == "west"
    assert west_dc2.can_host_now(task)
    assert west_dc2_b.can_host_now(task)
    assert not east_dc1.can_host_now(task)
    assert not south_dc3.can_host_now(task)
