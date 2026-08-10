from __future__ import annotations

import threading
import time
from math import ceil
from statistics import mean
from typing import Any

from ..core import ComputeNetworkPolicy, UserFeedback, UserRequirement
from ..domain import BatchSchedulingPlan, BatchStatus, ExecutionRecord, Node, PhysicalTopology, PolicyState, ReservationLedger, ResourceVector, SchedulingDecision, Task, TaskBatch, TaskStatus, clamp, normalize_weights
from ..policy.optimizer import PolicyOptimizer
from ..policy.clarifier import RequirementSession
from ..policy.generator import ComputeNetworkPolicyGenerator
from ..storage.sqlite_state_store import SQLiteStateStore
from ..scheduling.engine import ClosedLoopAdaptiveScheduler
from ..ml.runtime import TrainedModelRuntime
from .node_registry import NodeRegistry
from .policy_workflow import PolicyWorkflowService
from .requirement_dialogue import RequirementDialogueService
from .task_lease_service import TaskLease, TaskLeaseService
from .batch_scheduling_service import BatchSchedulingService
from .control_plane_state import restore_control_plane


def _truncate(text: str, limit: int = 400) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _percentile(values: list[float], percentile: float) -> float:
    """Return a linearly interpolated percentile without a NumPy dependency."""
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


class CentralControlPlane:
    def __init__(
        self,
        policy_state: PolicyState | None = None,
        policy_update_interval: int = 2,
        heartbeat_timeout_seconds: float = 15.0,
        lease_timeout_seconds: float = 60.0,
        state_store: SQLiteStateStore | None = None,
        scheduler: ClosedLoopAdaptiveScheduler | None = None,
        model_runtime: TrainedModelRuntime | None = None,
    ) -> None:
        self.policy_state = policy_state or PolicyState()
        self.scheduler = scheduler or ClosedLoopAdaptiveScheduler(
            self.policy_state,
            model_runtime=model_runtime,
        )
        self.optimizer = PolicyOptimizer()
        self.policy_generator = ComputeNetworkPolicyGenerator()
        self.policy_update_interval = policy_update_interval
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.lease_timeout_seconds = max(1.0, float(lease_timeout_seconds))
        self.state_store = state_store

        self.lock = threading.RLock()
        self.planning_lock = threading.Lock()
        self.started_at = time.monotonic()
        self.nodes: dict[str, Node] = {}
        self.tasks: dict[str, Task] = {}
        self.pending_queue: list[str] = []
        self.leases: dict[str, TaskLease] = {}
        self.decision_log: list[SchedulingDecision] = []
        self.execution_history: list[ExecutionRecord] = []
        self.task_progress: dict[str, dict[str, Any]] = {}
        self.progress_events: list[dict[str, Any]] = []
        self.last_heartbeat_at: dict[str, float] = {}
        self.last_heartbeat_epoch: dict[str, float] = {}
        self.policies: dict[str, ComputeNetworkPolicy] = {}
        self.policy_tasks: dict[str, Task] = {}
        self.user_feedback: list[UserFeedback] = []
        self.requirement_sessions: dict[str, RequirementSession] = {}
        self.physical_topology: PhysicalTopology | None = None
        self.resource_snapshot_version = 0
        self.task_batches: dict[str, Any] = {}
        self.batch_plans: dict[str, Any] = {}
        self.batch_idempotency: dict[str, str] = {}
        self.reservation_ledgers: dict[str, Any] = {}
        self.task_result_receipts: dict[str, dict[str, Any]] = {}
        self.latest_task_result_receipts: dict[str, dict[str, Any]] = {}
        self.tool_audit_log: list[dict[str, Any]] = []
        self.node_registry = NodeRegistry(self)
        self.task_lease_service = TaskLeaseService(self)
        self.batch_scheduling_service = BatchSchedulingService(self)
        self.policy_workflow = PolicyWorkflowService(self)
        self.requirement_dialogue = RequirementDialogueService(self)

        if self.state_store is not None:
            self._restore_from_store()
            self.state_store.set_control_value("policy_weights", self.policy_state.current_weights())
            self.state_store.set_control_value("policy_group_weights", self.policy_state.current_group_weights())

    def register_node(self, node: Node) -> dict[str, Any]:
        return self.node_registry.register_node(node)

    def register_topology(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            topology = PhysicalTopology.from_dict(payload)
            self.physical_topology = topology
            self.scheduler.set_physical_topology(topology)
            if self.state_store is not None:
                self.state_store.set_control_value("physical_topology", topology.to_dict())
            return topology.to_dict()

    def submit_task(self, task: Task) -> dict[str, Any]:
        return self.task_lease_service.submit_task(task)

    def preview_task(self, task: Task) -> dict[str, Any] | None:
        return self.task_lease_service.preview_task(task)

    def schedule_pending_task(self, task_id: str) -> dict[str, Any]:
        return self.task_lease_service.schedule_pending_task(task_id)

    def import_task_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.batch_scheduling_service.import_json(payload)

    def import_task_batch_csv(self, text: str, *, batch_name: str = "CSV批次") -> dict[str, Any]:
        return self.batch_scheduling_service.import_csv(text, batch_name=batch_name)

    def get_task_batch(self, batch_id: str) -> dict[str, Any]:
        return self.batch_scheduling_service.get_batch(batch_id)

    def get_task_batch_actual_metrics(self, batch_id: str) -> dict[str, Any]:
        return self.batch_scheduling_service.actual_metrics(batch_id)

    def preview_batch_schedule(self, batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.batch_scheduling_service.preview(batch_id, payload)

    def compare_batch_strategies(self, batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.batch_scheduling_service.compare(batch_id, payload)

    def commit_batch_schedule(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.batch_scheduling_service.commit(batch_id, payload)

    def record_tool_call(
        self,
        *,
        tool_name: str,
        actor: str,
        result_status: str,
        batch_id: str | None = None,
        plan_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        with self.lock:
            self.tool_audit_log.append({
                "request_id": request_id or f"req-{int(time.time() * 1000)}",
                "session_id": session_id,
                "batch_id": batch_id,
                "plan_id": plan_id,
                "actor": actor,
                "tool_name": tool_name,
                "timestamp": round(time.time(), 4),
                "result_status": result_status,
            })
            self.tool_audit_log = self.tool_audit_log[-200:]
            if self.state_store is not None:
                self.state_store.set_control_value("tool_audit_log", list(self.tool_audit_log))

    def parse_requirement(
        self,
        message: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.requirement_dialogue.parse_requirement(message, overrides=overrides)

    def start_requirement_session(
        self,
        message: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.requirement_dialogue.start_requirement_session(message, overrides=overrides)

    def continue_requirement_session(
        self,
        session_id: str,
        message: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.requirement_dialogue.continue_requirement_session(session_id, message, overrides=overrides)

    def get_requirement_session(self, session_id: str) -> dict[str, Any]:
        return self.requirement_dialogue.get_requirement_session(session_id)

    def _requirement_session_payload(self, session: RequirementSession) -> dict[str, Any]:
        return self.requirement_dialogue.requirement_session_payload(session)

    def draft_policy_from_session(
        self,
        session_id: str,
        *,
        execution_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.policy_workflow.draft_policy_from_session(session_id, execution_payload=execution_payload)

    def compare_policy_options_from_session(
        self,
        session_id: str,
        *,
        execution_payload: dict[str, Any] | None = None,
        option_profiles: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.policy_workflow.compare_policy_options_from_session(
            session_id,
            execution_payload=execution_payload,
            option_profiles=option_profiles,
        )

    def draft_policy(
        self,
        requirement_payload: dict[str, Any],
        *,
        execution_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.policy_workflow.draft_policy(requirement_payload, execution_payload=execution_payload)

    def compare_policy_options(
        self,
        requirement_payload: dict[str, Any],
        *,
        execution_payload: dict[str, Any] | None = None,
        option_profiles: list[str] | None = None,
        requirement_session: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.policy_workflow.compare_policy_options(
            requirement_payload,
            execution_payload=execution_payload,
            option_profiles=option_profiles,
            requirement_session=requirement_session,
        )

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        return self.policy_workflow.get_policy(policy_id)

    def simulate_policy(self, policy_id: str) -> dict[str, Any]:
        return self.policy_workflow.simulate_policy(policy_id)

    def commit_policy(self, policy_id: str) -> dict[str, Any]:
        return self.policy_workflow.commit_policy(policy_id)

    def update_policy_weights(
        self,
        weights: dict[str, Any],
        *,
        group_weights: dict[str, Any] | None = None,
        reason: str = "用户手动提交多维策略权重。",
    ) -> dict[str, Any]:
        with self.lock:
            submitted = {str(key): float(value) for key, value in dict(weights or {}).items()}
            if not submitted and group_weights is None:
                raise ValueError("weights or group_weights are required")
            normalized = normalize_weights(submitted) if submitted else self.policy_state.current_weights()
            self.policy_state.update(
                tick=self.current_tick(),
                new_weights=normalized,
                new_group_weights=(
                    {str(key): float(value) for key, value in dict(group_weights).items()}
                    if group_weights is not None
                    else None
                ),
                reasons=[reason],
                affected_records=0,
                metrics={},
            )
            if self.state_store is not None:
                latest_adjustment = self.policy_state.adjustment_history[-1]
                self.state_store.append_policy_adjustment(latest_adjustment.to_dict())
                self.state_store.set_control_value("policy_weights", self.policy_state.current_weights())
                self.state_store.set_control_value("policy_group_weights", self.policy_state.current_group_weights())
            return {
                "status": "updated",
                "policy_weights": {key: round(value, 4) for key, value in self.policy_state.current_weights().items()},
                "policy_group_weights": {key: round(value, 4) for key, value in self.policy_state.current_group_weights().items()},
                "adjustment": self.policy_state.adjustment_history[-1].to_dict(),
            }

    def parse_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        return self.policy_workflow.parse_feedback(feedback_payload)

    def record_user_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        return self.policy_workflow.record_user_feedback(feedback_payload)

    def optimize_policy_from_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        return self.policy_workflow.optimize_policy_from_feedback(feedback_payload)

    def record_heartbeat(
        self,
        node_id: str,
        *,
        health_score: float | None = None,
        online: bool | None = None,
        reliability_score: float | None = None,
        cost_per_tick: float | None = None,
        region: str | None = None,
        location: str | None = None,
        service_region: str | None = None,
        labels: set[str] | None = None,
        performance_factors: dict[str, float] | None = None,
        network_paths: dict[str, dict[str, float]] | None = None,
        current_power_w: float | None = None,
        energy_kwh_delta: float | None = None,
        operational_carbon_g_delta: float | None = None,
        carbon_intensity_g_per_kwh: float | None = None,
        carbon_signal_timestamp: float | None = None,
        runtime_telemetry: dict[str, float] | None = None,
        telemetry_source: str | None = None,
        simulation_tick: float | None = None,
    ) -> dict[str, Any]:
        return self.node_registry.record_heartbeat(
            node_id,
            health_score=health_score,
            online=online,
            reliability_score=reliability_score,
            cost_per_tick=cost_per_tick,
            region=region,
            location=location,
            service_region=service_region,
            labels=labels,
            performance_factors=performance_factors,
            network_paths=network_paths,
            current_power_w=current_power_w,
            energy_kwh_delta=energy_kwh_delta,
            operational_carbon_g_delta=operational_carbon_g_delta,
            carbon_intensity_g_per_kwh=carbon_intensity_g_per_kwh,
            carbon_signal_timestamp=carbon_signal_timestamp,
            runtime_telemetry=runtime_telemetry,
            telemetry_source=telemetry_source,
            simulation_tick=simulation_tick,
        )

    def request_lease(self, node_id: str) -> dict[str, Any] | None:
        return self.task_lease_service.request_lease(node_id)

    def acknowledge_lease(self, *, node_id: str, task_id: str, lease_id: str) -> dict[str, Any]:
        return self.task_lease_service.acknowledge_lease(
            node_id=node_id,
            task_id=task_id,
            lease_id=lease_id,
        )

    def report_task_progress(
        self,
        *,
        node_id: str,
        task_id: str,
        stage: str,
        status: str = "running",
        progress: float | None = None,
        message: str | None = None,
        metrics: dict[str, Any] | None = None,
        lease_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an in-flight task lifecycle update from a real or simulated agent."""
        with self.lock:
            self._expire_stale_nodes()
            lease = self.leases.get(task_id)
            if lease is None:
                raise ValueError(f"Task {task_id} does not have an active lease.")
            if lease.node_id != node_id:
                raise ValueError(f"Task {task_id} is leased to {lease.node_id}, not {node_id}.")
            if lease_id is not None and lease.lease_id != lease_id:
                raise ValueError("Lease identity does not match the active task lease.")
            self.task_lease_service.renew_lease(lease)
            tick = self.current_tick()
            payload = {
                "task_id": task_id,
                "node_id": node_id,
                "stage": str(stage),
                "status": str(status),
                "progress": round(clamp(float(progress if progress is not None else 0.0)), 4),
                "message": message or "",
                "metrics": dict(metrics or {}),
                "tick": tick,
                "updated_at": round(time.time(), 3),
            }
            self.task_progress[task_id] = payload
            self.progress_events.append(payload)
            if len(self.progress_events) > 64:
                self.progress_events = self.progress_events[-64:]
            node = self.nodes.get(node_id)
            if node is not None:
                node.telemetry_tick = tick
                self.last_heartbeat_at[node_id] = time.monotonic()
                self.last_heartbeat_epoch[node_id] = time.time()
                self._persist_node(node)
            return payload

    def report_task_result(
        self,
        *,
        node_id: str,
        task_id: str,
        success: bool,
        duration_seconds: float,
        stdout: str = "",
        stderr: str = "",
        failure_reason: str | None = None,
        returncode: int | None = None,
        cost: float | None = None,
        metadata: dict[str, Any] | None = None,
        lease_id: str | None = None,
        result_id: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            self._expire_stale_nodes()
            if result_id and result_id in self.task_result_receipts:
                receipt = self.task_result_receipts[result_id]
                if receipt.get("task_id") != task_id or receipt.get("node_id") != node_id:
                    raise ValueError("Result identity belongs to a different task or node.")
                if lease_id is not None and receipt.get("lease_id") != lease_id:
                    raise ValueError("Result identity belongs to a different lease.")
                return {**receipt, "idempotent_replay": True}
            lease = self.leases.get(task_id)
            if lease is None:
                previous = self.latest_task_result_receipts.get(task_id)
                if previous is not None and previous.get("node_id") == node_id and (lease_id is None or previous.get("lease_id") == lease_id):
                    return {**previous, "idempotent_replay": True}
                raise ValueError(f"Task {task_id} does not have an active lease.")
            if lease.node_id != node_id:
                raise ValueError(f"Task {task_id} is leased to {lease.node_id}, not {node_id}.")
            if lease_id is not None and lease.lease_id != lease_id:
                raise ValueError("Lease identity does not match the active task lease.")
            if node_id not in self.nodes:
                raise ValueError(f"Unknown node {node_id}.")
            self.leases.pop(task_id)

            tick = self.current_tick()
            node = self.nodes[node_id]
            node.running_tasks.pop(task_id, None)
            task = self.tasks[task_id]

            actual_duration = max(1, int(ceil(duration_seconds)))
            actual_cost = cost if cost is not None else (actual_duration * node.cost_per_tick)
            within_budget = None if task.budget is None else actual_cost <= task.budget
            deadline_tick = task.effective_deadline_tick()
            sla_met = deadline_tick is None or tick <= deadline_tick
            result_metadata = dict(metadata or {})
            predicted_carbon = node.predict_operational_carbon(task, actual_duration, tick)
            energy_kwh = float(result_metadata.get("energy_kwh", predicted_carbon.get("facility_energy_kwh", 0.0)))
            compute_carbon_g = float(result_metadata.get("compute_carbon_g", predicted_carbon.get("compute_carbon_g", 0.0)))
            network_carbon_g = float(result_metadata.get("network_carbon_g", predicted_carbon.get("network_carbon_g", 0.0)))
            operational_carbon_g = float(result_metadata.get("operational_carbon_g", compute_carbon_g + network_carbon_g))
            record = ExecutionRecord(
                task_id=task.task_id,
                task_type=task.task_type,
                node_id=node_id,
                start_tick=lease.issued_tick,
                end_tick=tick,
                predicted_duration=max(1, lease.predicted_finish_tick - lease.issued_tick),
                actual_duration=actual_duration,
                success=success,
                cost=actual_cost,
                sla_met=sla_met,
                within_budget=within_budget,
                retry_count=max(0, task.attempts - 1),
                failure_reason=failure_reason or (None if success else f"returncode_{returncode or -1}"),
                stdout_excerpt=_truncate(stdout),
                stderr_excerpt=_truncate(stderr),
                network_delay_ticks=int(round(lease.decision.network_snapshot.get("transfer_ticks", 0.0))),
                network_risk=float(lease.decision.network_snapshot.get("uncertainty", 0.0)),
                effective_bandwidth_mbps=float(
                    lease.decision.network_snapshot.get("guaranteed_bandwidth_mbps", 0.0)
                ),
                delivery_probability=float(lease.decision.network_snapshot.get("delivery_probability", 1.0)),
                sla_reason=self._sla_reason(
                    task=task,
                    tick=tick,
                    cost=actual_cost,
                    sla_met=sla_met,
                    within_budget=within_budget,
                ),
                metadata=result_metadata,
                energy_kwh=energy_kwh,
                compute_carbon_g=compute_carbon_g,
                network_carbon_g=network_carbon_g,
                operational_carbon_g=operational_carbon_g,
                carbon_scope=str(result_metadata.get("carbon_scope", "operational_only")),
                batch_id=task.batch_id,
                queue_wait_seconds=max(0.0, float(result_metadata.get("queue_wait_seconds", 0.0))),
                jct_seconds=max(0.0, float(result_metadata.get("jct_seconds", duration_seconds))),
                cpu_utilization=clamp(float(result_metadata.get("cpu_utilization", 0.0))),
                memory_utilization=clamp(float(result_metadata.get("memory_utilization", 0.0))),
                bandwidth_utilization=clamp(float(result_metadata.get("bandwidth_utilization", 0.0))),
                storage_utilization=clamp(float(result_metadata.get("storage_utilization", 0.0))),
            )
            self.execution_history.append(record)
            self.execution_history = self.execution_history[-SQLiteStateStore.MAX_EXECUTION_RECORDS:]
            self.task_progress.pop(task_id, None)
            node.update_after_record(task, record)
            node.task_energy_kwh_total += energy_kwh
            node.task_operational_carbon_g_total += operational_carbon_g
            node.resource_version += 1
            self.resource_snapshot_version += 1

            if success:
                task.status = TaskStatus.SUCCEEDED
            elif task.attempts <= task.max_retries:
                task.status = TaskStatus.PENDING
                self.pending_queue.append(task.task_id)
            else:
                task.status = TaskStatus.FAILED

            if task.batch_id and task.batch_id in self.task_batches:
                batch = self.task_batches[task.batch_id]
                statuses = [self.tasks[item.task_id].status for item in batch.tasks if item.task_id in self.tasks]
                if statuses and all(status == TaskStatus.SUCCEEDED for status in statuses):
                    batch.status = BatchStatus.COMPLETED
                elif statuses and all(status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED} for status in statuses):
                    batch.status = BatchStatus.PARTIAL_FAILED

            if self.state_store is not None:
                self.state_store.delete_lease(task_id)
                self.state_store.append_execution_record(record.to_dict())
            self._persist_task(task)
            self._persist_node(node)

            if len(self.execution_history) % self.policy_update_interval == 0:
                previous_adjustment_count = len(self.policy_state.adjustment_history)
                self.optimizer.update_policy(
                    policy_state=self.policy_state,
                    recent_records=self.execution_history,
                    nodes=self.nodes.values(),
                    tick=tick,
                    context=self._feedback_context(),
                )
                if (
                    self.state_store is not None
                    and len(self.policy_state.adjustment_history) > previous_adjustment_count
                ):
                    latest_adjustment = self.policy_state.adjustment_history[-1]
                    self.state_store.append_policy_adjustment(latest_adjustment.to_dict())
                    self.state_store.set_control_value("policy_weights", self.policy_state.current_weights())
                    self.state_store.set_control_value(
                        "policy_group_weights", self.policy_state.current_group_weights()
                    )
            receipt = {
                **record.to_dict(),
                "lease_id": lease.lease_id,
                "result_id": result_id or f"result-{lease.lease_id}",
                "idempotent_replay": False,
            }
            self.task_result_receipts[receipt["result_id"]] = receipt
            self.latest_task_result_receipts[task_id] = receipt
            if len(self.task_result_receipts) > SQLiteStateStore.MAX_EXECUTION_RECORDS:
                oldest = next(iter(self.task_result_receipts))
                self.task_result_receipts.pop(oldest, None)
            if self.state_store is not None:
                self.state_store.set_control_value("task_result_receipts", list(self.task_result_receipts.values()))
            return receipt

    def cancel_task_run(self, *, task_id: str, requeue: bool = False) -> dict[str, Any]:
        with self.lock:
            self._expire_stale_nodes()
            lease = self.leases.pop(task_id, None)
            released_nodes: list[str] = []
            if lease is not None:
                released_nodes.append(lease.node_id)
            for node in self.nodes.values():
                if task_id not in node.running_tasks:
                    continue
                node.running_tasks.pop(task_id, None)
                if node.node_id not in released_nodes:
                    released_nodes.append(node.node_id)
                self._persist_node(node)
            self.task_progress.pop(task_id, None)
            if self.state_store is not None:
                self.state_store.delete_lease(task_id)

            task = self.tasks.get(task_id)
            if task is None and lease is None and not released_nodes:
                raise ValueError(f"Task {task_id} does not have an active lease or resource allocation.")
            if task is not None and task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PENDING if requeue else TaskStatus.FAILED
                if requeue and task_id not in self.pending_queue:
                    self.pending_queue.append(task_id)
                self._persist_task(task)

            return {
                "status": "requeued" if requeue else "cancelled",
                "task_id": task_id,
                "node_id": released_nodes[0] if released_nodes else "",
                "released_nodes": released_nodes,
                "released": True,
            }

    def has_work(self) -> bool:
        with self.lock:
            return bool(self.pending_queue or self.leases)

    @staticmethod
    def _sla_reason(
        *,
        task: Task,
        tick: int,
        cost: float,
        sla_met: bool,
        within_budget: bool | None,
    ) -> str:
        reasons: list[str] = []
        deadline_tick = task.effective_deadline_tick()
        if deadline_tick is not None and tick > deadline_tick:
            elapsed = max(0, tick - task.submit_tick)
            allowed = max(0, deadline_tick - task.submit_tick)
            reasons.append(f"提交后耗时 {elapsed} ticks 超过时限 {allowed} ticks")
        if within_budget is False and task.budget is not None:
            reasons.append(f"成本 {round(cost, 4)} 超过预算 {round(task.budget, 4)}")
        if reasons:
            return "；".join(reasons)
        if sla_met:
            return "SLA 达标"
        return "未满足 SLA 目标"

    def build_report(self) -> dict[str, Any]:
        with self.lock:
            self._expire_stale_nodes()
            succeeded = [record for record in self.execution_history if record.success]
            failed = [record for record in self.execution_history if not record.success]
            avg_wait = self._average_wait_time()
            avg_cost = mean(record.cost for record in self.execution_history) if self.execution_history else 0.0
            avg_network_delay = (
                mean(record.network_delay_ticks for record in self.execution_history)
                if self.execution_history
                else 0.0
            )
            avg_network_risk = (
                mean(record.network_risk for record in self.execution_history)
                if self.execution_history
                else 0.0
            )
            total_energy_kwh = sum(record.energy_kwh for record in self.execution_history)
            total_operational_carbon_g = sum(record.operational_carbon_g for record in self.execution_history)
            actual_jct_seconds = [
                record.jct_seconds for record in self.execution_history if record.jct_seconds > 0.0
            ]
            queue_wait_seconds = [record.queue_wait_seconds for record in self.execution_history]
            cpu_utilization = [record.cpu_utilization for record in self.execution_history]
            memory_utilization = [record.memory_utilization for record in self.execution_history]
            bandwidth_utilization = [record.bandwidth_utilization for record in self.execution_history]
            storage_utilization = [record.storage_utilization for record in self.execution_history]
            batch_makespans: dict[str, float] = {}
            for record in self.execution_history:
                if record.batch_id and record.jct_seconds > 0.0:
                    batch_makespans[record.batch_id] = max(
                        batch_makespans.get(record.batch_id, 0.0),
                        record.jct_seconds,
                    )
            stable_latencies = [
                float(decision.network_snapshot.get("stable_latency_ms", decision.network_snapshot.get("robust_latency_ms", 0.0)))
                for decision in self.decision_log
            ]
            fusion_scores = [
                float(decision.network_snapshot.get("feature_fusion_score", 0.0))
                for decision in self.decision_log
            ]
            deterministic_confidences = [
                float(decision.network_snapshot.get("deterministic_confidence", 0.0))
                for decision in self.decision_log
            ]
            model_predictions = [
                decision.network_snapshot.get("model_prediction", {})
                for decision in self.decision_log
                if decision.network_snapshot.get("model_prediction")
            ]
            latest_model_prediction = model_predictions[-1] if model_predictions else {}
            model_runtime = self.scheduler.model_runtime.describe()
            loaded_models = set(model_runtime.get("loaded_models", []))
            active_model_features = []
            if "lstm" in loaded_models:
                active_model_features.append("lstm_latency_prediction")
            if "gnn" in loaded_models:
                active_model_features.append("graphsage_topology_score")
            reference_weight_sources = self.scheduler.weight_components(
                Task(
                    task_id="__weight_reference__",
                    task_type="batch_cpu",
                    demand=ResourceVector(cpu=1, memory=1, gpu=0, storage=1),
                    estimated_duration=10,
                ),
                self.current_tick(),
            )
            reference_group_weight_sources = self.scheduler.group_weight_components(
                Task(
                    task_id="__group_weight_reference__",
                    task_type="batch_cpu",
                    demand=ResourceVector(cpu=1, memory=1, gpu=0, storage=1),
                    estimated_duration=10,
                ),
                self.current_tick(),
            )
            external_mcp_calls = [
                item for item in self.tool_audit_log if item.get("actor") == "external_mcp"
            ]
            external_mcp_successes = [
                item for item in external_mcp_calls if item.get("result_status") == "success"
            ]
            return {
                "tick": self.current_tick(),
                "generated_at": time.time(),
                "report_version": f"{self.resource_snapshot_version}:{self.current_tick()}",
                "totals": {
                    "tasks": len(self.tasks),
                    "completed_attempts": len(self.execution_history),
                    "succeeded_attempts": len(succeeded),
                    "failed_attempts": len(failed),
                    "completed": len(self.execution_history),
                    "succeeded": len(succeeded),
                    "failed": len(failed),
                    "pending_tasks": len(self.pending_queue),
                    "leased_tasks": len(self.leases),
                    "running_tasks": len(self.leases),
                    "pending": len(self.pending_queue),
                    "running": len(self.leases),
                    "sla_met": sum(1 for record in self.execution_history if record.sla_met),
                    "sla_missed": sum(1 for record in self.execution_history if not record.sla_met),
                },
                "metrics": {
                    "success_rate": round((len(succeeded) / len(self.execution_history)) if self.execution_history else 0.0, 4),
                    "average_wait_ticks": round(avg_wait, 4),
                    "average_cost": round(avg_cost, 4),
                    "average_network_delay_ticks": round(avg_network_delay, 4),
                    "average_network_risk": round(avg_network_risk, 4),
                    "total_energy_kwh": round(total_energy_kwh, 8),
                    "total_operational_carbon_g": round(total_operational_carbon_g, 6),
                    "average_operational_carbon_g_per_task": round(total_operational_carbon_g / len(self.execution_history), 6) if self.execution_history else 0.0,
                    "average_actual_jct_seconds": round(mean(actual_jct_seconds), 6) if actual_jct_seconds else 0.0,
                    "p95_actual_jct_seconds": round(_percentile(actual_jct_seconds, 0.95), 6),
                    "average_queue_wait_seconds": round(mean(queue_wait_seconds), 6) if queue_wait_seconds else 0.0,
                    "p95_queue_wait_seconds": round(_percentile(queue_wait_seconds, 0.95), 6),
                    "actual_makespan_seconds": round(max(actual_jct_seconds), 6) if actual_jct_seconds else 0.0,
                    "average_cpu_utilization": round(mean(cpu_utilization), 6) if cpu_utilization else 0.0,
                    "average_memory_utilization": round(mean(memory_utilization), 6) if memory_utilization else 0.0,
                    "average_bandwidth_utilization": round(mean(bandwidth_utilization), 6) if bandwidth_utilization else 0.0,
                    "average_storage_utilization": round(mean(storage_utilization), 6) if storage_utilization else 0.0,
                    "completed_batch_count": len(batch_makespans),
                    "batch_makespan_seconds": {
                        batch_id: round(value, 6) for batch_id, value in sorted(batch_makespans.items())
                    },
                    "average_stable_latency_ms": round(mean(stable_latencies) if stable_latencies else 0.0, 4),
                    "average_fusion_score": round(mean(fusion_scores) if fusion_scores else 0.0, 4),
                    "average_deterministic_confidence": round(
                        mean(deterministic_confidences) if deterministic_confidences else 0.0,
                        4,
                    ),
                    "sla_rate": round(
                        mean(1.0 if record.sla_met else 0.0 for record in self.execution_history)
                        if self.execution_history
                        else 0.0,
                        4,
                    ),
                },
                "policy_weights": {key: round(value, 4) for key, value in self.policy_state.current_weights().items()},
                "policy_group_weights": {key: round(value, 4) for key, value in self.policy_state.current_group_weights().items()},
                "weight_sources": {
                    **{
                        source: {key: round(value, 4) for key, value in weights.items()}
                        for source, weights in reference_weight_sources.items()
                    },
                    "fusion_coefficients": {"intent": 0.4, "sla": 0.4, "data": 0.2},
                    "data_method": "fixed_critic_reference_profile",
                    "scope": "reference_batch_cpu_task; actual SLA/final weights are recomputed per task",
                },
                "group_weight_sources": {
                    **{
                        source: {key: round(value, 4) for key, value in weights.items()}
                        for source, weights in reference_group_weight_sources.items()
                    },
                    "fusion_coefficients": {"intent": 0.4, "sla": 0.4, "data": 0.2},
                    "hierarchy_version": "five-groups-v1",
                    "security_policy": "hard constraints plus non-compensable residual risk penalty",
                },
                "batch_scheduling": self.batch_scheduling_service.report(),
                "toolchain_runtime": {
                    "external_mcp_last_call": external_mcp_calls[-1] if external_mcp_calls else None,
                    "external_mcp_last_success": external_mcp_successes[-1] if external_mcp_successes else None,
                    "external_mcp_call_count": len(external_mcp_calls),
                    "external_mcp_success_count": len(external_mcp_successes),
                    "recent_calls": list(self.tool_audit_log[-20:]),
                },
                "resource_snapshot_version": self.resource_snapshot_version,
                "policy_history": [entry.to_dict() for entry in self.policy_state.adjustment_history],
                "nodes": [
                    self._node_report_payload(node)
                    for node in self.nodes.values()
                ],
                "physical_topology": None if self.physical_topology is None else self.physical_topology.to_dict(),
                "recent_decisions": [decision.to_dict() for decision in self.decision_log[-8:]],
                "active_runs": self._active_runs_payload(),
                "recent_progress_events": list(self.progress_events[-16:]),
                "recent_records": [record.to_dict() for record in self.execution_history[-8:]],
                "execution_records": [record.to_dict() for record in self.execution_history],
                "task_statuses": {
                    task_id: task.status.value for task_id, task in sorted(self.tasks.items(), key=lambda item: item[0])
                },
                "pending_task_queue": [
                    self.tasks[task_id].to_dict()
                    for task_id in self.pending_queue
                    if task_id in self.tasks and self.tasks[task_id].status == TaskStatus.PENDING
                ],
                "policies": [policy.to_dict() for policy in list(self.policies.values())[-8:]],
                "user_feedback": [feedback.to_dict() for feedback in self.user_feedback[-8:]],
                "model_runtime": {
                    **model_runtime,
                    "latest_prediction": latest_model_prediction,
                },
                "algorithm_profile": {
                    "name": "deterministic_compute_network_policy_engine",
                    "features": [
                        "resource_fit",
                        "deadline_completion",
                        "cost",
                        "reliability",
                        "load_balance",
                        "locality",
                        "jitter",
                        "node_load",
                        "bandwidth_utilization",
                        "security_policy",
                        "operational_carbon",
                        "batch_joint_allocation",
                        "pareto_tchebycheff",
                        "future_fit_fragmentation",
                        "atomic_snapshot_reservation",
                        "hierarchical_objective_fusion",
                        "plan_level_delta_search",
                        *active_model_features,
                    ],
                    "model_status": model_runtime["status"],
                    "objective": "以确定性调度评分为主，按实际加载的模型状态增强时延和拓扑稳定性预测。",
                    "paper_adaptations": [
                        "多特征融合",
                        "时延确定化预测",
                        "闭环反馈调权",
                        "安全约束评分",
                    ],
                },
                "data_gaps": {
                    "latency_history": "当前 runtime 使用链路画像合成序列；模型是否参与预测以 model_runtime.status 为准。",
                    "lstm_latency_prediction": (
                        "LSTM 模型已参与 predicted_latency_ms，作为 EWMA 的增强预测器。"
                        if "lstm" in loaded_models
                        else "LSTM 模型未加载，predicted_latency_ms 使用 EWMA fallback。"
                    ),
                    "bandwidth_utilization": "当前由带宽波动与丢包估计，后续需要接入交换机端口或云监控链路利用率。",
                    "security_policy": "安全维度已进入策略对象和调度评分；企业级身份、审计和密钥管理仍需后续接入。",
                    "gnn_topology_embedding": (
                        "GraphSAGE 模型已参与 gnn_topology 评分；当前已按物理链路传播时延加权聚合仿真算力邻居特征。"
                        if "gnn" in loaded_models and self.physical_topology is not None
                        else "GraphSAGE 模型已参与 gnn_topology 评分；未注册物理拓扑时邻居特征使用自嵌入兜底。"
                        if "gnn" in loaded_models
                        else "GraphSAGE 模型未加载，gnn_topology 使用中性兜底分。"
                    ),
                },
            }


    def _node_report_payload(self, node: Node) -> dict[str, Any]:
        heartbeat_age = max(
            0.0,
            time.monotonic() - self.last_heartbeat_at.get(node.node_id, self.started_at),
        )
        payload = {
            **node.to_dict(),
            "last_heartbeat_age": round(heartbeat_age, 3),
        }
        runtime_utilization: dict[str, float | None] = {
            "cpu": node.runtime_telemetry.get("cpu"),
            "memory": node.runtime_telemetry.get("memory"),
            "gpu": node.runtime_telemetry.get("gpu"),
            "storage": node.runtime_telemetry.get("storage"),
            "bandwidth": node.runtime_telemetry.get("bandwidth"),
        }
        active_task_ids: list[str] = []
        active_stages: list[str] = []
        for progress in self.task_progress.values():
            if progress.get("node_id") != node.node_id:
                continue
            task_id = str(progress.get("task_id") or "")
            if task_id and task_id not in self.leases:
                continue
            active_task_ids.append(task_id)
            active_stages.append(str(progress.get("stage") or "running"))
            util = dict(dict(progress.get("metrics") or {}).get("simulated_utilization") or {})
            for key in runtime_utilization:
                try:
                    observed = util.get(key)
                    if observed is not None:
                        current = runtime_utilization[key]
                        runtime_utilization[key] = max(0.0 if current is None else current, float(observed))
                except (TypeError, ValueError):
                    pass
        payload["runtime_utilization"] = {
            key: None if value is None else round(clamp(value), 4)
            for key, value in runtime_utilization.items()
        }
        payload["runtime_telemetry_available"] = any(value is not None for value in runtime_utilization.values())
        payload["active_task_ids"] = active_task_ids
        payload["active_stages"] = active_stages
        telemetry_source = str(node.telemetry_source or "").strip().lower()
        telemetry_is_current = node.online and heartbeat_age <= self.heartbeat_timeout_seconds
        if telemetry_source in {"cloudsim", "cloudsimplus", "simulator"}:
            load_source = "simulated_telemetry"
            load_source_label = "CloudSim Plus 模拟遥测"
        elif telemetry_source:
            load_source = "live_telemetry"
            load_source_label = "节点实时遥测"
        elif payload["runtime_telemetry_available"]:
            load_source = "task_progress_estimate"
            load_source_label = "任务进度估算"
        elif node.running_tasks or active_task_ids:
            load_source = "allocation_estimate"
            load_source_label = "任务分配估算"
        else:
            load_source = "unavailable"
            load_source_label = "暂无负载遥测"
        payload["resource_load_source"] = load_source
        payload["resource_load_source_label"] = load_source_label
        payload["telemetry_freshness"] = (
            "current" if telemetry_is_current and load_source != "unavailable" else
            "stale" if load_source != "unavailable" else
            "unavailable"
        )

        carbon_version = str(node.carbon_profile.source_version or "").strip().lower()
        if node.carbon_signal_timestamp is not None:
            carbon_source = "simulated_signal" if load_source == "simulated_telemetry" else "live_signal"
            carbon_source_label = "CloudSim Plus 模拟碳信号" if carbon_source == "simulated_signal" else "节点实时碳信号"
            carbon_freshness = "current" if telemetry_is_current else "stale"
        elif any(marker in carbon_version for marker in ("synthetic", "simulated", "trace")):
            carbon_source = "simulated_profile"
            carbon_source_label = "模拟碳强度曲线"
            carbon_freshness = "profile"
        else:
            carbon_source = "configured_profile"
            carbon_source_label = "配置碳强度"
            carbon_freshness = "profile"
        payload["carbon_data_source"] = carbon_source
        payload["carbon_data_source_label"] = carbon_source_label
        payload["carbon_data_freshness"] = carbon_freshness
        return payload

    def current_tick(self) -> int:
        return int(max(0.0, ceil(time.monotonic() - self.started_at)))

    def _active_runs_payload(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for task_id, lease in sorted(self.leases.items(), key=lambda item: item[0]):
            task = self.tasks.get(task_id)
            progress = dict(self.task_progress.get(task_id, {}))
            if not progress:
                progress = {
                    "task_id": task_id,
                    "node_id": lease.node_id,
                    "stage": "leased",
                    "status": "running",
                    "progress": 0.0,
                    "message": "lease acquired; waiting for agent progress",
                    "metrics": {},
                    "tick": self.current_tick(),
                }
            progress["task"] = None if task is None else task.to_dict()
            progress["lease"] = {
                "issued_tick": lease.issued_tick,
                "predicted_finish_tick": lease.predicted_finish_tick,
                "predicted_cost": round(lease.predicted_cost, 4),
            }
            runs.append(progress)
        return runs

    def _policy_or_raise(self, policy_id: str) -> ComputeNetworkPolicy:
        return self.policy_workflow.policy_or_raise(policy_id)

    def _session_or_raise(self, session_id: str) -> RequirementSession:
        return self.requirement_dialogue.session_or_raise(session_id)

    def _normalize_feedback_payload(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        return self.policy_workflow.normalize_feedback_payload(feedback_payload)

    def _normalize_option_profiles(self, option_profiles: list[str] | None) -> list[str]:
        return self.policy_workflow.normalize_option_profiles(option_profiles)

    def _requirement_for_option_profile(self, requirement: UserRequirement, profile: str) -> UserRequirement:
        return self.policy_workflow.requirement_for_option_profile(requirement, profile)

    def _policy_option_payload(
        self,
        *,
        label: str,
        profile: str,
        policy: dict[str, Any],
        simulation: dict[str, Any],
    ) -> dict[str, Any]:
        return self.policy_workflow.policy_option_payload(
            label=label,
            profile=profile,
            policy=policy,
            simulation=simulation,
        )

    def _recommended_policy_option(self, options: list[dict[str, Any]]) -> dict[str, Any] | None:
        return self.policy_workflow.recommended_policy_option(options)

    def _policy_options_explanation(self, options: list[dict[str, Any]], recommended: dict[str, Any] | None) -> str:
        return self.policy_workflow.policy_options_explanation(options, recommended)

    def _new_session_id(self) -> str:
        return f"sess_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}"

    def _expire_stale_nodes(self) -> None:
        now = time.monotonic()
        stale_node_ids: set[str] = set()
        for node_id, node in self.nodes.items():
            last_seen = self.last_heartbeat_at.get(node_id, self.started_at)
            if now - last_seen > self.heartbeat_timeout_seconds:
                stale_node_ids.add(node_id)
                if node.online:
                    node.online = False
                    self._persist_node(node)
        if stale_node_ids:
            self._recover_leases_for_stale_nodes(stale_node_ids)
        self.task_lease_service.expire_stale_leases()

    def _recover_leases_for_stale_nodes(self, stale_node_ids: set[str]) -> None:
        """Release leases held by offline agents so tasks can be retried elsewhere."""
        for task_id, lease in list(self.leases.items()):
            if lease.node_id not in stale_node_ids:
                continue
            self.leases.pop(task_id, None)
            node = self.nodes.get(lease.node_id)
            if node is not None:
                node.running_tasks.pop(task_id, None)
                self._persist_node(node)
            if self.state_store is not None:
                self.state_store.delete_lease(task_id)

            task = self.tasks.get(task_id)
            if task is None or task.status != TaskStatus.RUNNING:
                continue
            if task.attempts <= task.max_retries:
                task.status = TaskStatus.PENDING
                if task_id not in self.pending_queue:
                    self.pending_queue.append(task_id)
            else:
                task.status = TaskStatus.FAILED
            self._persist_task(task)

    def _feedback_context(self) -> dict[str, float]:
        gpu_pending = [
            self.tasks[task_id]
            for task_id in self.pending_queue
            if self.tasks[task_id].demand.gpu > 0
        ]
        locality_records = [record for record in self.execution_history if self.tasks[record.task_id].data_region]
        locality_miss_rate = 0.0
        if locality_records:
            locality_miss_rate = mean(
                1.0
                if self.tasks[record.task_id].data_region != self.nodes[record.node_id].region
                else 0.0
                for record in locality_records[-12:]
            )
        recent_records = self.execution_history[-12:]
        carbon_budget_records = [
            (record, self.tasks.get(record.task_id))
            for record in recent_records
            if self.tasks.get(record.task_id) is not None
            and self.tasks[record.task_id].carbon_budget_g is not None
        ]
        return {
            "gpu_wait_ratio": (len(gpu_pending) / len(self.pending_queue)) if self.pending_queue else 0.0,
            "locality_miss_rate": locality_miss_rate,
            "network_instability": (
                mean(record.network_risk for record in recent_records)
                if recent_records
                else 0.0
            ),
            "network_pressure": (
                mean(
                    min(1.0, record.network_delay_ticks / max(1, record.actual_duration))
                    for record in recent_records
                )
                if recent_records
                else 0.0
            ),
            "carbon_budget_violation_rate": (
                mean(
                    1.0
                    if record.operational_carbon_g > float(task.carbon_budget_g)
                    else 0.0
                    for record, task in carbon_budget_records
                )
                if carbon_budget_records
                else 0.0
            ),
        }

    def _average_wait_time(self) -> float:
        wait_times = []
        first_start: dict[str, int] = {}
        for record in self.execution_history:
            if record.task_id not in first_start:
                first_start[record.task_id] = record.start_tick
        for task_id, start_tick in first_start.items():
            wait_times.append(start_tick - self.tasks[task_id].submit_tick)
        return mean(wait_times) if wait_times else 0.0

    def _task_sort_key(self, task: Task) -> tuple[float, int, int, str]:
        return self.task_lease_service.task_sort_key(task)

    def _activate_task_lease(
        self,
        *,
        task: Task,
        node: Node,
        decision: SchedulingDecision,
        tick: int,
        remove_from_pending: bool,
    ) -> TaskLease:
        return self.task_lease_service.activate_task_lease(
            task=task,
            node=node,
            decision=decision,
            tick=tick,
            remove_from_pending=remove_from_pending,
        )

    def _persist_node(self, node: Node) -> None:
        if self.state_store is None:
            return
        last_seen_epoch = self.last_heartbeat_epoch.get(node.node_id, time.time())
        self.state_store.save_node(node.to_dict(), last_seen_epoch)

    def _persist_task(self, task: Task) -> None:
        if self.state_store is None:
            return
        self.state_store.save_task(task.to_dict())

    def _restore_from_store(self) -> None:
        restore_control_plane(self)
