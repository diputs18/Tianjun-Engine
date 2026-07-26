from __future__ import annotations

import time
from statistics import mean
from typing import TYPE_CHECKING, Any

from ..domain import ResourceVector, Task, TaskStatus

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


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
    "resource_load_source",
    "resource_load_source_label",
    "telemetry_freshness",
    "carbon_data_source",
    "carbon_data_source_label",
    "carbon_data_freshness",
    "simulation_tick",
    "active_task_ids",
    "active_stages",
}

SCHEDULING_NODE_FIELDS = SUMMARY_NODE_FIELDS | {"network_paths"}


def build_dashboard_report(
    control: "CentralControlPlane",
    view: str,
    *,
    cursor: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Build one dashboard page from a short, consistent control-plane snapshot."""
    normalized_view = view if view in VIEW_FIELDS else "summary"
    requested_fields = VIEW_FIELDS[normalized_view]
    with control.lock:
        control._expire_stale_nodes()
        tick = control.current_tick()
        records = list(control.execution_history)
        decisions = list(control.decision_log)
        tasks = dict(control.tasks)
        pending_ids = list(control.pending_queue)
        lease_count = len(control.leases)
        snapshot_version = control.resource_snapshot_version
        audit_log = list(control.tool_audit_log)
        report: dict[str, Any] = {
            "tick": tick,
            "generated_at": time.time(),
            "report_version": f"{snapshot_version}:{tick}",
            "resource_snapshot_version": snapshot_version,
        }
        if "nodes" in requested_fields:
            node_fields = (
                SCHEDULING_NODE_FIELDS
                if normalized_view == "scheduling"
                else SUMMARY_NODE_FIELDS
                if normalized_view == "summary"
                else None
            )
            node_payloads = [control._node_report_payload(node) for node in control.nodes.values()]
            report["nodes"] = (
                [
                    {key: value for key, value in node.items() if key in node_fields}
                    for node in node_payloads
                ]
                if node_fields is not None
                else node_payloads
            )
        if "physical_topology" in requested_fields:
            report["physical_topology"] = (
                None if control.physical_topology is None else control.physical_topology.to_dict()
            )
        if "recent_decisions" in requested_fields:
            decision_limit = 3 if normalized_view in {"summary", "topology"} else 8
            report["recent_decisions"] = [item.to_dict() for item in decisions[-decision_limit:]]
        if "active_runs" in requested_fields:
            report["active_runs"] = control._active_runs_payload()
        if "recent_progress_events" in requested_fields:
            report["recent_progress_events"] = list(control.progress_events[-16:])
        if "recent_records" in requested_fields:
            report["recent_records"] = [record.to_dict() for record in records[-8:]]
        if "task_statuses" in requested_fields:
            report["task_statuses"] = {
                task_id: task.status.value for task_id, task in sorted(tasks.items())
            }
        if "pending_task_queue" in requested_fields:
            report["pending_task_queue"] = [
                tasks[task_id].to_dict()
                for task_id in pending_ids
                if task_id in tasks and tasks[task_id].status == TaskStatus.PENDING
            ]
        if "execution_records" in requested_fields:
            safe_cursor = max(0, int(cursor))
            safe_limit = max(1, min(200, int(limit)))
            end = max(0, len(records) - safe_cursor)
            start = max(0, end - safe_limit)
            report["execution_records"] = [record.to_dict() for record in records[start:end]]
            report["pagination"] = {
                "cursor": safe_cursor,
                "limit": safe_limit,
                "total": len(records),
                "next_cursor": None if start == 0 else safe_cursor + (end - start),
            }
        if "batch_scheduling" in requested_fields:
            report["batch_scheduling"] = control.batch_scheduling_service.report()
        if "policy_history" in requested_fields:
            report["policy_history"] = [
                entry.to_dict() for entry in control.policy_state.adjustment_history[-50:]
            ]
        policy_weights = control.policy_state.current_weights()
        group_weights = control.policy_state.current_group_weights()
        topology_available = control.physical_topology is not None

    succeeded = [record for record in records if record.success]
    failed = [record for record in records if not record.success]
    report["totals"] = {
        "tasks": len(tasks),
        "completed_attempts": len(records),
        "succeeded_attempts": len(succeeded),
        "failed_attempts": len(failed),
        "completed": len(records),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "pending_tasks": len(pending_ids),
        "leased_tasks": lease_count,
        "running_tasks": lease_count,
        "pending": len(pending_ids),
        "running": lease_count,
        "sla_met": sum(1 for record in records if record.sla_met),
        "sla_missed": sum(1 for record in records if not record.sla_met),
    }
    report["metrics"] = _report_metrics(records, decisions, tasks)
    external_calls = [item for item in audit_log if item.get("actor") == "external_mcp"]
    external_successes = [item for item in external_calls if item.get("result_status") == "success"]
    report["toolchain_runtime"] = {
        "external_mcp_last_call": external_calls[-1] if external_calls else None,
        "external_mcp_last_success": external_successes[-1] if external_successes else None,
        "external_mcp_call_count": len(external_calls),
        "external_mcp_success_count": len(external_successes),
        "recent_calls": audit_log[-20:],
    }

    model_runtime = control.scheduler.model_runtime.describe()
    loaded_models = set(model_runtime.get("loaded_models", []))
    model_predictions = [
        item.network_snapshot.get("model_prediction", {})
        for item in decisions
        if item.network_snapshot.get("model_prediction")
    ]
    if "model_runtime" in requested_fields:
        report["model_runtime"] = {
            **model_runtime,
            "latest_prediction": model_predictions[-1] if model_predictions else {},
        }
    if "policy_weights" in requested_fields:
        report["policy_weights"] = {key: round(value, 4) for key, value in policy_weights.items()}
    if "policy_group_weights" in requested_fields:
        report["policy_group_weights"] = {key: round(value, 4) for key, value in group_weights.items()}
    if "weight_sources" in requested_fields or "group_weight_sources" in requested_fields:
        reference = Task(
            task_id="__dashboard_weight_reference__",
            task_type="batch_cpu",
            demand=ResourceVector(cpu=1, memory=1, storage=1),
            estimated_duration=10,
        )
        if "weight_sources" in requested_fields:
            report["weight_sources"] = control.scheduler.weight_components(reference, tick)
        if "group_weight_sources" in requested_fields:
            report["group_weight_sources"] = control.scheduler.group_weight_components(reference, tick)
    if "algorithm_profile" in requested_fields:
        report["algorithm_profile"] = {
            "name": "deterministic_compute_network_policy_engine",
            "model_status": model_runtime["status"],
            "features": [
                "resource_fit",
                "deadline_completion",
                "network_stability",
                "operational_carbon",
                "batch_joint_allocation",
                "hierarchical_objective_fusion",
                *(("lstm_latency_prediction",) if "lstm" in loaded_models else ()),
                *(("graphsage_topology_score",) if "gnn" in loaded_models else ()),
            ],
        }
    report["data_gaps"] = {
        "latency_history": "链路序列当前可能来自画像合成；具体来源以节点与链路数据来源字段为准。",
        "bandwidth_utilization": "无端口遥测时使用链路画像估算，不标记为实时数据。",
        "gnn_topology_embedding": (
            "GraphSAGE 已加载并使用物理拓扑。"
            if "gnn" in loaded_models and topology_available
            else "GraphSAGE 未加载或缺少物理拓扑，使用确定性兜底。"
        ),
    }
    report["view"] = normalized_view
    return report


def _report_metrics(records: list[Any], decisions: list[Any], tasks: dict[str, Any]) -> dict[str, Any]:
    values = lambda attribute: [float(getattr(record, attribute, 0.0)) for record in records]
    actual_jct = [record.jct_seconds for record in records if record.jct_seconds > 0.0]
    queue_wait = values("queue_wait_seconds")
    carbon = values("operational_carbon_g")
    stable_latency = [
        float(item.network_snapshot.get("stable_latency_ms", item.network_snapshot.get("robust_latency_ms", 0.0)))
        for item in decisions
    ]
    fusion = [float(item.network_snapshot.get("feature_fusion_score", 0.0)) for item in decisions]
    confidences = [float(item.network_snapshot.get("deterministic_confidence", 0.0)) for item in decisions]
    batch_makespans: dict[str, float] = {}
    for record in records:
        if record.batch_id and record.jct_seconds > 0.0:
            batch_makespans[record.batch_id] = max(batch_makespans.get(record.batch_id, 0.0), record.jct_seconds)
    first_start: dict[str, int] = {}
    for record in records:
        first_start.setdefault(record.task_id, record.start_tick)
    waits = [first_start[task_id] - tasks[task_id].submit_tick for task_id in first_start if task_id in tasks]
    return {
        "success_rate": round(sum(1 for record in records if record.success) / len(records), 4) if records else 0.0,
        "average_wait_ticks": round(mean(waits), 4) if waits else 0.0,
        "average_cost": round(mean(values("cost")), 4) if records else 0.0,
        "average_network_delay_ticks": round(mean(values("network_delay_ticks")), 4) if records else 0.0,
        "average_network_risk": round(mean(values("network_risk")), 4) if records else 0.0,
        "total_energy_kwh": round(sum(values("energy_kwh")), 8),
        "total_operational_carbon_g": round(sum(carbon), 6),
        "average_operational_carbon_g_per_task": round(mean(carbon), 6) if carbon else 0.0,
        "average_actual_jct_seconds": round(mean(actual_jct), 6) if actual_jct else 0.0,
        "p95_actual_jct_seconds": round(_percentile(actual_jct, 0.95), 6),
        "average_queue_wait_seconds": round(mean(queue_wait), 6) if queue_wait else 0.0,
        "p95_queue_wait_seconds": round(_percentile(queue_wait, 0.95), 6),
        "actual_makespan_seconds": round(max(actual_jct), 6) if actual_jct else 0.0,
        "average_cpu_utilization": round(mean(values("cpu_utilization")), 6) if records else 0.0,
        "average_memory_utilization": round(mean(values("memory_utilization")), 6) if records else 0.0,
        "average_bandwidth_utilization": round(mean(values("bandwidth_utilization")), 6) if records else 0.0,
        "average_storage_utilization": round(mean(values("storage_utilization")), 6) if records else 0.0,
        "completed_batch_count": len(batch_makespans),
        "batch_makespan_seconds": {key: round(value, 6) for key, value in sorted(batch_makespans.items())},
        "average_stable_latency_ms": round(mean(stable_latency), 4) if stable_latency else 0.0,
        "average_fusion_score": round(mean(fusion), 4) if fusion else 0.0,
        "average_deterministic_confidence": round(mean(confidences), 4) if confidences else 0.0,
        "sla_rate": round(mean(1.0 if record.sla_met else 0.0 for record in records), 4) if records else 0.0,
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, percentile)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


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
