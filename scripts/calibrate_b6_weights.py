from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any


def case_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row["seed"]),
        int(row["node_count"]),
        int(row["batch_task_count"]),
        float(row["load_rate"]),
        str(row["workload"]),
        str(row.get("fragmentation_mode", "uniform")),
    )


def safe_relative(candidate: float, baseline: float) -> float:
    return (candidate - baseline) / baseline if baseline else 0.0


def profile_samples(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    baselines = {
        case_key(row): row
        for row in rows
        if row.get("experiment_label") == "B0-current"
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("objective_scope") != "weight_calibration":
            continue
        baseline = baselines.get(case_key(row))
        if baseline is None:
            continue
        candidate_carbon_per_task = float(
            row.get("predicted_carbon_g_per_assignment")
            or float(row["predicted_carbon_g"]) / max(1, int(row["assigned_tasks"]))
        )
        baseline_carbon_per_task = float(
            baseline.get("predicted_carbon_g_per_assignment")
            or float(baseline["predicted_carbon_g"]) / max(1, int(baseline["assigned_tasks"]))
        )
        grouped[str(row["experiment_label"])].append({
            "seed": int(row["seed"]),
            "carbon_reduction": -safe_relative(
                candidate_carbon_per_task, baseline_carbon_per_task
            ),
            "acceptance_delta": float(row["acceptance_rate"]) - float(baseline["acceptance_rate"]),
            "future_fit_delta": float(row["future_fit_after"]) - float(baseline["future_fit_after"]),
            "makespan_change": safe_relative(
                float(row["predicted_makespan"]), float(baseline["predicted_makespan"])
            ),
            "decision_overhead": safe_relative(
                float(row["decision_time_ms"]), float(baseline["decision_time_ms"])
            ),
            "sla_delta": float(row["predicted_sla_violations"])
            - float(baseline["predicted_sla_violations"]),
            "group_weights": dict(row.get("group_weights") or {}),
        })
    return grouped


def aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {}
    result = {
        key: fmean(float(item[key]) for item in samples)
        for key in (
            "carbon_reduction",
            "acceptance_delta",
            "future_fit_delta",
            "makespan_change",
            "decision_overhead",
            "sla_delta",
        )
    }
    result["sample_count"] = len(samples)
    result["worst_acceptance_delta"] = min(float(item["acceptance_delta"]) for item in samples)
    result["group_weights"] = dict(samples[0]["group_weights"])
    result["feasible"] = (
        result["acceptance_delta"] >= -0.02
        and result["worst_acceptance_delta"] >= -0.05
        and result["sla_delta"] <= 0.0
    )
    # All terms are dimensionless paired changes. Positive is better.
    result["calibration_score"] = (
        0.50 * result["carbon_reduction"]
        + 0.25 * result["acceptance_delta"]
        + 0.15 * result["future_fit_delta"]
        - 0.07 * max(0.0, result["makespan_change"])
        - 0.03 * max(0.0, result["decision_overhead"])
    )
    return result


def calibrate(
    rows: list[dict[str, Any]],
    training_seeds: set[int],
    validation_seeds: set[int],
) -> dict[str, Any]:
    grouped = profile_samples(rows)
    profiles: list[dict[str, Any]] = []
    for label, samples in sorted(grouped.items()):
        training = aggregate([item for item in samples if item["seed"] in training_seeds])
        validation = aggregate([item for item in samples if item["seed"] in validation_seeds])
        profiles.append({"label": label, "training": training, "validation": validation})
    feasible = [item for item in profiles if item["training"].get("feasible")]
    ranked = sorted(
        feasible or profiles,
        key=lambda item: float(item["training"].get("calibration_score", float("-inf"))),
        reverse=True,
    )
    selected = ranked[0] if ranked else None
    return {
        "selection_rule": {
            "training_objective": "0.50*carbon_reduction_per_accepted_task + 0.25*acceptance_delta + 0.15*future_fit_delta - 0.07*makespan_regression - 0.03*decision_overhead",
            "constraints": {
                "mean_acceptance_delta_min": -0.02,
                "worst_acceptance_delta_min": -0.05,
                "mean_sla_delta_max": 0.0,
            },
            "training_seeds": sorted(training_seeds),
            "validation_seeds": sorted(validation_seeds),
        },
        "selected_profile": selected,
        "profiles": profiles,
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# B6 绿色权重校准",
        "",
        "> 权重仅由训练随机种子选择，验证随机种子只用于报告泛化结果。正的碳变化表示减排。",
        "",
        "| 配置 | 训练可行 | 训练减碳 | 训练接纳差 | 训练Future-Fit差 | 验证减碳 | 验证接纳差 | 验证Future-Fit差 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in result.get("profiles", []):
        train = item.get("training") or {}
        valid = item.get("validation") or {}
        lines.append(
            f"| {item['label']} | {str(bool(train.get('feasible'))).lower()} | "
            f"{float(train.get('carbon_reduction', 0.0)) * 100:.2f}% | "
            f"{float(train.get('acceptance_delta', 0.0)) * 100:.2f}pp | "
            f"{float(train.get('future_fit_delta', 0.0)):.4f} | "
            f"{float(valid.get('carbon_reduction', 0.0)) * 100:.2f}% | "
            f"{float(valid.get('acceptance_delta', 0.0)) * 100:.2f}pp | "
            f"{float(valid.get('future_fit_delta', 0.0)):.4f} |"
        )
    selected = result.get("selected_profile")
    if selected:
        lines.extend([
            "",
            "## 推荐实验配置",
            "",
            f"`{selected['label']}`：`{json.dumps(selected['training'].get('group_weights') or {}, ensure_ascii=False)}`",
            "",
            "该配置仍属于实验配置；只有验证集同时满足接纳率、SLA和减碳要求后，才应进入 CloudSim 实际执行复核。",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Select B6 green intent weights on training seeds and report held-out validation.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/fragmentation_green_experiments.json"))
    parser.add_argument("--output", type=Path, default=Path("exp_out/fragmentation_green/calibration.json"))
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = calibrate(
        rows,
        {int(item) for item in config.get("training_seeds") or []},
        {int(item) for item in config.get("validation_seeds") or []},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, args.output.with_suffix(".md"))
    selected = result.get("selected_profile") or {}
    print(f"selected {selected.get('label', 'none')}; wrote {args.output}")


if __name__ == "__main__":
    main()
