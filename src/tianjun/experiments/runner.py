from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict, dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Any, Iterable

from ..application.control_plane import CentralControlPlane
from ..domain import CarbonSiteProfile, Node, PowerProfile, ResourceVector, RunningTask


@dataclass(slots=True)
class ExperimentResult:
    schema_version: str
    seed: int
    node_count: int
    batch_task_count: int
    load_rate: float
    workload: str
    fragmentation_mode: str
    strategy: str
    assigned_tasks: int
    unassigned_tasks: int
    acceptance_rate: float
    predicted_makespan: int
    predicted_cost: float
    predicted_energy_kwh: float
    predicted_carbon_g: float
    predicted_carbon_g_per_assignment: float
    predicted_sla_violations: int
    future_fit_before: float
    future_fit_after: float
    future_fit_loss: float
    future_fit_loss_per_assignment: float
    decision_time_ms: float
    wall_time_ms: float
    plan_utility: float = 0.0
    group_objective_breakdown: dict[str, float] | None = None
    intent_weights: dict[str, float] | None = None
    group_weights: dict[str, float] | None = None
    security_risk_penalty: float = 0.0
    experiment_label: str = ""
    objective_scope: str = "flat_full"
    active_objectives: list[str] | None = None
    objective_hierarchy_version: str = "flat-ten-v1"
    carbon_scope: str = "operational_only"
    normalization_bounds_version: str = "engineering-v1"
    baseline_carbon_reduction: float | None = None
    baseline_carbon_per_assignment_reduction: float | None = None
    baseline_acceptance_delta: float | None = None


def run_matrix(config: dict[str, Any], *, quick: bool = False) -> list[ExperimentResult]:
    node_counts = _selection(config, "node_counts", quick)
    task_counts = _selection(config, "batch_task_counts", quick)
    load_rates = _selection(config, "load_rates", quick)
    workloads = _selection(config, "workloads", quick)
    fragmentation_modes = _selection(config, "fragmentation_modes", quick) or ["uniform"]
    seeds = _selection(config, "seeds", quick)
    strategies = list(config.get("online_strategies") or [])
    if not quick:
        strategies.extend(config.get("offline_strategies") or [])
    cases = _experiment_cases(strategies, config, quick=quick)

    results: list[ExperimentResult] = []
    for node_count, task_count, load_rate, workload, fragmentation_mode, seed in product(
        node_counts, task_counts, load_rates, workloads, fragmentation_modes, seeds
    ):
        for case in cases:
            strategy = case["strategy"]
            if strategy == "B2-milp-oracle" and (task_count > 20 or node_count > 20):
                continue
            control = CentralControlPlane()
            for node in synthetic_nodes(
                int(node_count),
                float(load_rate),
                int(seed),
                fragmentation_mode=str(fragmentation_mode),
            ):
                control.register_node(node)
            payload = synthetic_batch(
                int(task_count),
                str(workload),
                int(seed),
                case["label"],
                intent_weights=case.get("intent_weights"),
            )
            imported = control.import_task_batch(payload)
            started = time.perf_counter()
            plan = control.preview_batch_schedule(imported["batch_id"], {
                "strategy": strategy,
                "experiment_mode": strategy in {"B2-milp-oracle", "B5-nsga2"},
                "active_metrics": case.get("active_metrics"),
                "active_groups": case.get("active_groups"),
                "group_weights": case.get("group_weights"),
            })
            wall_time_ms = (time.perf_counter() - started) * 1000.0
            assigned = len(plan["task_node_assignments"])
            result = ExperimentResult(
                schema_version=str(config.get("schema_version", "1.0")),
                seed=int(seed),
                node_count=int(node_count),
                batch_task_count=int(task_count),
                load_rate=float(load_rate),
                workload=str(workload),
                fragmentation_mode=str(fragmentation_mode),
                strategy=strategy,
                assigned_tasks=assigned,
                unassigned_tasks=len(plan["unassigned_tasks"]),
                acceptance_rate=assigned / max(1, int(task_count)),
                predicted_makespan=int(plan["predicted_makespan"]),
                predicted_cost=float(plan["predicted_cost"]),
                predicted_energy_kwh=float(plan["predicted_energy_kwh"]),
                predicted_carbon_g=float(plan["predicted_carbon_g"]),
                predicted_carbon_g_per_assignment=(
                    float(plan["predicted_carbon_g"]) / max(1, assigned)
                ),
                predicted_sla_violations=int(plan["predicted_sla_violations"]),
                future_fit_before=float(plan["future_fit_before"]),
                future_fit_after=float(plan["future_fit_after"]),
                future_fit_loss=max(
                    0.0,
                    float(plan["future_fit_before"]) - float(plan["future_fit_after"]),
                ),
                future_fit_loss_per_assignment=(
                    max(0.0, float(plan["future_fit_before"]) - float(plan["future_fit_after"]))
                    / max(1, assigned)
                ),
                decision_time_ms=float(plan["decision_time_ms"]),
                wall_time_ms=wall_time_ms,
                plan_utility=float(plan.get("plan_utility", 0.0)),
                group_objective_breakdown={
                    str(key): float(value)
                    for key, value in dict(plan.get("group_objective_breakdown") or {}).items()
                },
                intent_weights={
                    str(key): float(value)
                    for key, value in dict(case.get("intent_weights") or {}).items()
                },
                group_weights={
                    str(key): float(value)
                    for key, value in dict(case.get("group_weights") or {}).items()
                },
                security_risk_penalty=float(plan.get("security_risk_penalty", 0.0)),
                experiment_label=case["label"],
                objective_scope=case["scope"],
                active_objectives=list(plan.get("active_objectives") or []),
                objective_hierarchy_version=str(plan.get("objective_hierarchy_version", "flat-ten-v1")),
                carbon_scope=str(config.get("carbon_scope", "operational_only")),
                normalization_bounds_version=str(config.get("normalization_bounds_version", "engineering-v1")),
            )
            results.append(result)
    _attach_baseline_deltas(results)
    return results


def _experiment_cases(
    strategies: list[str],
    config: dict[str, Any],
    *,
    quick: bool,
) -> list[dict[str, Any]]:
    cases = [
        {
            "label": strategy,
            "strategy": strategy,
            "scope": "hierarchical_full" if strategy == "B6-hierarchical-batch" else "flat_full",
        }
        for strategy in strategies
    ]
    profiles = dict(config.get("objective_experiments") or {})
    single_atomic = list(profiles.get("single_atomic") or [])
    dual_atomic_config = profiles.get("dual_atomic") or []
    single_groups = list(profiles.get("single_groups") or [])
    dual_groups_config = profiles.get("dual_groups") or []
    dual_atomic = (
        list(combinations(single_atomic, 2))
        if dual_atomic_config == "all"
        else list(dual_atomic_config)
    )
    dual_groups = (
        list(combinations(single_groups, 2))
        if dual_groups_config == "all"
        else list(dual_groups_config)
    )
    if quick:
        single_atomic = single_atomic[:1]
        dual_atomic = dual_atomic[:1]
        single_groups = single_groups[:1]
        dual_groups = dual_groups[:1]
    cases.extend({
        "label": f"S1-{metric}",
        "strategy": "B4-pareto-tchebycheff",
        "scope": "single_atomic",
        "active_metrics": [metric],
    } for metric in single_atomic)
    cases.extend({
        "label": f"S2-{'+'.join(pair)}",
        "strategy": "B4-pareto-tchebycheff",
        "scope": "dual_atomic",
        "active_metrics": list(pair),
    } for pair in dual_atomic)
    cases.extend({
        "label": f"G1-{group}",
        "strategy": "B6-hierarchical-batch",
        "scope": "single_group",
        "active_groups": [group],
    } for group in single_groups)
    cases.extend({
        "label": f"G2-{'+'.join(pair)}",
        "strategy": "B6-hierarchical-batch",
        "scope": "dual_group",
        "active_groups": list(pair),
    } for pair in dual_groups)
    cases.extend({
        "label": str(profile["label"]),
        "strategy": str(profile.get("strategy") or "B6-hierarchical-batch"),
        "scope": "weight_calibration",
        "active_groups": list(profile.get("active_groups") or []) or None,
        "intent_weights": {
            str(key): float(value)
            for key, value in dict(profile.get("intent_weights") or {}).items()
        },
        "group_weights": {
            str(key): float(value)
            for key, value in dict(profile.get("group_weights") or {}).items()
        },
    } for profile in list(config.get("weight_profiles") or []))
    return cases


def synthetic_nodes(
    count: int,
    load_rate: float,
    seed: int,
    *,
    fragmentation_mode: str = "uniform",
) -> Iterable[Node]:
    rng = random.Random(seed)
    regions = ("east", "north", "west")
    carbon_levels = (180.0, 430.0, 690.0)
    for index in range(count):
        region_index = index % len(regions)
        gpu = 8.0 if index % 4 == 0 else 0.0
        capacity = ResourceVector(
            cpu=32,
            memory=128,
            gpu=gpu,
            storage=2000,
            mips=96_000,
            gpu_memory=gpu * 24,
            storage_iops=120_000,
            bandwidth=25_000,
        )
        node = Node(
            node_id=f"node-{index:03d}",
            region=regions[region_index],
            labels={"cloudsim", "cpu", *( {"gpu"} if gpu else set() )},
            capacity=capacity,
            cost_per_tick=0.7 + region_index * 0.25 + rng.random() * 0.1,
            base_reliability=0.96 + rng.random() * 0.035,
            performance_factors={"batch_cpu": 0.9 + rng.random() * 0.4, "training": 1.2 + rng.random()},
            power_profile=PowerProfile(
                profile_id=f"power-{index % 4}",
                idle_power_w=90 + index % 4 * 15,
                max_power_w=260 + index % 4 * 35,
                gpu_idle_power_w=25,
                gpu_max_power_w=320,
            ),
            carbon_profile=CarbonSiteProfile(
                site_id=f"site-{region_index}",
                region=regions[region_index],
                pue=1.15 + region_index * 0.12,
                carbon_intensity_g_per_kwh=carbon_levels[region_index],
                carbon_intensity_trace={0: carbon_levels[region_index], 60: carbon_levels[region_index] * 0.72},
                source_version="synthetic-experiment-v1",
            ),
        )
        if load_rate > 0:
            allocation = _background_allocation(
                capacity,
                load_rate,
                index,
                fragmentation_mode=fragmentation_mode,
            )
            node.running_tasks[f"background-{index}"] = RunningTask(
                task_id=f"background-{index}",
                node_id=node.node_id,
                allocation=allocation,
                start_tick=0,
                predicted_duration=10_000,
                actual_duration=0,
                finish_tick=10_000,
                success_probability=1.0,
            )
        yield node


def synthetic_batch(
    count: int,
    workload: str,
    seed: int,
    strategy: str,
    *,
    intent_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    tasks = []
    workload_types = ["cpu", "gpu", "memory", "data"] if workload == "mixed" else [workload]
    for index in range(count):
        kind = workload_types[index % len(workload_types)]
        demand = {
            "cpu": rng.choice([1, 2, 4, 8]),
            "memory": rng.choice([2, 4, 8, 16]),
            "gpu": 1 if kind == "gpu" else 0,
            "storage": rng.choice([5, 10, 20, 40]),
            "mips": 0,
            "gpu_memory": 8 if kind == "gpu" else 0,
            "storage_iops": rng.choice([500, 1_000, 2_500, 5_000]),
            "bandwidth": rng.choice([100, 250, 500, 1_000]),
        }
        demand["mips"] = demand["cpu"] * rng.choice([1_000, 1_500, 2_000])
        if kind == "memory":
            demand["memory"] *= 3
        tasks.append({
            "task_id": f"task-{index:04d}",
            "task_type": "training" if kind == "gpu" else "batch_cpu",
            "demand": demand,
            "estimated_duration": rng.randint(10, 90),
            "priority": rng.randint(3, 9),
            "input_size_gb": rng.uniform(4, 25) if kind == "data" else rng.uniform(0.1, 2),
            "carbon_priority": 0.7 if index % 3 == 0 else 0.2,
            "allow_region_shift": True,
            "require_encrypted_transport": True,
        })
    return {
        "client_batch_id": f"exp-{seed}-{workload}-{count}-{strategy}",
        "batch_name": f"{workload}-{count}-{strategy}",
        "batch_preferences": {
            "intent_weights": dict(intent_weights or {"carbon": 0.2, "fragmentation": 0.15})
        },
        "tasks": tasks,
    }


def _background_allocation(
    capacity: ResourceVector,
    load_rate: float,
    node_index: int,
    *,
    fragmentation_mode: str,
) -> ResourceVector:
    if fragmentation_mode == "uniform":
        fractions = {key: load_rate for key in capacity.to_dict()}
    elif fragmentation_mode == "heterogeneous":
        # Four complementary background shapes create CPU-, memory-, GPU/IO-
        # and network-heavy holes while keeping the fleet-wide pressure close
        # to the requested load rate.
        delta = min(0.16, max(0.08, (1.0 - load_rate) * 1.5))
        low = max(0.0, load_rate - delta)
        high = min(0.985, load_rate + delta)
        fractions_by_shape = (
            {"cpu": high, "mips": high, "memory": low, "gpu": load_rate, "gpu_memory": load_rate, "storage": low, "storage_iops": low, "bandwidth": load_rate},
            {"cpu": low, "mips": low, "memory": high, "gpu": load_rate, "gpu_memory": load_rate, "storage": load_rate, "storage_iops": load_rate, "bandwidth": low},
            {"cpu": load_rate, "mips": load_rate, "memory": low, "gpu": low, "gpu_memory": low, "storage": high, "storage_iops": high, "bandwidth": load_rate},
            {"cpu": low, "mips": low, "memory": load_rate, "gpu": high, "gpu_memory": high, "storage": low, "storage_iops": low, "bandwidth": high},
        )
        fractions = fractions_by_shape[node_index % len(fractions_by_shape)]
    else:
        raise ValueError(f"unknown fragmentation mode: {fragmentation_mode}")
    values = capacity.to_dict()
    return ResourceVector(**{
        key: float(value) * float(fractions[key])
        for key, value in values.items()
    })


def _selection(config: dict[str, Any], key: str, quick: bool) -> list[Any]:
    values = list(config.get(key) or [])
    return values[:1] if quick else values


def _attach_baseline_deltas(results: list[ExperimentResult]) -> None:
    baselines = {
        (item.seed, item.node_count, item.batch_task_count, item.load_rate, item.workload, item.fragmentation_mode): item
        for item in results
        if item.strategy == "B0-current"
    }
    for item in results:
        baseline = baselines.get((item.seed, item.node_count, item.batch_task_count, item.load_rate, item.workload, item.fragmentation_mode))
        if baseline is None:
            continue
        item.baseline_acceptance_delta = item.acceptance_rate - baseline.acceptance_rate
        if baseline.predicted_carbon_g > 0:
            item.baseline_carbon_reduction = (
                baseline.predicted_carbon_g - item.predicted_carbon_g
            ) / baseline.predicted_carbon_g
        if baseline.predicted_carbon_g_per_assignment > 0:
            item.baseline_carbon_per_assignment_reduction = (
                baseline.predicted_carbon_g_per_assignment
                - item.predicted_carbon_g_per_assignment
            ) / baseline.predicted_carbon_g_per_assignment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible Tianjun batch scheduling experiments.")
    parser.add_argument("--config", default="configs/batch_experiments.json")
    parser.add_argument("--output", default="exp_out/results.json")
    parser.add_argument("--quick", action="store_true", help="Run only the first online matrix cell.")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    results = run_matrix(config, quick=args.quick)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(results)} experiment rows to {output}")


if __name__ == "__main__":
    main()
