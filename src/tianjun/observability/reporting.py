from __future__ import annotations


def format_report(report: dict) -> str:
    totals = report["totals"]
    metrics = report["metrics"]
    active_tasks = totals.get("running_tasks", totals.get("leased_tasks", 0))
    lines = [
        "Closed-Loop Compute Agent Report",
        f"Ticks elapsed: {report['tick']}",
        (
            "Attempts: "
            f"{totals['completed_attempts']} total, "
            f"{totals['succeeded_attempts']} succeeded, "
            f"{totals['failed_attempts']} failed"
        ),
        (
            "Tasks remaining: "
            f"{totals['pending_tasks']} pending, {active_tasks} active"
        ),
        (
            "Cluster metrics: "
            f"success_rate={metrics['success_rate']}, "
            f"sla_rate={metrics['sla_rate']}, "
            f"avg_wait={metrics['average_wait_ticks']}, "
            f"avg_cost={metrics['average_cost']}, "
            f"avg_net_delay={metrics.get('average_network_delay_ticks', 0.0)}, "
            f"avg_net_risk={metrics.get('average_network_risk', 0.0)}"
        ),
        "Current policy weights: "
        + ", ".join(f"{key}={value}" for key, value in report["policy_weights"].items()),
    ]

    if report["policy_history"]:
        lines.append("Recent policy adjustments:")
        for entry in report["policy_history"][-3:]:
            lines.append(f"  tick={entry['tick']}: {' | '.join(entry['reasons'])}")

    if report["recent_decisions"]:
        lines.append("Recent scheduling decisions:")
        for decision in report["recent_decisions"][-5:]:
            lines.append(
                "  "
                f"{decision['task_id']} -> {decision['node_id']} "
                f"(score={decision['total_score']}, cost={decision['predicted_cost']})"
            )
    return "\n".join(lines)
