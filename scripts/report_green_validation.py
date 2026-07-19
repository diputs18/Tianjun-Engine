from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean, stdev
from typing import Any


FORMAL_STRATEGIES = (
    "B0-current",
    "B6-green-single-v1",
    "B6-green-sla-85-v1",
)
METRICS = (
    "actual_acceptance_rate",
    "average_jct_seconds",
    "p95_jct_seconds",
    "makespan_seconds",
    "total_energy_kwh",
    "total_operational_carbon_g",
    "sla_violation_count",
    "decision_time_ms",
    "carbon_prediction_error_percent",
)
T_CRITICAL_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
}


def interval(values: list[float]) -> tuple[float, float, float]:
    center = fmean(values) if values else 0.0
    if len(values) < 2:
        return center, center, center
    margin = T_CRITICAL_95.get(len(values) - 1, 1.96) * stdev(values) / math.sqrt(len(values))
    return center, center - margin, center + margin


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the formal B0 vs green single/dual CloudSim report.")
    parser.add_argument("--input", type=Path, default=Path("exp_out/cloudsim_core/raw_metrics.csv"))
    parser.add_argument("--output", type=Path, default=Path("exp_out/cloudsim_green_validation"))
    args = parser.parse_args()
    rows = [row for row in read_rows(args.input) if row["strategy"] in FORMAL_STRATEGIES]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["strategy"], row["scenario"])].append(row)

    summary: list[dict[str, Any]] = []
    for (strategy, scenario), samples in sorted(grouped.items()):
        item: dict[str, Any] = {"strategy": strategy, "scenario": scenario, "n": len(samples)}
        for metric in METRICS:
            center, low, high = interval([float(sample[metric]) for sample in samples])
            item[f"{metric}_mean"] = center
            item[f"{metric}_ci95_low"] = low
            item[f"{metric}_ci95_high"] = high
        summary.append(item)

    indexed = {(row["strategy"], row["scenario"], row["seed"]): row for row in rows}
    effects: list[dict[str, Any]] = []
    for strategy in FORMAL_STRATEGIES[1:]:
        for scenario in sorted({row["scenario"] for row in rows}):
            seeds = sorted(row["seed"] for row in rows if row["strategy"] == strategy and row["scenario"] == scenario)
            for metric in ("average_jct_seconds", "p95_jct_seconds", "makespan_seconds", "total_operational_carbon_g"):
                deltas: list[float] = []
                relatives: list[float] = []
                for seed in seeds:
                    baseline = indexed.get(("B0-current", scenario, seed))
                    candidate = indexed.get((strategy, scenario, seed))
                    if baseline is None or candidate is None:
                        continue
                    base = float(baseline[metric])
                    delta = float(candidate[metric]) - base
                    deltas.append(delta)
                    relatives.append(delta / base * 100.0 if base else 0.0)
                center, low, high = interval(deltas)
                effects.append({
                    "strategy": strategy,
                    "scenario": scenario,
                    "metric": metric,
                    "paired_n": len(deltas),
                    "mean_delta": center,
                    "delta_ci95_low": low,
                    "delta_ci95_high": high,
                    "mean_relative_change_percent": fmean(relatives) if relatives else 0.0,
                })

    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(summary, args.output / "summary.csv")
    write_csv(effects, args.output / "paired_effects.csv")
    lines = [
        "# CloudSim 绿色单目标与双目标正式验证",
        "",
        "> 每个场景 10 个相同随机种子；指标来自 Cloudlet 实际执行，区间使用 Student-t 95% 置信区间。",
        "",
        "| 策略 | 场景 | n | 平均JCT(s) | P95 JCT(s) | Makespan(s) | 运行碳(g) | SLA违规 | 碳预测误差 | 决策时间(ms) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['strategy']} | {row['scenario']} | {row['n']} | "
            f"{row['average_jct_seconds_mean']:.4f} | {row['p95_jct_seconds_mean']:.4f} | "
            f"{row['makespan_seconds_mean']:.4f} | {row['total_operational_carbon_g_mean']:.4f} | "
            f"{row['sla_violation_count_mean']:.2f} | "
            f"{row['carbon_prediction_error_percent_mean']:.2f}% | {row['decision_time_ms_mean']:.2f} |"
        )
    lines.extend([
        "",
        "## 相对 B0 的配对效应",
        "",
        "| 策略 | 场景 | 指标 | n | 相对变化 | 差值95% CI |",
        "|---|---|---|---:|---:|---:|",
    ])
    for row in effects:
        lines.append(
            f"| {row['strategy']} | {row['scenario']} | {row['metric']} | {row['paired_n']} | "
            f"{row['mean_relative_change_percent']:.2f}% | "
            f"[{row['delta_ci95_low']:.6f}, {row['delta_ci95_high']:.6f}] |"
        )
    (args.output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote formal green validation report for {len(rows)} runs to {args.output.resolve()}")


if __name__ == "__main__":
    main()
