from __future__ import annotations

from dataclasses import asdict

import pytest

from tianjun.application.batch_scheduling_service import BatchRequestError
from tianjun.application.control_plane import CentralControlPlane
from tianjun.domain import Node, ResourceVector
from tianjun.experiments import (
    AssignmentCandidate,
    critic_weights,
    entropy_weights,
    milp_oracle,
    nsga2_assignments,
)
from tianjun.experiments.runner import run_matrix
from tianjun.experiments.report import summarize


def test_objective_weight_methods_are_normalized_and_deterministic() -> None:
    rows = [
        [0.1, 0.8, 0.4],
        [0.4, 0.3, 0.7],
        [0.9, 0.2, 0.5],
        [0.6, 0.6, 0.1],
    ]
    critic = critic_weights(rows)
    entropy = entropy_weights(rows)

    assert critic == critic_weights(rows)
    assert entropy == entropy_weights(rows)
    assert sum(critic) == pytest.approx(1.0)
    assert sum(entropy) == pytest.approx(1.0)
    assert all(weight >= 0 for weight in critic + entropy)


def test_milp_oracle_maximizes_admission_without_resource_oversell() -> None:
    candidates = [
        AssignmentCandidate("task-a", "node-a", 0.9, {"cpu": 4}),
        AssignmentCandidate("task-a", "node-b", 0.5, {"cpu": 4}),
        AssignmentCandidate("task-b", "node-a", 0.8, {"cpu": 4}),
        AssignmentCandidate("task-b", "node-b", 0.7, {"cpu": 4}),
    ]
    capacities = {
        "node-a": {"cpu": 4, "memory": 8, "gpu": 0, "storage": 20},
        "node-b": {"cpu": 4, "memory": 8, "gpu": 0, "storage": 20},
    }

    solution = milp_oracle(candidates, capacities)

    assert solution.status == "optimal"
    assert solution.assigned_count == 2
    assert {(item.task_id, item.node_id) for item in solution.selected} == {
        ("task-a", "node-a"),
        ("task-b", "node-b"),
    }


def test_nsga2_baseline_is_reproducible() -> None:
    candidates = [
        AssignmentCandidate(
            task_id=f"task-{task}",
            node_id=f"node-{node}",
            utility=1.0 - node * 0.1,
            demand={"cpu": 1},
            objectives={"carbon": 1.0 - node * 0.2, "completion": 0.8 + node * 0.1},
        )
        for task in range(3)
        for node in range(2)
    ]
    capacities = {
        "node-0": {"cpu": 2, "memory": 8, "gpu": 0, "storage": 20},
        "node-1": {"cpu": 2, "memory": 8, "gpu": 0, "storage": 20},
    }

    first = nsga2_assignments(candidates, capacities, population_size=16, generations=8)
    second = nsga2_assignments(candidates, capacities, population_size=16, generations=8)

    first_allocations = [tuple(sorted((item.task_id, item.node_id) for item in solution.selected)) for solution in first]
    second_allocations = [tuple(sorted((item.task_id, item.node_id) for item in solution.selected)) for solution in second]
    assert first_allocations == second_allocations
    assert max(solution.assigned_count for solution in first) == 3


def test_experiment_solvers_require_explicit_experiment_mode() -> None:
    control = CentralControlPlane()
    control.register_node(Node(
        node_id="node-a",
        region="east",
        labels={"cloudsim"},
        capacity=ResourceVector(cpu=8, memory=16, gpu=0, storage=100),
    ))
    imported = control.import_task_batch({
        "client_batch_id": "experiment-mode-gate",
        "tasks": [
            {
                "task_id": "oracle-task",
                "task_type": "batch_cpu",
                "demand": {"cpu": 2, "memory": 2, "gpu": 0, "storage": 5},
                "estimated_duration": 10,
                "priority": 5,
            }
        ],
    })

    with pytest.raises(BatchRequestError) as forbidden:
        control.preview_batch_schedule(imported["batch_id"], {"strategy": "B2-milp-oracle"})
    assert forbidden.value.status_code == 403

    plan = control.preview_batch_schedule(imported["batch_id"], {
        "strategy": "B2-milp-oracle",
        "experiment_mode": True,
    })
    assert len(plan["task_node_assignments"]) == 1
    assert plan["task_node_assignments"][0]["decision"]["network_snapshot"]["experiment_solver_status"] == "optimal"


def test_experiment_runner_emits_fixed_baseline_comparison_schema() -> None:
    results = run_matrix({
        "schema_version": "1.0",
        "node_counts": [2],
        "batch_task_counts": [2],
        "load_rates": [0.3],
        "workloads": ["cpu"],
        "seeds": [7],
        "online_strategies": ["B0-current", "B1-batch-greedy"],
        "offline_strategies": [],
        "carbon_scope": "operational_only",
        "normalization_bounds_version": "engineering-v1",
    })

    assert [item.strategy for item in results] == ["B0-current", "B1-batch-greedy"]
    assert all(item.carbon_scope == "operational_only" for item in results)
    assert results[0].baseline_carbon_reduction == pytest.approx(0.0)
    assert results[1].baseline_acceptance_delta is not None


def test_experiment_runner_covers_single_dual_and_hierarchical_objectives() -> None:
    results = run_matrix({
        "schema_version": "2.0",
        "node_counts": [2],
        "batch_task_counts": [2],
        "load_rates": [0.3],
        "workloads": ["cpu"],
        "seeds": [7],
        "online_strategies": ["B0-current", "B6-hierarchical-batch"],
        "objective_experiments": {
            "single_atomic": ["carbon"],
            "dual_atomic": [["completion", "carbon"]],
            "single_groups": ["green_carbon"],
            "dual_groups": [["sla_quality", "green_carbon"]],
        },
    })

    assert {item.objective_scope for item in results} == {
        "flat_full",
        "hierarchical_full",
        "single_atomic",
        "dual_atomic",
        "single_group",
        "dual_group",
    }
    assert all(item.group_objective_breakdown is not None for item in results)
    assert all(0 <= item.plan_utility <= 1 for item in results)
    summary = summarize([asdict(item) for item in results])
    assert len(summary) == len(results)
    assert all(item["sample_count"] == 1 for item in summary)
