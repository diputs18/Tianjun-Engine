from __future__ import annotations

import pytest

from tianjun.domain import ExecutionRecord, Node, PolicyState, ResourceVector
from tianjun.policy.optimizer import PolicyOptimizer


def record(
    index: int,
    *,
    success: bool = True,
    sla_met: bool = True,
    within_budget: bool | None = True,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id=f"task-{index}",
        task_type="batch_cpu",
        node_id="node-1",
        start_tick=index,
        end_tick=index + 10,
        predicted_duration=10,
        actual_duration=10,
        success=success,
        cost=1.0,
        sla_met=sla_met,
        within_budget=within_budget,
        retry_count=0,
    )


def node(node_id: str = "node-1") -> Node:
    return Node(
        node_id=node_id,
        region="east",
        capacity=ResourceVector(cpu=16, memory=64, gpu=4, storage=500),
    )


def test_dynamic_optimizer_waits_for_minimum_history() -> None:
    state = PolicyState()
    before = state.current_weights()

    reasons = PolicyOptimizer(min_history=4).update_policy(
        state,
        [record(1, sla_met=False), record(2, sla_met=False)],
        [node()],
        tick=2,
    )

    assert reasons == []
    assert state.current_weights() == before
    assert state.adjustment_history == []


def test_budget_feedback_updates_atomic_and_group_weights_together() -> None:
    state = PolicyState()
    before_atomic = state.current_weights()
    before_groups = state.current_group_weights()

    reasons = PolicyOptimizer().update_policy(
        state,
        [record(index, within_budget=False) for index in range(6)],
        [node()],
        tick=6,
    )

    assert reasons
    assert state.current_weights()["cost"] > before_atomic["cost"]
    assert state.current_group_weights()["economic_cost"] > before_groups["economic_cost"]
    assert sum(state.current_weights().values()) == pytest.approx(1.0)
    assert sum(state.current_group_weights().values()) == pytest.approx(1.0)
    adjustment = state.adjustment_history[-1].to_dict()
    assert adjustment["weights"]["cost"] == pytest.approx(
        round(state.current_weights()["cost"], 4)
    )
    assert adjustment["group_weights"]["economic_cost"] == pytest.approx(
        round(state.current_group_weights()["economic_cost"], 4)
    )


def test_network_failure_feedback_reaches_both_hierarchy_layers() -> None:
    state = PolicyState()
    before_atomic = state.current_weights()
    before_groups = state.current_group_weights()

    PolicyOptimizer().update_policy(
        state,
        [record(index, success=False, sla_met=False) for index in range(8)],
        [node()],
        tick=8,
        context={
            "network_instability": 0.9,
            "network_pressure": 0.8,
            "locality_miss_rate": 0.7,
        },
    )

    after_atomic = state.current_weights()
    after_groups = state.current_group_weights()
    assert after_atomic["reliability"] > before_atomic["reliability"]
    assert after_atomic["network"] > before_atomic["network"]
    assert after_groups["sla_quality"] > before_groups["sla_quality"]
    assert after_groups["network_coordination"] > before_groups["network_coordination"]
    assert abs(after_atomic["security"] - before_atomic["security"]) < 0.01


def test_carbon_budget_feedback_updates_green_group_and_is_bounded() -> None:
    state = PolicyState()
    before_atomic = state.current_weights()
    before_groups = state.current_group_weights()
    optimizer = PolicyOptimizer(max_weight_delta=0.03)

    optimizer.update_policy(
        state,
        [record(index) for index in range(12)],
        [node()],
        tick=12,
        context={"carbon_budget_violation_rate": 1.0},
    )

    after_atomic = state.current_weights()
    after_groups = state.current_group_weights()
    assert after_atomic["carbon"] > before_atomic["carbon"]
    assert after_groups["green_carbon"] > before_groups["green_carbon"]
    assert max(
        abs(after_atomic[key] - before_atomic[key]) for key in before_atomic
    ) < 0.035
    assert max(
        abs(after_groups[key] - before_groups[key]) for key in before_groups
    ) < 0.035
