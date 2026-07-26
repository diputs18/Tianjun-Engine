from __future__ import annotations

import threading
import time

import pytest

from tianjun.application.batch_scheduling_service import BatchRequestError, BatchSchedulingService
from tianjun.application.control_plane import CentralControlPlane
from tianjun.domain import CarbonSiteProfile, Node, PowerProfile, ResourceVector, RunningTask, Task


def node(node_id: str, *, carbon: float, cpu: float = 16.0) -> Node:
    return Node(
        node_id=node_id,
        region=node_id,
        labels={"cloudsim"},
        capacity=ResourceVector(cpu=cpu, memory=64, gpu=2, storage=500),
        performance_factors={"batch_cpu": 1.0},
        power_profile=PowerProfile(
            profile_id=f"power-{node_id}",
            idle_power_w=100,
            max_power_w=300,
            gpu_idle_power_w=20,
            gpu_max_power_w=220,
        ),
        carbon_profile=CarbonSiteProfile(
            site_id=f"site-{node_id}",
            region=node_id,
            pue=1.2,
            carbon_intensity_g_per_kwh=carbon,
        ),
    )


def batch_payload(client_batch_id: str = "batch-client-1") -> dict:
    return {
        "client_batch_id": client_batch_id,
        "batch_name": "联合调度回归",
        "batch_preferences": {"intent_weights": {"carbon": 0.7, "fragmentation": 0.3}},
        "tasks": [
            {
                "task_id": f"task-{index}",
                "task_type": "batch_cpu",
                "demand": {"cpu": 4, "memory": 8, "gpu": 0, "storage": 10},
                "estimated_duration": 20,
                "priority": 6,
                "carbon_priority": 0.9,
            }
            for index in range(3)
        ],
    }


def test_batch_import_preview_commit_is_idempotent_and_capacity_safe() -> None:
    control = CentralControlPlane()
    control.register_node(node("dirty", carbon=780))
    control.register_node(node("green", carbon=120))

    imported = control.import_task_batch(batch_payload())
    replay = control.import_task_batch(batch_payload())
    assert replay["batch_id"] == imported["batch_id"]
    assert replay["idempotent_replay"] is True

    plan = control.preview_batch_schedule(imported["batch_id"], {"strategy": "B4-pareto-tchebycheff"})
    assert len(plan["task_node_assignments"]) == 3
    assigned_nodes = [item["node_id"] for item in plan["task_node_assignments"]]
    assert assigned_nodes[0] == "green"
    assert assigned_nodes.count("green") >= assigned_nodes.count("dirty")
    assert plan["predicted_carbon_g"] > 0
    assert plan["resource_snapshot_version"] == control.resource_snapshot_version

    with pytest.raises(BatchRequestError) as unconfirmed:
        control.commit_batch_schedule(imported["batch_id"], {
            "plan_id": plan["plan_id"],
            "resource_snapshot_version": plan["resource_snapshot_version"],
        })
    assert unconfirmed.value.status_code == 403

    committed = control.commit_batch_schedule(imported["batch_id"], {
        "plan_id": plan["plan_id"],
        "resource_snapshot_version": plan["resource_snapshot_version"],
        "confirmed_by_user_button": True,
    })
    assert len(committed["leases"]) == 3
    assert sum(item.used().cpu for item in control.nodes.values()) == 12
    assert all(item.used().fits_in(item.capacity) for item in control.nodes.values())

    for index, lease in enumerate(committed["leases"]):
        control.report_task_result(
            node_id=lease["node_id"],
            task_id=lease["task_id"],
            success=True,
            duration_seconds=10 + index,
            metadata={
                "queue_wait_seconds": index,
                "jct_seconds": 10 + index * 2,
                "cpu_utilization": 0.5 + index * 0.1,
                "memory_utilization": 0.4,
                "bandwidth_utilization": 0.2,
                "storage_utilization": 0.1,
            },
        )
    actual = control.get_task_batch_actual_metrics(imported["batch_id"])
    assert actual["status"] == "completed"
    assert actual["completed_count"] == 3
    assert actual["makespan_seconds"] == 14
    assert actual["average_cpu_utilization"] == pytest.approx(0.6)
    assert actual["prediction"]["decision_time_ms"] > 0


def test_snapshot_conflict_creates_no_partial_reservation() -> None:
    control = CentralControlPlane()
    control.register_node(node("green", carbon=120))
    imported = control.import_task_batch(batch_payload("snapshot-conflict"))
    plan = control.preview_batch_schedule(imported["batch_id"], {"strategy": "B1-batch-greedy"})

    control.record_heartbeat("green", health_score=0.99)
    with pytest.raises(BatchRequestError) as conflict:
        control.commit_batch_schedule(imported["batch_id"], {
            "plan_id": plan["plan_id"],
            "resource_snapshot_version": plan["resource_snapshot_version"],
            "confirmed_by_user_button": True,
        })
    assert conflict.value.status_code == 409
    assert control.leases == {}
    assert control.reservation_ledgers == {}


def test_slow_batch_planning_does_not_block_node_heartbeat(monkeypatch) -> None:
    control = CentralControlPlane()
    control.register_node(node("green", carbon=120))
    imported = control.import_task_batch(batch_payload("nonblocking-planning"))
    planning_started = threading.Event()
    release_planning = threading.Event()
    original = BatchSchedulingService._build_plan

    def slow_build(self, *args, **kwargs):
        planning_started.set()
        assert release_planning.wait(timeout=3)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BatchSchedulingService, "_build_plan", slow_build)
    error: list[BaseException] = []

    def preview() -> None:
        try:
            control.preview_batch_schedule(imported["batch_id"], {"strategy": "B1-batch-greedy"})
        except BaseException as exc:  # pragma: no cover - asserted below
            error.append(exc)

    worker = threading.Thread(target=preview)
    worker.start()
    assert planning_started.wait(timeout=2)
    started = time.perf_counter()
    control.record_heartbeat("green", health_score=0.99)
    heartbeat_elapsed = time.perf_counter() - started
    release_planning.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert error == []
    assert heartbeat_elapsed < 0.25


def test_carbon_time_shift_uses_lowest_forecast_tick_only_when_allowed() -> None:
    control = CentralControlPlane()
    green = node("trace", carbon=700)
    green.carbon_profile.carbon_intensity_trace = {0: 700, 30: 100, 60: 500}
    control.register_node(green)
    task = Task(
        task_id="deferrable",
        task_type="batch_cpu",
        demand=ResourceVector(cpu=2, memory=4, storage=5),
        estimated_duration=10,
        carbon_priority=1.0,
        allow_time_shift=True,
        deferrable_until_tick=60,
    )
    decision = control.preview_task(task)
    assert decision is not None
    assert decision["predicted_start_tick"] == 30
    assert decision["network_snapshot"]["carbon"]["scheduled_carbon_tick"] == 30


def test_hermes_parses_green_goal_and_latency_hard_limit() -> None:
    control = CentralControlPlane()
    requirement = control.parse_requirement("绿色优先但不违反30ms时延，碳预算8克，允许跨地域，不允许延后")
    assert requirement["priority"] == "green"
    assert requirement["latency_target_ms"] == 30
    assert requirement["carbon_budget_g"] == 8
    assert requirement["carbon_priority"] > 0
    assert requirement["allow_region_shift"] is True
    assert requirement["allow_time_shift"] is False


def test_hierarchical_batch_exposes_five_groups_and_security_guardrail() -> None:
    control = CentralControlPlane()
    control.register_node(node("dirty", carbon=780))
    control.register_node(node("green", carbon=120))
    imported = control.import_task_batch(batch_payload("hierarchical-five-groups"))

    plan = control.preview_batch_schedule(imported["batch_id"], {
        "strategy": "B6-hierarchical-batch",
    })

    assert plan["objective_hierarchy_version"] == "five-groups-v1"
    assert set(plan["group_objective_breakdown"]) == {
        "sla_quality",
        "network_coordination",
        "resource_efficiency",
        "economic_cost",
        "green_carbon",
    }
    assert sum(plan["group_weights"].values()) == pytest.approx(1.0)
    assert "security" not in plan["group_weights"]
    assert 0 <= plan["plan_utility"] <= 1
    decision = plan["task_node_assignments"][0]["decision"]
    assert decision["network_snapshot"]["adaptive_scoring_formula"].startswith("nested augmented")
    assert "security_risk_penalty" in decision["network_snapshot"]
    assert decision["network_snapshot"]["future_fit_sample_count"] == 2
    assert 0 <= decision["network_snapshot"]["future_fit_after"] <= 1


def test_single_and_dual_objective_masks_are_auditable() -> None:
    control = CentralControlPlane()
    control.register_node(node("dirty", carbon=780))
    control.register_node(node("green", carbon=120))
    imported = control.import_task_batch(batch_payload("objective-masks"))

    single = control.preview_batch_schedule(imported["batch_id"], {
        "strategy": "B4-pareto-tchebycheff",
        "active_metrics": ["carbon"],
    })
    dual = control.preview_batch_schedule(imported["batch_id"], {
        "strategy": "B6-hierarchical-batch",
        "active_groups": ["sla_quality", "green_carbon"],
    })

    assert single["active_objectives"] == ["carbon"]
    assert dual["active_objectives"] == ["sla_quality", "green_carbon"]
    first = single["task_node_assignments"][0]["decision"]
    assert first["weights"]["carbon"] == pytest.approx(1.0)
    assert sum(value for key, value in first["weights"].items() if key != "carbon") == pytest.approx(0.0)

    with pytest.raises(BatchRequestError) as invalid:
        control.preview_batch_schedule(imported["batch_id"], {
            "strategy": "B6-hierarchical-batch",
            "active_groups": ["unknown_group"],
        })
    assert invalid.value.status_code == 422


def test_named_green_profiles_preserve_public_strategy_and_weights() -> None:
    control = CentralControlPlane()
    control.register_node(node("dirty", carbon=780))
    control.register_node(node("green", carbon=120))
    imported = control.import_task_batch(batch_payload("named-green-profiles"))

    single = control.preview_batch_schedule(imported["batch_id"], {
        "strategy": "B6-green-single-v1",
    })
    dual = control.preview_batch_schedule(imported["batch_id"], {
        "strategy": "B6-green-sla-85-v1",
    })

    assert single["strategy"] == "B6-green-single-v1"
    assert single["active_objectives"] == ["green_carbon"]
    assert single["group_weights"] == {"green_carbon": pytest.approx(1.0)}
    assert dual["strategy"] == "B6-green-sla-85-v1"
    assert set(dual["active_objectives"]) == {"green_carbon", "sla_quality"}
    assert dual["group_weights"]["green_carbon"] == pytest.approx(0.85)
    assert dual["group_weights"]["sla_quality"] == pytest.approx(0.15)


def test_expected_cpu_utilization_drives_incremental_carbon_prediction() -> None:
    target = node("carbon-site", carbon=500)
    low = Task(
        task_id="low-util",
        task_type="batch_cpu",
        demand=ResourceVector(cpu=4, memory=8, storage=10),
        estimated_duration=20,
        expected_cpu_utilization=0.2,
    )
    high = Task(
        task_id="high-util",
        task_type="batch_cpu",
        demand=ResourceVector(cpu=4, memory=8, storage=10),
        estimated_duration=20,
        expected_cpu_utilization=0.8,
    )

    low_prediction = target.predict_operational_carbon(low, 20, 0)
    high_prediction = target.predict_operational_carbon(high, 20, 0)

    assert high_prediction["power_w"] > low_prediction["power_w"]
    assert high_prediction["operational_carbon_g"] > low_prediction["operational_carbon_g"]
    assert high.to_dict()["expected_cpu_utilization"] == pytest.approx(0.8)


def test_future_fit_counts_feasible_task_node_pairs() -> None:
    control = CentralControlPlane()
    blocked = node("blocked", carbon=500)
    available = node("available", carbon=500)
    blocked.running_tasks["background"] = RunningTask(
        task_id="background",
        node_id=blocked.node_id,
        allocation=ResourceVector(cpu=14, memory=4, storage=1),
        start_tick=0,
        predicted_duration=100,
        actual_duration=100,
        finish_tick=100,
        success_probability=1.0,
    )
    future = Task(
        task_id="future",
        task_type="batch_cpu",
        demand=ResourceVector(cpu=4, memory=8, storage=10),
        estimated_duration=20,
    )

    score = control.batch_scheduling_service._future_fit([blocked, available], [future])

    assert score == pytest.approx(0.5)
