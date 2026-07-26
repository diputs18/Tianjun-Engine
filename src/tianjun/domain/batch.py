from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .decision import SchedulingDecision
from .resource import ResourceVector
from .task import Task


class BatchStatus(str, Enum):
    IMPORTED = "imported"
    VALIDATED = "validated"
    PREVIEWED = "previewed"
    COMMITTED = "committed"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


@dataclass(slots=True)
class BatchValidationIssue:
    row: int
    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }


@dataclass(slots=True)
class BatchValidationReport:
    valid_count: int
    errors: list[BatchValidationIssue] = field(default_factory=list)
    warnings: list[BatchValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_count": self.valid_count,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass(slots=True)
class TaskBatch:
    batch_id: str
    client_batch_id: str
    batch_name: str
    tasks: list[Task]
    defaults: dict[str, Any] = field(default_factory=dict)
    batch_preferences: dict[str, Any] = field(default_factory=dict)
    status: BatchStatus = BatchStatus.VALIDATED
    content_hash: str = ""
    created_tick: int = 0
    latest_plan_id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, tasks: list[Task]) -> "TaskBatch":
        return cls(
            batch_id=str(payload["batch_id"]),
            client_batch_id=str(payload["client_batch_id"]),
            batch_name=str(payload.get("batch_name") or "未命名批次"),
            tasks=tasks,
            defaults=dict(payload.get("defaults") or {}),
            batch_preferences=dict(payload.get("batch_preferences") or {}),
            status=BatchStatus(str(payload.get("status") or BatchStatus.VALIDATED.value)),
            content_hash=str(payload.get("content_hash") or ""),
            created_tick=int(payload.get("created_tick", 0)),
            latest_plan_id=payload.get("latest_plan_id"),
        )

    def to_dict(self, *, include_tasks: bool = True) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "client_batch_id": self.client_batch_id,
            "batch_name": self.batch_name,
            "status": self.status.value,
            "task_count": len(self.tasks),
            "content_hash": self.content_hash,
            "created_tick": self.created_tick,
            "latest_plan_id": self.latest_plan_id,
            "defaults": dict(self.defaults),
            "batch_preferences": dict(self.batch_preferences),
            "tasks": [task.to_dict() for task in self.tasks] if include_tasks else [],
        }


@dataclass(slots=True)
class ResourceSnapshot:
    version: int
    tick: int
    available_by_node: dict[str, ResourceVector]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tick": self.tick,
            "available_by_node": {
                node_id: available.to_dict()
                for node_id, available in sorted(self.available_by_node.items())
            },
        }


@dataclass(slots=True)
class BatchAssignment:
    task_id: str
    node_id: str
    decision: SchedulingDecision
    predicted_energy_kwh: float = 0.0
    predicted_carbon_g: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BatchAssignment":
        return cls(
            task_id=str(payload["task_id"]),
            node_id=str(payload["node_id"]),
            decision=SchedulingDecision.from_dict(dict(payload["decision"])),
            predicted_energy_kwh=float(payload.get("predicted_energy_kwh", 0.0)),
            predicted_carbon_g=float(payload.get("predicted_carbon_g", 0.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "node_id": self.node_id,
            "predicted_energy_kwh": round(self.predicted_energy_kwh, 8),
            "predicted_carbon_g": round(self.predicted_carbon_g, 6),
            "decision": self.decision.to_dict(),
        }


@dataclass(slots=True)
class UnassignedTask:
    task_id: str
    reason: str
    detail: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnassignedTask":
        return cls(
            task_id=str(payload["task_id"]),
            reason=str(payload.get("reason") or ""),
            detail=str(payload.get("detail") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {"task_id": self.task_id, "reason": self.reason, "detail": self.detail}


@dataclass(slots=True)
class BatchSchedulingPlan:
    plan_id: str
    batch_id: str
    strategy: str
    resource_snapshot_version: int
    assignments: list[BatchAssignment]
    unassigned_tasks: list[UnassignedTask]
    objective_breakdown: dict[str, float]
    predicted_makespan: int
    predicted_cost: float
    predicted_energy_kwh: float
    predicted_carbon_g: float
    predicted_sla_violations: int
    future_fit_before: float
    future_fit_after: float
    decision_time_ms: float
    group_objective_breakdown: dict[str, float] = field(default_factory=dict)
    group_weights: dict[str, float] = field(default_factory=dict)
    plan_utility: float = 0.0
    security_risk_penalty: float = 0.0
    objective_hierarchy_version: str = "flat-ten-v1"
    active_objectives: list[str] = field(default_factory=list)
    status: str = "previewed"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BatchSchedulingPlan":
        return cls(
            plan_id=str(payload["plan_id"]),
            batch_id=str(payload["batch_id"]),
            strategy=str(payload.get("strategy") or "B6-hierarchical-batch"),
            resource_snapshot_version=int(payload.get("resource_snapshot_version", 0)),
            assignments=[BatchAssignment.from_dict(dict(item)) for item in payload.get("task_node_assignments", [])],
            unassigned_tasks=[UnassignedTask.from_dict(dict(item)) for item in payload.get("unassigned_tasks", [])],
            objective_breakdown={str(key): float(value) for key, value in dict(payload.get("objective_breakdown") or {}).items()},
            predicted_makespan=int(payload.get("predicted_makespan", 0)),
            predicted_cost=float(payload.get("predicted_cost", 0.0)),
            predicted_energy_kwh=float(payload.get("predicted_energy_kwh", 0.0)),
            predicted_carbon_g=float(payload.get("predicted_carbon_g", 0.0)),
            predicted_sla_violations=int(payload.get("predicted_sla_violations", 0)),
            future_fit_before=float(payload.get("future_fit_before", 0.0)),
            future_fit_after=float(payload.get("future_fit_after", 0.0)),
            decision_time_ms=float(payload.get("decision_time_ms", 0.0)),
            group_objective_breakdown={str(key): float(value) for key, value in dict(payload.get("group_objective_breakdown") or {}).items()},
            group_weights={str(key): float(value) for key, value in dict(payload.get("group_weights") or {}).items()},
            plan_utility=float(payload.get("plan_utility", 0.0)),
            security_risk_penalty=float(payload.get("security_risk_penalty", 0.0)),
            objective_hierarchy_version=str(payload.get("objective_hierarchy_version") or "flat-ten-v1"),
            active_objectives=[str(item) for item in payload.get("active_objectives", [])],
            status=str(payload.get("status") or "previewed"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "batch_id": self.batch_id,
            "strategy": self.strategy,
            "status": self.status,
            "resource_snapshot_version": self.resource_snapshot_version,
            "task_node_assignments": [item.to_dict() for item in self.assignments],
            "unassigned_tasks": [item.to_dict() for item in self.unassigned_tasks],
            "objective_breakdown": {
                key: round(value, 6) for key, value in self.objective_breakdown.items()
            },
            "group_objective_breakdown": {
                key: round(value, 6) for key, value in self.group_objective_breakdown.items()
            },
            "group_weights": {
                key: round(value, 6) for key, value in self.group_weights.items()
            },
            "plan_utility": round(self.plan_utility, 6),
            "security_risk_penalty": round(self.security_risk_penalty, 6),
            "objective_hierarchy_version": self.objective_hierarchy_version,
            "active_objectives": list(self.active_objectives),
            "predicted_makespan": self.predicted_makespan,
            "predicted_cost": round(self.predicted_cost, 6),
            "predicted_energy_kwh": round(self.predicted_energy_kwh, 8),
            "predicted_carbon_g": round(self.predicted_carbon_g, 6),
            "predicted_sla_violations": self.predicted_sla_violations,
            "future_fit_before": round(self.future_fit_before, 6),
            "future_fit_after": round(self.future_fit_after, 6),
            "decision_time_ms": round(self.decision_time_ms, 3),
        }


@dataclass(slots=True)
class ReservationLedger:
    plan_id: str
    resource_snapshot_version: int
    reservations: dict[str, ResourceVector] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReservationLedger":
        return cls(
            plan_id=str(payload["plan_id"]),
            resource_snapshot_version=int(payload.get("resource_snapshot_version", 0)),
            reservations={
                str(node_id): ResourceVector(**{
                    key: float(value) for key, value in dict(demand).items()
                    if key in ResourceVector.__dataclass_fields__
                })
                for node_id, demand in dict(payload.get("reservations") or {}).items()
            },
        )

    def reserve(self, node_id: str, demand: ResourceVector) -> None:
        self.reservations[node_id] = self.reservations.get(node_id, ResourceVector()) + demand

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "resource_snapshot_version": self.resource_snapshot_version,
            "reservations": {
                node_id: demand.to_dict()
                for node_id, demand in sorted(self.reservations.items())
            },
        }
