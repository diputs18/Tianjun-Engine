from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


METRICS = (
    "acceptance_rate",
    "predicted_makespan",
    "predicted_carbon_g",
    "predicted_carbon_g_per_assignment",
    "predicted_sla_violations",
    "future_fit_after",
    "future_fit_loss",
    "future_fit_loss_per_assignment",
    "plan_utility",
    "decision_time_ms",
    "baseline_acceptance_delta",
    "baseline_carbon_reduction",
    "baseline_carbon_per_assignment_reduction",
)

T_CRITICAL_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row.get("experiment_label", row.get("strategy", "unknown")),
            row.get("objective_scope", "flat_full"),
            row.get("node_count"),
            row.get("batch_task_count"),
            row.get("load_rate"),
            row.get("workload"),
            row.get("fragmentation_mode", "uniform"),
        )
        grouped[key].append(row)

    output: list[dict[str, Any]] = []
    for key, samples in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        label, scope, nodes, tasks, load, workload, fragmentation_mode = key
        result: dict[str, Any] = {
            "experiment_label": label,
            "objective_scope": scope,
            "active_objectives": "|".join(str(item) for item in samples[0].get("active_objectives") or []),
            "node_count": nodes,
            "batch_task_count": tasks,
            "load_rate": load,
            "workload": workload,
            "fragmentation_mode": fragmentation_mode,
            "sample_count": len(samples),
        }
        for metric in METRICS:
            values = [float(row[metric]) for row in samples if row.get(metric) is not None]
            if not values:
                result[f"{metric}_mean"] = None
                result[f"{metric}_ci95"] = None
                continue
            result[f"{metric}_mean"] = statistics.fmean(values)
            result[f"{metric}_ci95"] = (
                T_CRITICAL_95.get(len(values) - 1, 1.96)
                * statistics.stdev(values)
                / math.sqrt(len(values))
                if len(values) > 1
                else 0.0
            )
        output.append(result)
    return output


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 天钧引擎目标消融实验汇总",
        "",
        "每个单元格按相同节点数、任务数、负载和工作负载聚合随机种子；`±` 后为 95% 置信区间。",
        "",
        "| 实验 | 范围 | 场景 | n | 接纳率 | 运行碳(g) | 碳/接纳任务(g) | Future-Fit | FF损失/接纳任务 | 方案效用 | 决策时间(ms) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        scenario = (
            f"N{row['node_count']}/T{row['batch_task_count']}/"
            f"L{float(row['load_rate']):.2f}/{row['workload']}/{row['fragmentation_mode']}"
        )
        lines.append(
            "| {label} | {scope} | {scenario} | {n} | {acceptance} | {carbon} | {carbon_per_task} | {future_fit} | {future_fit_loss} | {utility} | {latency} |".format(
                label=row["experiment_label"],
                scope=row["objective_scope"],
                scenario=scenario,
                n=row["sample_count"],
                acceptance=_mean_ci(row, "acceptance_rate", 4),
                carbon=_mean_ci(row, "predicted_carbon_g", 3),
                carbon_per_task=_mean_ci(row, "predicted_carbon_g_per_assignment", 4),
                future_fit=_mean_ci(row, "future_fit_after", 4),
                future_fit_loss=_mean_ci(row, "future_fit_loss_per_assignment", 5),
                utility=_mean_ci(row, "plan_utility", 4),
                latency=_mean_ci(row, "decision_time_ms", 2),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mean_ci(row: dict[str, Any], metric: str, digits: int) -> str:
    mean = row.get(f"{metric}_mean")
    ci = row.get(f"{metric}_ci95")
    if mean is None:
        return "--"
    return f"{float(mean):.{digits}f} ± {float(ci or 0):.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate objective-ablation results with 95% confidence intervals.")
    parser.add_argument("input", help="Raw JSON produced by tianjun.experiments.runner")
    parser.add_argument("--csv", default="exp_out/summary.csv")
    parser.add_argument("--markdown", default="exp_out/summary.md")
    args = parser.parse_args()
    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = summarize(rows)
    write_csv(summary, Path(args.csv))
    write_markdown(summary, Path(args.markdown))
    print(f"wrote {len(summary)} aggregate rows to {args.csv} and {args.markdown}")


if __name__ == "__main__":
    main()
