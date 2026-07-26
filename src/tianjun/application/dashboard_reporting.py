from __future__ import annotations

from typing import Any


COMMON_FIELDS = {
    "tick",
    "generated_at",
    "report_version",
    "resource_snapshot_version",
    "totals",
    "metrics",
    "toolchain_runtime",
    "data_gaps",
}

VIEW_FIELDS = {
    "summary": COMMON_FIELDS
    | {
        "batch_scheduling",
        "model_runtime",
        "nodes",
        "recent_decisions",
        "active_runs",
        "recent_progress_events",
        "recent_records",
        "task_statuses",
        "pending_task_queue",
    },
    "scheduling": COMMON_FIELDS
    | {
        "batch_scheduling",
        "model_runtime",
        "nodes",
        "recent_decisions",
        "active_runs",
        "pending_task_queue",
    },
    "topology": COMMON_FIELDS
    | {
        "nodes",
        "physical_topology",
        "recent_decisions",
        "active_runs",
        "recent_progress_events",
        "recent_records",
        "task_statuses",
    },
    "tasks": COMMON_FIELDS
    | {
        "task_statuses",
        "active_runs",
        "recent_progress_events",
        "recent_records",
        "execution_records",
        "pending_task_queue",
    },
    "model": COMMON_FIELDS
    | {
        "model_runtime",
        "policy_weights",
        "policy_group_weights",
        "weight_sources",
        "group_weight_sources",
        "policy_history",
        "batch_scheduling",
        "task_statuses",
        "recent_decisions",
        "algorithm_profile",
    },
}

SUMMARY_NODE_FIELDS = {
    "node_id",
    "region",
    "location",
    "service_region",
    "online",
    "health_score",
    "reliability_score",
    "capacity",
    "available",
    "runtime_utilization",
    "runtime_telemetry_available",
    "telemetry_source",
    "simulation_tick",
    "active_task_ids",
    "active_stages",
}

SCHEDULING_NODE_FIELDS = SUMMARY_NODE_FIELDS | {"network_paths"}


def dashboard_report_view(
    report: dict[str, Any],
    view: str,
    *,
    cursor: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Return a bounded Dashboard projection while preserving the full report API."""
    normalized_view = view if view in VIEW_FIELDS else "summary"
    result = {
        key: value
        for key, value in report.items()
        if key in VIEW_FIELDS[normalized_view]
    }
    result["view"] = normalized_view

    if normalized_view in {"summary", "scheduling"}:
        node_fields = SCHEDULING_NODE_FIELDS if normalized_view == "scheduling" else SUMMARY_NODE_FIELDS
        result["nodes"] = [
            {key: value for key, value in node.items() if key in node_fields}
            for node in report.get("nodes", [])
        ]

    decision_limit = 3 if normalized_view in {"summary", "topology"} else 8
    if "recent_decisions" in result:
        result["recent_decisions"] = list(report.get("recent_decisions", []))[-decision_limit:]

    if normalized_view == "tasks":
        records = list(report.get("execution_records", []))
        safe_cursor = max(0, int(cursor))
        safe_limit = max(1, min(200, int(limit)))
        end = max(0, len(records) - safe_cursor)
        start = max(0, end - safe_limit)
        result["execution_records"] = records[start:end]
        result["pagination"] = {
            "cursor": safe_cursor,
            "limit": safe_limit,
            "total": len(records),
            "next_cursor": None if start == 0 else safe_cursor + (end - start),
        }

    if normalized_view == "model" and "policy_history" in result:
        result["policy_history"] = list(report.get("policy_history", []))[-50:]

    return result
