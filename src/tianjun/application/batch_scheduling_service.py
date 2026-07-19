from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass
from statistics import mean
from typing import TYPE_CHECKING, Any

from ..domain import (
    BatchAssignment,
    BatchSchedulingPlan,
    BatchStatus,
    BatchValidationIssue,
    BatchValidationReport,
    GROUP_KEYS,
    METRIC_KEYS,
    ReservationLedger,
    ResourceSnapshot,
    ResourceVector,
    RunningTask,
    Task,
    TaskBatch,
    TaskStatus,
    UnassignedTask,
    clamp,
)
from ..scenarios import task_from_dict
from ..experiments import AssignmentCandidate, milp_oracle, nsga2_assignments

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


MAX_BATCH_TASKS = 1000
MAX_BATCH_BYTES = 5 * 1024 * 1024
B6_LOCAL_SEARCH_TASK_LIMIT = 24
B6_LOCAL_SEARCH_NODE_LIMIT = 4
B6_FUTURE_FIT_SAMPLE_LIMIT = 32
DEFAULT_STRATEGIES = [
    "B0-current",
    "B1-batch-greedy",
    "B3-batch-local-search",
    "B4-pareto-tchebycheff",
    "B6-hierarchical-batch",
]
NAMED_BATCH_PROFILES: dict[str, dict[str, Any]] = {
    "B6-green-single-v1": {
        "strategy": "B6-hierarchical-batch",
        "active_groups": ["green_carbon"],
        "group_weights": {"green_carbon": 1.0},
    },
    "B6-green-sla-85-v1": {
        "strategy": "B6-hierarchical-batch",
        "active_groups": ["green_carbon", "sla_quality"],
        "group_weights": {"green_carbon": 0.85, "sla_quality": 0.15},
    },
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


class BatchRequestError(ValueError):
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload))
        self.status_code = status_code
        self.payload = payload


@dataclass(slots=True)
class BatchSchedulingService:
    control_plane: CentralControlPlane

    def import_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list):
            raise BatchRequestError(400, {"error": "tasks must be a JSON array"})
        return self._import(
            raw_tasks,
            client_batch_id=str(payload.get("client_batch_id") or ""),
            batch_name=str(payload.get("batch_name") or "未命名批次"),
            defaults=dict(payload.get("defaults") or {}),
            batch_preferences=dict(payload.get("batch_preferences") or {}),
        )

    def import_csv(self, text: str, *, batch_name: str = "CSV批次") -> dict[str, Any]:
        if len(text.encode("utf-8")) > MAX_BATCH_BYTES:
            raise BatchRequestError(413, {"error": "batch file exceeds 5MB"})
        try:
            reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
            rows = list(reader)
        except csv.Error as exc:
            raise BatchRequestError(400, {"error": f"invalid CSV: {exc}"}) from exc
        required = {"task_id", "task_type", "cpu", "memory", "gpu", "storage", "estimated_duration", "priority"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise BatchRequestError(400, {"error": f"CSV missing required columns: {', '.join(missing)}"})
        raw_tasks: list[dict[str, Any]] = []
        csv_issues: list[BatchValidationIssue] = []
        for index, row in enumerate(rows, start=2):
            try:
                raw_tasks.append(self._csv_row(row, index))
            except BatchRequestError as exc:
                for item in exc.payload.get("validation", {}).get("errors", []):
                    csv_issues.append(BatchValidationIssue(
                        int(item.get("row", index)),
                        str(item.get("field", "row")),
                        str(item.get("code", "INVALID_VALUE")),
                        str(item.get("message", "invalid CSV value")),
                    ))
        if csv_issues:
            raise BatchRequestError(422, {"error": "batch validation failed", "validation": BatchValidationReport(max(0, len(rows) - len({item.row for item in csv_issues})), errors=csv_issues).to_dict()})
        return self._import(raw_tasks, client_batch_id="", batch_name=batch_name, defaults={}, batch_preferences={})

    def _import(
        self,
        raw_tasks: list[Any],
        *,
        client_batch_id: str,
        batch_name: str,
        defaults: dict[str, Any],
        batch_preferences: dict[str, Any],
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            if not raw_tasks:
                raise BatchRequestError(422, {"error": "batch must contain at least one task", "validation": BatchValidationReport(0).to_dict()})
            if len(raw_tasks) > MAX_BATCH_TASKS:
                raise BatchRequestError(413, {"error": f"batch exceeds {MAX_BATCH_TASKS} tasks"})
            if client_batch_id and client_batch_id in control.batch_idempotency:
                existing_id = control.batch_idempotency[client_batch_id]
                existing = control.task_batches[existing_id]
                return {**existing.to_dict(include_tasks=False), "idempotent_replay": True, "validation": BatchValidationReport(len(existing.tasks)).to_dict()}

            issues: list[BatchValidationIssue] = []
            normalized: list[dict[str, Any]] = []
            seen: set[str] = set()
            existing_batch_task_ids = {
                task.task_id
                for existing_batch in control.task_batches.values()
                for task in existing_batch.tasks
            }
            batch_intent = dict(batch_preferences.get("intent_weights") or {})
            for index, item in enumerate(raw_tasks, start=1):
                if not isinstance(item, dict):
                    issues.append(BatchValidationIssue(index, "task", "INVALID_ROW", "task row must be an object"))
                    continue
                task_payload = {**defaults, **item}
                task_payload["batch_id"] = "pending"
                task_payload["intent_weights"] = {**batch_intent, **dict(task_payload.get("intent_weights") or {})}
                task_id = str(task_payload.get("task_id") or "").strip()
                if not task_id:
                    issues.append(BatchValidationIssue(index, "task_id", "REQUIRED", "task_id is required"))
                elif task_id in seen or task_id in control.tasks or task_id in existing_batch_task_ids:
                    issues.append(BatchValidationIssue(index, "task_id", "DUPLICATE_TASK_ID", f"task_id {task_id} already exists"))
                seen.add(task_id)
                for key in ("cpu", "memory", "gpu", "storage"):
                    value = dict(task_payload.get("demand") or {}).get(key, 0)
                    try:
                        if float(value) < 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        issues.append(BatchValidationIssue(index, f"demand.{key}", "INVALID_RESOURCE", f"{key} must be non-negative"))
                try:
                    if int(task_payload.get("estimated_duration", 0)) <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    issues.append(BatchValidationIssue(index, "estimated_duration", "INVALID_DURATION", "estimated_duration must be positive"))
                for key in ("carbon_priority",):
                    try:
                        value = float(task_payload.get(key, 0.0))
                        if not 0.0 <= value <= 1.0:
                            raise ValueError
                    except (TypeError, ValueError):
                        issues.append(BatchValidationIssue(index, key, "OUT_OF_RANGE", f"{key} must be between 0 and 1"))
                if str(task_payload.get("security_level", "medium")) not in {"low", "medium", "high"}:
                    issues.append(BatchValidationIssue(index, "security_level", "INVALID_SECURITY_LEVEL", "security_level must be low, medium or high"))
                if task_payload.get("carbon_budget_g") is not None:
                    try:
                        if float(task_payload["carbon_budget_g"]) < 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        issues.append(BatchValidationIssue(index, "carbon_budget_g", "INVALID_CARBON_BUDGET", "carbon_budget_g must be non-negative"))
                normalized.append(task_payload)

            report = BatchValidationReport(max(0, len(raw_tasks) - len({item.row for item in issues})), errors=issues)
            if issues:
                raise BatchRequestError(422, {"error": "batch validation failed", "validation": report.to_dict()})

            digest = hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            batch_id = f"batch-{int(time.time() * 1000)}-{digest[:8]}"
            tasks: list[Task] = []
            created_tick = control.current_tick()
            for payload in normalized:
                payload["batch_id"] = batch_id
                task = task_from_dict(payload)
                task.submit_tick = created_tick
                if task.deadline is not None and task.deadline <= created_tick:
                    task.deadline = created_tick + task.deadline
                tasks.append(task)
            client_id = client_batch_id or f"client-{int(time.time() * 1000)}-{digest[:8]}"
            batch = TaskBatch(
                batch_id=batch_id,
                client_batch_id=client_id,
                batch_name=batch_name,
                tasks=tasks,
                defaults=defaults,
                batch_preferences=batch_preferences,
                status=BatchStatus.VALIDATED,
                content_hash=digest,
                created_tick=created_tick,
            )
            control.task_batches[batch_id] = batch
            control.batch_idempotency[client_id] = batch_id
            return {**batch.to_dict(include_tasks=False), "validation": BatchValidationReport(len(tasks)).to_dict()}

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        batch = self._batch(batch_id)
        payload = batch.to_dict()
        if batch.latest_plan_id and batch.latest_plan_id in self.control_plane.batch_plans:
            payload["latest_plan"] = self.control_plane.batch_plans[batch.latest_plan_id].to_dict()
        return payload

    def actual_metrics(self, batch_id: str) -> dict[str, Any]:
        """Return measured execution outcomes, distinct from preview predictions."""
        batch = self._batch(batch_id)
        committed_plans = [
            plan
            for plan in self.control_plane.batch_plans.values()
            if plan.batch_id == batch_id and plan.status == "committed"
        ]
        plan = committed_plans[-1] if committed_plans else None
        assigned_ids = {assignment.task_id for assignment in plan.assignments} if plan else set()
        latest_records: dict[str, Any] = {}
        for record in self.control_plane.execution_history:
            if record.batch_id == batch_id:
                latest_records[record.task_id] = record
        records = list(latest_records.values())
        jct = [record.jct_seconds for record in records if record.jct_seconds > 0.0]
        waits = [record.queue_wait_seconds for record in records]
        succeeded = sum(1 for record in records if record.success)
        failed = len(records) - succeeded
        unassigned_count = len(plan.unassigned_tasks) if plan else 0
        if assigned_ids and len(records) >= len(assigned_ids):
            if failed >= len(assigned_ids):
                batch.status = BatchStatus.FAILED
            elif failed or unassigned_count:
                batch.status = BatchStatus.PARTIAL_FAILED
            else:
                batch.status = BatchStatus.COMPLETED
        return {
            "batch_id": batch_id,
            "status": batch.status.value,
            "strategy": plan.strategy if plan else None,
            "task_count": len(batch.tasks),
            "assigned_count": len(assigned_ids),
            "unassigned_count": unassigned_count,
            "completed_count": len(records),
            "succeeded_count": succeeded,
            "failed_count": failed,
            "actual_acceptance_rate": round(len(assigned_ids) / max(1, len(batch.tasks)), 6),
            "actual_completion_rate": round(len(records) / max(1, len(batch.tasks)), 6),
            "average_jct_seconds": round(mean(jct), 6) if jct else 0.0,
            "p95_jct_seconds": round(_percentile(jct, 0.95), 6),
            "makespan_seconds": round(max(jct), 6) if jct else 0.0,
            "average_queue_wait_seconds": round(mean(waits), 6) if waits else 0.0,
            "average_cpu_utilization": round(mean(record.cpu_utilization for record in records), 6) if records else 0.0,
            "average_memory_utilization": round(mean(record.memory_utilization for record in records), 6) if records else 0.0,
            "average_bandwidth_utilization": round(mean(record.bandwidth_utilization for record in records), 6) if records else 0.0,
            "average_storage_utilization": round(mean(record.storage_utilization for record in records), 6) if records else 0.0,
            "total_energy_kwh": round(sum(record.energy_kwh for record in records), 8),
            "total_operational_carbon_g": round(sum(record.operational_carbon_g for record in records), 6),
            "total_cost": round(sum(record.cost for record in records), 6),
            "sla_violation_count": sum(1 for record in records if not record.sla_met),
            "prediction": None if plan is None else {
                "decision_time_ms": round(plan.decision_time_ms, 6),
                "makespan": plan.predicted_makespan,
                "energy_kwh": round(plan.predicted_energy_kwh, 8),
                "operational_carbon_g": round(plan.predicted_carbon_g, 6),
                "sla_violations": plan.predicted_sla_violations,
                "future_fit_before": round(plan.future_fit_before, 6),
                "future_fit_after": round(plan.future_fit_after, 6),
            },
        }

    def preview(self, batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(payload or {})
        requested_strategy = str(options.get("strategy") or "B6-hierarchical-batch")
        profile = NAMED_BATCH_PROFILES.get(requested_strategy)
        if profile:
            options = {**profile, **options, "strategy": profile["strategy"]}
            options["active_groups"] = profile["active_groups"]
            options["group_weights"] = profile["group_weights"]
        strategy = str(options.get("strategy") or "B6-hierarchical-batch")
        experiment_mode = bool(options.get("experiment_mode"))
        if strategy in {"B2-milp-oracle", "B5-nsga2"} and not experiment_mode:
            raise BatchRequestError(403, {"error": f"{strategy} is available only when experiment_mode=true"})
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            batch = self._batch(batch_id)
            active_metrics = self._validated_objectives(options.get("active_metrics"), METRIC_KEYS, "active_metrics")
            active_groups = self._validated_objectives(options.get("active_groups"), GROUP_KEYS, "active_groups")
            group_weight_overrides = self._validated_weights(
                options.get("group_weights"), GROUP_KEYS, "group_weights"
            )
            plan = self._build_plan(
                batch,
                strategy=strategy,
                active_metrics=active_metrics,
                active_groups=active_groups,
                group_weight_overrides=group_weight_overrides,
            )
            plan.strategy = requested_strategy
            control.batch_plans[plan.plan_id] = plan
            batch.latest_plan_id = plan.plan_id
            batch.status = BatchStatus.PREVIEWED
            return plan.to_dict()

    def compare(self, batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(payload or {})
        strategies = [str(item) for item in options.get("strategies", DEFAULT_STRATEGIES)]
        if not strategies:
            strategies = list(DEFAULT_STRATEGIES)
        experiment_mode = bool(options.get("experiment_mode"))
        plans = [self.preview(batch_id, {
            "strategy": strategy,
            "experiment_mode": experiment_mode,
            "active_metrics": options.get("active_metrics"),
            "active_groups": options.get("active_groups"),
            "group_weights": options.get("group_weights"),
        }) for strategy in strategies]
        recommended = max(
            plans,
            key=lambda item: (
                len(item["task_node_assignments"]),
                -item["predicted_sla_violations"],
                -item["predicted_carbon_g"],
                -item["predicted_makespan"],
            ),
        )
        return {"batch_id": batch_id, "strategies": plans, "recommended_plan_id": recommended["plan_id"]}

    def commit(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not bool(payload.get("confirmed_by_user_button") or payload.get("confirmed")):
            raise BatchRequestError(403, {"error": "batch commit requires explicit confirmation"})
        control = self.control_plane
        with control.lock:
            batch = self._batch(batch_id)
            plan_id = str(payload.get("plan_id") or batch.latest_plan_id or "")
            plan = control.batch_plans.get(plan_id)
            if plan is None or plan.batch_id != batch_id:
                raise BatchRequestError(404, {"error": "batch plan not found"})
            requested_version = int(payload.get("resource_snapshot_version", -1))
            if requested_version != plan.resource_snapshot_version or requested_version != control.resource_snapshot_version:
                raise BatchRequestError(409, {"error": "SNAPSHOT_CONFLICT", "expected_version": control.resource_snapshot_version, "plan_version": plan.resource_snapshot_version})
            task_by_id = {task.task_id: task for task in batch.tasks}
            demand_by_node: dict[str, ResourceVector] = {}
            for assignment in plan.assignments:
                task = task_by_id[assignment.task_id]
                demand_by_node[assignment.node_id] = demand_by_node.get(assignment.node_id, ResourceVector()) + task.demand
            for node_id, demand in demand_by_node.items():
                node = control.nodes.get(node_id)
                if node is None or not demand.fits_in(node.available()):
                    raise BatchRequestError(409, {"error": "SNAPSHOT_CONFLICT", "node_id": node_id})

            ledger = ReservationLedger(plan_id=plan.plan_id, resource_snapshot_version=plan.resource_snapshot_version)
            for node_id, demand in demand_by_node.items():
                ledger.reserve(node_id, demand)
            control.reservation_ledgers[plan.plan_id] = ledger
            tick = control.current_tick()
            for task in batch.tasks:
                if task.task_id not in control.tasks:
                    task.submit_tick = tick
                    control.tasks[task.task_id] = task
                    control.pending_queue.append(task.task_id)
                    control._persist_task(task)
            leases = []
            for assignment in plan.assignments:
                task = task_by_id[assignment.task_id]
                task.status = TaskStatus.RESERVED
                lease = control.task_lease_service.activate_task_lease(
                    task=task,
                    node=control.nodes[assignment.node_id],
                    decision=assignment.decision,
                    tick=tick,
                    remove_from_pending=True,
                )
                leases.append(lease.to_dict())
            control.resource_snapshot_version += 1
            batch.status = BatchStatus.RUNNING if leases else BatchStatus.COMMITTED
            plan.status = "committed"
            return {
                "status": "committed",
                "batch_id": batch_id,
                "plan_id": plan.plan_id,
                "resource_snapshot_version": control.resource_snapshot_version,
                "reservation_ledger": ledger.to_dict(),
                "leases": leases,
                "unassigned_tasks": [item.to_dict() for item in plan.unassigned_tasks],
            }

    def report(self) -> dict[str, Any]:
        control = self.control_plane
        batches = list(control.task_batches.values())
        assigned = sum(len(plan.assignments) for plan in control.batch_plans.values() if plan.status == "committed")
        total = sum(len(batch.tasks) for batch in batches)
        return {
            "total_batches": len(batches),
            "total_batch_tasks": total,
            "committed_assignments": assigned,
            "batch_acceptance_rate": round(assigned / total, 4) if total else 0.0,
            "recent_batches": [batch.to_dict(include_tasks=False) for batch in batches[-8:]],
        }

    def _build_plan(
        self,
        batch: TaskBatch,
        *,
        strategy: str,
        active_metrics: tuple[str, ...] | None = None,
        active_groups: tuple[str, ...] | None = None,
        group_weight_overrides: dict[str, float] | None = None,
    ) -> BatchSchedulingPlan:
        control = self.control_plane
        started = time.perf_counter()
        shadow_nodes = {node_id: copy.deepcopy(node) for node_id, node in control.nodes.items()}
        snapshot = ResourceSnapshot(
            version=control.resource_snapshot_version,
            tick=control.current_tick(),
            available_by_node={node_id: node.available() for node_id, node in shadow_nodes.items()},
        )
        # B0 preserves the legacy submission order. Joint strategies use the
        # deterministic urgency/priority/scarcity ordering defined for batches.
        ordered = list(batch.tasks) if strategy == "B0-current" else sorted(batch.tasks, key=self._task_sort_key)
        assignments: list[BatchAssignment] = []
        unassigned: list[UnassignedTask] = []
        if strategy == "B6-hierarchical-batch":
            scoring = "hierarchical_tchebycheff"
        elif strategy in {"B4-pareto-tchebycheff", "pareto_tchebycheff"}:
            scoring = "pareto_tchebycheff"
        else:
            scoring = "weighted_sum"
        if strategy in {"B2-milp-oracle", "B5-nsga2"}:
            assignments, unassigned = self._experimental_assign(
                batch=batch,
                ordered=ordered,
                shadow_nodes=shadow_nodes,
                tick=snapshot.tick,
                strategy=strategy,
                active_metrics=active_metrics,
                active_groups=active_groups,
                group_weight_overrides=group_weight_overrides,
            )
        else:
            future_tasks_for_scoring = (
                ordered
                if self._needs_future_fit(active_metrics, active_groups)
                else ()
            )
            for task in ordered:
                decision = control.scheduler.select_node(
                    task,
                    shadow_nodes.values(),
                    current_tick=snapshot.tick,
                    topology_nodes=shadow_nodes.values(),
                    scoring_strategy=scoring,
                    active_metrics=active_metrics,
                    active_groups=active_groups,
                    group_weight_overrides=group_weight_overrides,
                    future_tasks=future_tasks_for_scoring,
                )
                if decision is None:
                    unassigned.append(UnassignedTask(task.task_id, self._rejection_reason(task, shadow_nodes.values())))
                    continue
                node = shadow_nodes[decision.node_id]
                carbon = dict(decision.network_snapshot.get("carbon") or {})
                assignments.append(BatchAssignment(
                    task_id=task.task_id,
                    node_id=node.node_id,
                    decision=decision,
                    predicted_energy_kwh=float(carbon.get("facility_energy_kwh", 0.0)) + float(carbon.get("network_energy_kwh", 0.0)),
                    predicted_carbon_g=float(carbon.get("operational_carbon_g", 0.0)),
                ))
                node.running_tasks[f"__batch__{task.task_id}"] = self._shadow_running_task(task, decision, snapshot.tick)

        if strategy in {"B3-batch-local-search", "B4-pareto-tchebycheff"}:
            assignments, unassigned = self._local_improve(
                batch=batch,
                assignments=assignments,
                unassigned=unassigned,
                shadow_nodes=shadow_nodes,
                tick=snapshot.tick,
                scoring=scoring,
                active_metrics=active_metrics,
                active_groups=active_groups,
            )
        elif strategy == "B6-hierarchical-batch":
            assignments, unassigned = self._local_improve_hierarchical(
                batch=batch,
                assignments=assignments,
                unassigned=unassigned,
                shadow_nodes=shadow_nodes,
                tick=snapshot.tick,
                active_metrics=active_metrics,
                active_groups=active_groups,
                group_weight_overrides=group_weight_overrides,
            )

        task_samples = batch.tasks[: min(64, len(batch.tasks))]
        future_before = self._future_fit(control.nodes.values(), task_samples)
        summary = self._plan_hierarchical_summary(
            batch,
            assignments,
            shadow_nodes.values(),
            snapshot.tick,
            active_groups=active_groups,
            group_weight_overrides=group_weight_overrides,
        )
        plan_id = f"plan-{batch.batch_id}-{strategy}-{int(time.time() * 1000)}"
        return BatchSchedulingPlan(
            plan_id=plan_id,
            batch_id=batch.batch_id,
            strategy=strategy,
            resource_snapshot_version=snapshot.version,
            assignments=assignments,
            unassigned_tasks=unassigned,
            objective_breakdown=summary["atomic_scores"],
            group_objective_breakdown=summary["group_scores"],
            group_weights=summary["group_weights"],
            plan_utility=summary["plan_utility"],
            security_risk_penalty=summary["security_risk_penalty"],
            objective_hierarchy_version="five-groups-v1" if strategy == "B6-hierarchical-batch" else "flat-ten-v1",
            active_objectives=list(active_groups or GROUP_KEYS) if strategy == "B6-hierarchical-batch" else list(active_metrics or METRIC_KEYS),
            predicted_makespan=summary["predicted_makespan"],
            predicted_cost=sum(item.decision.predicted_cost for item in assignments),
            predicted_energy_kwh=sum(item.predicted_energy_kwh for item in assignments),
            predicted_carbon_g=sum(item.predicted_carbon_g for item in assignments),
            predicted_sla_violations=summary["predicted_sla_violations"],
            future_fit_before=future_before,
            future_fit_after=summary["future_fit_after"],
            decision_time_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _experimental_assign(
        self,
        *,
        batch: TaskBatch,
        ordered: list[Task],
        shadow_nodes: dict[str, Any],
        tick: int,
        strategy: str,
        active_metrics: tuple[str, ...] | None,
        active_groups: tuple[str, ...] | None,
        group_weight_overrides: dict[str, float] | None,
    ) -> tuple[list[BatchAssignment], list[UnassignedTask]]:
        if strategy == "B2-milp-oracle" and (len(ordered) > 20 or len(shadow_nodes) > 20):
            raise BatchRequestError(422, {"error": "B2-milp-oracle is limited to 20 tasks x 20 nodes"})
        candidates: list[AssignmentCandidate] = []
        nodes = list(shadow_nodes.values())
        task_by_id = {task.task_id: task for task in ordered}
        future_tasks_for_scoring = (
            ordered
            if self._needs_future_fit(active_metrics, active_groups)
            else ()
        )
        for task in ordered:
            for node in nodes:
                decision = self.control_plane.scheduler.select_node(
                    task,
                    [node],
                    current_tick=tick,
                    topology_nodes=nodes,
                    scoring_strategy="pareto_tchebycheff" if strategy == "B5-nsga2" else "weighted_sum",
                    active_metrics=active_metrics,
                    active_groups=active_groups,
                    group_weight_overrides=group_weight_overrides,
                    future_tasks=future_tasks_for_scoring,
                )
                if decision is None:
                    continue
                candidates.append(AssignmentCandidate(
                    task_id=task.task_id,
                    node_id=node.node_id,
                    utility=decision.total_score,
                    demand=task.demand.to_dict(),
                    objectives=dict(decision.metric_scores),
                    payload=decision,
                ))
        capacities = {node.node_id: node.available().to_dict() for node in nodes}
        if strategy == "B2-milp-oracle":
            solution = milp_oracle(candidates, capacities)
        else:
            front = nsga2_assignments(candidates, capacities)
            solution = max(front, key=lambda item: (item.assigned_count, item.utility), default=None)
            if solution is None:
                selected_ids: set[str] = set()
                return [], [UnassignedTask(task.task_id, self._rejection_reason(task, nodes)) for task in ordered if task.task_id not in selected_ids]
        assignments: list[BatchAssignment] = []
        selected_ids = {item.task_id for item in solution.selected}
        for item in solution.selected:
            task = task_by_id[item.task_id]
            decision = item.payload
            decision.network_snapshot["experiment_solver_status"] = solution.status
            carbon = dict(decision.network_snapshot.get("carbon") or {})
            assignment = BatchAssignment(
                task_id=item.task_id,
                node_id=item.node_id,
                decision=decision,
                predicted_energy_kwh=float(carbon.get("facility_energy_kwh", 0.0)) + float(carbon.get("network_energy_kwh", 0.0)),
                predicted_carbon_g=float(carbon.get("operational_carbon_g", 0.0)),
            )
            assignments.append(assignment)
            shadow_nodes[item.node_id].running_tasks[f"__batch__{item.task_id}"] = self._shadow_running_task(task, decision, tick)
        unassigned = [
            UnassignedTask(task.task_id, self._rejection_reason(task, nodes))
            for task in ordered
            if task.task_id not in selected_ids
        ]
        return assignments, unassigned

    def _local_improve(
        self,
        *,
        batch: TaskBatch,
        assignments: list[BatchAssignment],
        unassigned: list[UnassignedTask],
        shadow_nodes: dict[str, Any],
        tick: int,
        scoring: str,
        active_metrics: tuple[str, ...] | None,
        active_groups: tuple[str, ...] | None,
    ) -> tuple[list[BatchAssignment], list[UnassignedTask]]:
        """One bounded exchange/backfill pass suitable for the online B3/B4 path."""
        task_by_id = {task.task_id: task for task in batch.tasks}
        future_tasks_for_scoring = (
            task_by_id.values()
            if self._needs_future_fit(active_metrics, active_groups)
            else ()
        )
        improved: list[BatchAssignment] = []
        for assignment in assignments:
            task = task_by_id[assignment.task_id]
            old_node = shadow_nodes[assignment.node_id]
            old_node.running_tasks.pop(f"__batch__{task.task_id}", None)
            alternative = self.control_plane.scheduler.select_node(
                task,
                shadow_nodes.values(),
                current_tick=tick,
                topology_nodes=shadow_nodes.values(),
                scoring_strategy=scoring,
                active_metrics=active_metrics,
                active_groups=active_groups,
                future_tasks=future_tasks_for_scoring,
            )
            replacement = assignment
            if alternative is not None:
                carbon = dict(alternative.network_snapshot.get("carbon") or {})
                alternative_assignment = BatchAssignment(
                    task_id=task.task_id,
                    node_id=alternative.node_id,
                    decision=alternative,
                    predicted_energy_kwh=float(carbon.get("facility_energy_kwh", 0.0)) + float(carbon.get("network_energy_kwh", 0.0)),
                    predicted_carbon_g=float(carbon.get("operational_carbon_g", 0.0)),
                )
                better_utility = alternative.total_score > assignment.decision.total_score + 1e-9
                greener_tie = (
                    alternative_assignment.predicted_carbon_g + 1e-9 < assignment.predicted_carbon_g
                    and alternative.total_score >= assignment.decision.total_score * 0.98
                )
                if better_utility or greener_tie:
                    replacement = alternative_assignment
            selected_node = shadow_nodes[replacement.node_id]
            selected_node.running_tasks[f"__batch__{task.task_id}"] = self._shadow_running_task(task, replacement.decision, tick)
            improved.append(replacement)

        remaining: list[UnassignedTask] = []
        for item in unassigned:
            task = task_by_id[item.task_id]
            decision = self.control_plane.scheduler.select_node(
                task,
                shadow_nodes.values(),
                current_tick=tick,
                topology_nodes=shadow_nodes.values(),
                scoring_strategy=scoring,
                active_metrics=active_metrics,
                active_groups=active_groups,
                future_tasks=future_tasks_for_scoring,
            )
            if decision is None:
                remaining.append(item)
                continue
            carbon = dict(decision.network_snapshot.get("carbon") or {})
            assignment = BatchAssignment(
                task_id=task.task_id,
                node_id=decision.node_id,
                decision=decision,
                predicted_energy_kwh=float(carbon.get("facility_energy_kwh", 0.0)) + float(carbon.get("network_energy_kwh", 0.0)),
                predicted_carbon_g=float(carbon.get("operational_carbon_g", 0.0)),
            )
            shadow_nodes[decision.node_id].running_tasks[f"__batch__{task.task_id}"] = self._shadow_running_task(task, decision, tick)
            improved.append(assignment)
        return improved, remaining

    def _local_improve_hierarchical(
        self,
        *,
        batch: TaskBatch,
        assignments: list[BatchAssignment],
        unassigned: list[UnassignedTask],
        shadow_nodes: dict[str, Any],
        tick: int,
        active_metrics: tuple[str, ...] | None,
        active_groups: tuple[str, ...] | None,
        group_weight_overrides: dict[str, float] | None,
    ) -> tuple[list[BatchAssignment], list[UnassignedTask]]:
        """Bounded plan-level search; replacements are accepted by delta J(X)."""
        task_by_id = {task.task_id: task for task in batch.tasks}
        future_samples = list(task_by_id.values())[:B6_FUTURE_FIT_SAMPLE_LIMIT]
        scoring_future_samples = (
            future_samples
            if self._needs_future_fit(active_metrics, active_groups)
            else ()
        )
        improved = list(assignments)
        for index, current in enumerate(list(improved)[:B6_LOCAL_SEARCH_TASK_LIMIT]):
            task = task_by_id[current.task_id]
            shadow_nodes[current.node_id].running_tasks.pop(f"__batch__{task.task_id}", None)
            trials: list[tuple[float, float, BatchAssignment]] = []
            current_node = shadow_nodes[current.node_id]
            alternatives = sorted(
                (
                    node
                    for node in shadow_nodes.values()
                    if node.node_id != current.node_id and node.can_host_now(task)
                ),
                key=lambda node: (
                    -node.dominant_utilization_after(task.demand),
                    node.carbon_profile.intensity_at(tick),
                    node.node_id,
                ),
            )[: max(0, B6_LOCAL_SEARCH_NODE_LIMIT - 1)]
            candidate_nodes = [current_node, *alternatives]
            for node in candidate_nodes:
                decision = self.control_plane.scheduler.select_node(
                    task,
                    [node],
                    current_tick=tick,
                    topology_nodes=shadow_nodes.values(),
                    scoring_strategy="hierarchical_tchebycheff",
                    active_metrics=active_metrics,
                    active_groups=active_groups,
                    group_weight_overrides=group_weight_overrides,
                    future_tasks=scoring_future_samples,
                )
                if decision is None:
                    continue
                candidate = self._assignment_from_decision(task, decision)
                node.running_tasks[f"__batch__{task.task_id}"] = self._shadow_running_task(task, decision, tick)
                proposal = list(improved)
                proposal[index] = candidate
                summary = self._plan_hierarchical_summary(
                    batch,
                    proposal,
                    shadow_nodes.values(),
                    tick,
                    active_groups=active_groups,
                    group_weight_overrides=group_weight_overrides,
                    calculate_future_fit=False,
                )
                trials.append((summary["plan_utility"], -candidate.predicted_carbon_g, candidate))
                node.running_tasks.pop(f"__batch__{task.task_id}", None)

            replacement = max(trials, key=lambda item: (item[0], item[1], item[2].node_id))[2] if trials else current
            improved[index] = replacement
            shadow_nodes[replacement.node_id].running_tasks[f"__batch__{task.task_id}"] = self._shadow_running_task(
                task, replacement.decision, tick
            )

        remaining: list[UnassignedTask] = []
        for item in unassigned:
            task = task_by_id[item.task_id]
            decision = self.control_plane.scheduler.select_node(
                task,
                shadow_nodes.values(),
                current_tick=tick,
                topology_nodes=shadow_nodes.values(),
                scoring_strategy="hierarchical_tchebycheff",
                active_metrics=active_metrics,
                active_groups=active_groups,
                group_weight_overrides=group_weight_overrides,
                future_tasks=scoring_future_samples,
            )
            if decision is None:
                remaining.append(item)
                continue
            candidate = self._assignment_from_decision(task, decision)
            shadow_nodes[decision.node_id].running_tasks[f"__batch__{task.task_id}"] = self._shadow_running_task(
                task, decision, tick
            )
            improved.append(candidate)
        return improved, remaining

    @staticmethod
    def _assignment_from_decision(task: Task, decision: Any) -> BatchAssignment:
        carbon = dict(decision.network_snapshot.get("carbon") or {})
        return BatchAssignment(
            task_id=task.task_id,
            node_id=decision.node_id,
            decision=decision,
            predicted_energy_kwh=float(carbon.get("facility_energy_kwh", 0.0))
            + float(carbon.get("network_energy_kwh", 0.0)),
            predicted_carbon_g=float(carbon.get("operational_carbon_g", 0.0)),
        )

    def _plan_hierarchical_summary(
        self,
        batch: TaskBatch,
        assignments: list[BatchAssignment],
        nodes: Any,
        tick: int,
        *,
        active_groups: tuple[str, ...] | None,
        group_weight_overrides: dict[str, float] | None,
        calculate_future_fit: bool = True,
    ) -> dict[str, Any]:
        selected_groups = active_groups or GROUP_KEYS
        task_by_id = {task.task_id: task for task in batch.tasks}
        count = len(assignments)
        atomic_totals = {key: 0.0 for key in METRIC_KEYS}
        group_totals = {key: 0.0 for key in GROUP_KEYS}
        weight_totals = {key: 0.0 for key in selected_groups}
        security_penalty = 0.0
        placement_penalty = 0.0
        for assignment in assignments:
            decision = assignment.decision
            for key in METRIC_KEYS:
                atomic_totals[key] += float(decision.metric_scores.get(key, 0.0))
            decision_groups = dict(decision.network_snapshot.get("objective_groups") or {})
            if not decision_groups:
                decision_groups = self.control_plane.scheduler.objective_group_scores(decision.metric_scores)
            for key in GROUP_KEYS:
                group_totals[key] += float(decision_groups.get(key, 0.0))
            decision_weights = dict(decision.network_snapshot.get("objective_group_weights") or {})
            for key in selected_groups:
                weight_totals[key] += float(decision_weights.get(key, 0.0))
            security_penalty += float(decision.network_snapshot.get("security_risk_penalty", 0.0))
            placement_penalty += sum(
                float(value)
                for value in dict(decision.network_snapshot.get("placement_penalties") or {}).values()
            )

        denominator = max(1, count)
        atomic_scores = {key: value / denominator for key, value in atomic_totals.items()}
        group_scores = {key: value / denominator for key, value in group_totals.items()}
        group_weights = self.control_plane.scheduler._masked_weights(
            group_weight_overrides
            or (
                {key: value / denominator for key, value in weight_totals.items()}
                if count
                else self.control_plane.policy_state.current_group_weights()
            ),
            selected_groups,
        )
        should_calculate_future_fit = calculate_future_fit or "resource_efficiency" in selected_groups
        task_samples = batch.tasks[: min(64, len(batch.tasks))]
        future_fit_after = self._future_fit(nodes, task_samples) if should_calculate_future_fit else 0.0
        if count and should_calculate_future_fit:
            group_scores["resource_efficiency"] = clamp(
                0.60 * group_scores["resource_efficiency"] + 0.40 * future_fit_after
                - placement_penalty / denominator
            )
        predicted_sla = sum(
            1
            for item in assignments
            if task_by_id[item.task_id].effective_deadline_tick() is not None
            and item.decision.predicted_finish_tick
            > int(task_by_id[item.task_id].effective_deadline_tick() or 0)
        )
        if count:
            group_scores["sla_quality"] *= 1.0 - (predicted_sla / count)
        average_security_penalty = security_penalty / denominator
        scalar = (
            self.control_plane.scheduler.tchebycheff_utility(
                group_scores, group_weights, selected_groups
            )
            if count
            else 0.0
        )
        acceptance_rate = count / max(1, len(batch.tasks))
        plan_utility = 0.65 * acceptance_rate + 0.35 * max(0.0, scalar - average_security_penalty)
        makespan = max((item.decision.predicted_finish_tick for item in assignments), default=tick) - tick
        return {
            "atomic_scores": atomic_scores,
            "group_scores": group_scores,
            "group_weights": group_weights,
            "plan_utility": plan_utility,
            "security_risk_penalty": average_security_penalty,
            "future_fit_after": future_fit_after,
            "predicted_sla_violations": predicted_sla,
            "predicted_makespan": max(0, makespan),
        }

    @staticmethod
    def _needs_future_fit(
        active_metrics: tuple[str, ...] | None,
        active_groups: tuple[str, ...] | None,
    ) -> bool:
        if active_groups is not None:
            return "resource_efficiency" in active_groups
        if active_metrics is not None:
            return "fragmentation" in active_metrics
        return True

    @staticmethod
    def _shadow_running_task(task: Task, decision: Any, tick: int) -> RunningTask:
        return RunningTask(
            task_id=task.task_id,
            node_id=decision.node_id,
            allocation=task.demand,
            start_tick=tick,
            predicted_duration=max(1, decision.predicted_finish_tick - tick),
            actual_duration=0,
            finish_tick=decision.predicted_finish_tick,
            success_probability=1.0,
        )

    @staticmethod
    def _validated_objectives(value: Any, allowed: tuple[str, ...], field: str) -> tuple[str, ...] | None:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)):
            raise BatchRequestError(422, {"error": f"{field} must be an array"})
        unknown = [str(item) for item in value if str(item) not in allowed]
        if unknown:
            raise BatchRequestError(422, {"error": f"unknown {field}: {', '.join(unknown)}"})
        unique = tuple(dict.fromkeys(str(item) for item in value))
        if not unique:
            raise BatchRequestError(422, {"error": f"{field} cannot be empty"})
        return unique

    @staticmethod
    def _validated_weights(
        value: Any,
        allowed: tuple[str, ...],
        field: str,
    ) -> dict[str, float] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise BatchRequestError(422, {"error": f"{field} must be an object"})
        unknown = [str(key) for key in value if str(key) not in allowed]
        if unknown:
            raise BatchRequestError(422, {"error": f"unknown {field}: {', '.join(unknown)}"})
        weights = {str(key): float(weight) for key, weight in value.items()}
        if any(weight < 0.0 for weight in weights.values()) or sum(weights.values()) <= 0.0:
            raise BatchRequestError(422, {"error": f"{field} values must be non-negative with a positive sum"})
        return weights

    def _batch(self, batch_id: str) -> TaskBatch:
        batch = self.control_plane.task_batches.get(batch_id)
        if batch is None:
            raise BatchRequestError(404, {"error": f"unknown batch {batch_id}"})
        return batch

    def _task_sort_key(self, task: Task) -> tuple[float, int, float, int, str]:
        tick = self.control_plane.current_tick()
        fleet = ResourceVector()
        for node in self.control_plane.nodes.values():
            fleet = fleet + node.capacity
        scarcity = task.demand.dominant_share_against(fleet)
        deadline = task.effective_deadline_tick() if task.effective_deadline_tick() is not None else 10**12
        return (float(deadline - tick - task.estimated_duration), -task.priority, -scarcity, task.submit_tick, task.task_id)

    def _future_fit(self, nodes: Any, tasks: list[Task]) -> float:
        nodes_list = list(nodes)
        if not nodes_list or not tasks:
            return 0.0
        # Average the per-node Future-Fit values instead of counting a future
        # task as feasible when just one node can host it.  The former is the
        # task-node feasible-pair ratio and therefore drops when placement
        # consumes interchangeable capacity or creates resource-shape holes.
        feasible_pairs = sum(
            1
            for node in nodes_list
            for task in tasks
            if self._future_task_fits(node, task)
        )
        return feasible_pairs / (len(nodes_list) * len(tasks))

    def _future_task_fits(self, node: Any, task: Task) -> bool:
        if not node.can_host_now(task):
            return False
        path = node.path_profile_for(task.network_source())
        if task.max_latency_ms is not None and path.robust_latency_ms() > task.max_latency_ms:
            return False
        if task.min_bandwidth_mbps is not None and path.guaranteed_bandwidth_mbps() < task.min_bandwidth_mbps:
            return False
        if task.carbon_budget_g is not None:
            predicted = node.predict_operational_carbon(task, node.predict_duration(task), self.control_plane.current_tick())
            if float(predicted["operational_carbon_g"]) > task.carbon_budget_g:
                return False
        return True

    @staticmethod
    def _rejection_reason(task: Task, nodes: Any) -> str:
        nodes_list = list(nodes)
        if task.demand.gpu > 0 and all(node.available().gpu + 1e-9 < task.demand.gpu for node in nodes_list):
            return "INSUFFICIENT_GPU"
        if task.allowed_regions and all(not any(node.matches_deployment_region(region) for region in task.allowed_regions) for node in nodes_list):
            return "REGION_FORBIDDEN"
        if task.carbon_budget_g is not None:
            return "CARBON_BUDGET_EXCEEDED"
        if task.deadline is not None:
            return "DEADLINE_INFEASIBLE"
        return "NO_FEASIBLE_NODE"

    @staticmethod
    def _csv_row(row: dict[str, str], row_number: int) -> dict[str, Any]:
        def number(name: str, default: float = 0.0) -> float:
            text = str(row.get(name, "")).strip()
            if text == "":
                return default
            try:
                return float(text)
            except ValueError as exc:
                raise BatchRequestError(422, {"error": "batch validation failed", "validation": BatchValidationReport(0, errors=[BatchValidationIssue(row_number, name, "INVALID_NUMBER", f"{name} must be numeric")]).to_dict()}) from exc

        def boolean(name: str, default: bool) -> bool:
            text = str(row.get(name, "")).strip().lower()
            if text == "":
                return default
            if text not in {"true", "false"}:
                raise BatchRequestError(422, {"error": "batch validation failed", "validation": BatchValidationReport(0, errors=[BatchValidationIssue(row_number, name, "INVALID_BOOLEAN", f"{name} must be true or false")]).to_dict()})
            return text == "true"

        payload: dict[str, Any] = {
            "task_id": str(row.get("task_id", "")).strip(),
            "task_type": str(row.get("task_type", "batch")).strip() or "batch",
            "demand": {key: number(key) for key in ("cpu", "memory", "gpu", "storage")},
            "estimated_duration": int(number("estimated_duration", 0)),
            "priority": int(number("priority", 5)),
            "security_level": str(row.get("security_level", "medium")).strip() or "medium",
            "isolation_level": str(row.get("isolation_level", "process")).strip() or "process",
            "allowed_regions": [item for item in str(row.get("allowed_regions", "")).split("|") if item],
            "forbidden_nodes": [item for item in str(row.get("forbidden_nodes", "")).split("|") if item],
            "require_encrypted_transport": boolean("require_encrypted_transport", True),
            "allow_region_shift": boolean("allow_region_shift", True),
            "allow_time_shift": boolean("allow_time_shift", False),
            "carbon_priority": number("carbon_priority", 0.0),
        }
        region = str(row.get("region", "")).strip()
        if region and not payload["allowed_regions"]:
            payload["allowed_regions"] = [region]
        optional_numbers = ("budget", "deadline", "input_size_gb", "max_latency_ms", "min_bandwidth_mbps", "carbon_budget_g", "deferrable_until_tick")
        for key in optional_numbers:
            text = str(row.get(key, "")).strip()
            if text:
                payload[key] = float(text) if key not in {"deadline", "deferrable_until_tick"} else int(float(text))
        for key in ("data_region", "source_region"):
            text = str(row.get(key, "")).strip()
            if text:
                payload[key] = text
        return payload
