from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any


METRICS = (
    "actual_acceptance_rate",
    "actual_completion_rate",
    "average_jct_seconds",
    "p95_jct_seconds",
    "makespan_seconds",
    "average_cpu_utilization",
    "average_memory_utilization",
    "average_bandwidth_utilization",
    "total_energy_kwh",
    "total_operational_carbon_g",
    "sla_violation_count",
    "predicted_operational_carbon_g",
    "carbon_prediction_error_g",
    "carbon_prediction_error_percent",
)

T_CRITICAL_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def confidence_interval(values: list[float]) -> tuple[float, float, float]:
    center = mean(values) if values else 0.0
    if len(values) < 2:
        return center, center, center
    critical = T_CRITICAL_95.get(len(values) - 1, 1.96)
    margin = critical * stdev(values) / math.sqrt(len(values))
    return center, center - margin, center + margin


def load_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.metrics.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(root)
        parts = relative.parts
        if len(parts) < 4:
            continue
        prediction = payload.get("prediction") or {}
        predicted_carbon = float(prediction.get("operational_carbon_g", 0.0))
        actual_carbon = float(payload.get("total_operational_carbon_g", 0.0))
        rows.append({
            "strategy": parts[0],
            "scenario": parts[1],
            "seed": parts[2].removeprefix("seed-"),
            "source": str(relative),
            **{
                metric: float(payload.get(metric, 0.0))
                for metric in METRICS
                if metric not in {
                    "predicted_operational_carbon_g",
                    "carbon_prediction_error_g",
                    "carbon_prediction_error_percent",
                }
            },
            "predicted_operational_carbon_g": predicted_carbon,
            "carbon_prediction_error_g": actual_carbon - predicted_carbon,
            "carbon_prediction_error_percent": (
                (actual_carbon - predicted_carbon) / predicted_carbon * 100.0
                if predicted_carbon
                else 0.0
            ),
            "decision_time_ms": float(prediction.get("decision_time_ms", 0.0)),
            "future_fit_before": float(prediction.get("future_fit_before", 0.0)),
            "future_fit_after": float(prediction.get("future_fit_after", 0.0)),
        })
    return rows


def write_raw(rows: list[dict[str, Any]], root: Path) -> None:
    fields = list(rows[0]) if rows else ["strategy", "scenario", "seed"]
    with (root / "raw_metrics.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["strategy"], row["scenario"])].append(row)
    summary: list[dict[str, Any]] = []
    for (strategy, scenario), items in sorted(groups.items()):
        result: dict[str, Any] = {"strategy": strategy, "scenario": scenario, "n": len(items)}
        for metric in (*METRICS, "decision_time_ms", "future_fit_before", "future_fit_after"):
            center, lower, upper = confidence_interval([float(item[metric]) for item in items])
            result[f"{metric}_mean"] = center
            result[f"{metric}_ci95_low"] = lower
            result[f"{metric}_ci95_high"] = upper
        summary.append(result)
    fields = list(summary[0]) if summary else ["strategy", "scenario", "n"]
    with (root / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    return summary


def paired_effects(rows: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    indexed = {(row["strategy"], row["scenario"], row["seed"]): row for row in rows}
    effects: list[dict[str, Any]] = []
    strategies = sorted({row["strategy"] for row in rows if row["strategy"] != "B0-current"})
    scenarios = sorted({row["scenario"] for row in rows})
    for strategy in strategies:
        for scenario in scenarios:
            seeds = sorted({row["seed"] for row in rows if row["strategy"] == strategy and row["scenario"] == scenario})
            for metric in ("average_jct_seconds", "makespan_seconds", "total_energy_kwh", "total_operational_carbon_g", "actual_acceptance_rate"):
                deltas: list[float] = []
                relative: list[float] = []
                for seed in seeds:
                    baseline = indexed.get(("B0-current", scenario, seed))
                    candidate = indexed.get((strategy, scenario, seed))
                    if baseline is None or candidate is None:
                        continue
                    delta = float(candidate[metric]) - float(baseline[metric])
                    deltas.append(delta)
                    if float(baseline[metric]) != 0.0:
                        relative.append(delta / float(baseline[metric]) * 100.0)
                center, low, high = confidence_interval(deltas)
                effects.append({
                    "strategy": strategy,
                    "scenario": scenario,
                    "metric": metric,
                    "paired_n": len(deltas),
                    "mean_delta": center,
                    "delta_ci95_low": low,
                    "delta_ci95_high": high,
                    "mean_relative_change_percent": mean(relative) if relative else 0.0,
                })
    fields = list(effects[0]) if effects else ["strategy", "scenario", "metric", "paired_n"]
    with (root / "paired_effects.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(effects)
    return effects


def write_markdown(summary: list[dict[str, Any]], effects: list[dict[str, Any]], root: Path) -> None:
    lines = [
        "# CloudSim 核心策略实验统计",
        "",
        "> 数据来自 Cloudlet 实际执行回传；区间为按随机种子计算的 Student-t 95% 置信区间。碳口径为 operational_only。",
        "",
        "| 策略 | 场景 | n | 接纳率 | 平均 JCT(s) | Makespan(s) | 预测碳(g) | 实际运行碳(g) | 碳预测误差 | 决策时间(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            "| {strategy} | {scenario} | {n} | {acceptance:.4f} | {jct:.4f} | {makespan:.4f} | {predicted_carbon:.4f} | {carbon:.4f} | {carbon_error:.2f}% | {decision:.3f} |".format(
                strategy=row["strategy"], scenario=row["scenario"], n=row["n"],
                acceptance=row["actual_acceptance_rate_mean"], jct=row["average_jct_seconds_mean"],
                makespan=row["makespan_seconds_mean"],
                predicted_carbon=row["predicted_operational_carbon_g_mean"],
                carbon=row["total_operational_carbon_g_mean"], decision=row["decision_time_ms_mean"],
                carbon_error=row["carbon_prediction_error_percent_mean"],
            )
        )
    lines.extend(["", "## 相对 B0 的配对效应", "", "| 策略 | 场景 | 指标 | 配对数 | 平均差值 | 95% CI | 相对变化 |", "|---|---|---|---:|---:|---:|---:|"])
    for row in effects:
        lines.append(
            f"| {row['strategy']} | {row['scenario']} | {row['metric']} | {row['paired_n']} | "
            f"{row['mean_delta']:.6f} | [{row['delta_ci95_low']:.6f}, {row['delta_ci95_high']:.6f}] | "
            f"{row['mean_relative_change_percent']:.2f}% |"
        )
    (root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("exp_out/cloudsim_core"))
    args = parser.parse_args()
    root = args.input.resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = load_rows(root)
    if not rows:
        raise SystemExit(f"No *.metrics.json files found under {root}")
    write_raw(rows, root)
    summary = summarize(rows, root)
    effects = paired_effects(rows, root)
    write_markdown(summary, effects, root)
    print(f"analyzed {len(rows)} CloudSim runs; wrote statistics to {root}")


if __name__ == "__main__":
    main()
