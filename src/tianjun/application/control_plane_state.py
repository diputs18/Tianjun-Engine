from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..domain import (
    BatchSchedulingPlan,
    ExecutionRecord,
    PhysicalTopology,
    PolicyAdjustment,
    ReservationLedger,
    SchedulingDecision,
    TaskBatch,
    TaskStatus,
)
from ..scenarios import node_from_dict, task_from_dict
from ..storage.sqlite_state_store import SQLiteStateStore

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


def restore_control_plane(control: CentralControlPlane) -> None:
    """Restore durable state while deliberately invalidating in-flight leases."""
    if control.state_store is None:
        return
    snapshot = control.state_store.load_state()

    restored_weights = snapshot["control_state"].get("policy_weights")
    if restored_weights:
        control.policy_state.weights = restored_weights
    restored_group_weights = snapshot["control_state"].get("policy_group_weights")
    if restored_group_weights:
        control.policy_state.group_weights = restored_group_weights

    restored_tool_audit_log = snapshot["control_state"].get("tool_audit_log")
    if isinstance(restored_tool_audit_log, list):
        control.tool_audit_log = [
            dict(item) for item in restored_tool_audit_log if isinstance(item, dict)
        ][-200:]

    restored_receipts = snapshot["control_state"].get("task_result_receipts")
    if isinstance(restored_receipts, list):
        for receipt in restored_receipts[-SQLiteStateStore.MAX_EXECUTION_RECORDS:]:
            if not isinstance(receipt, dict):
                continue
            result_id = str(receipt.get("result_id") or "")
            task_id = str(receipt.get("task_id") or "")
            if result_id:
                control.task_result_receipts[result_id] = dict(receipt)
            if task_id:
                control.latest_task_result_receipts[task_id] = dict(receipt)

    restored_topology = snapshot["control_state"].get("physical_topology")
    if restored_topology:
        control.physical_topology = PhysicalTopology.from_dict(restored_topology)
        control.scheduler.set_physical_topology(control.physical_topology)

    control.policy_state.adjustment_history = [
        PolicyAdjustment(
            tick=int(payload["tick"]),
            weights={str(key): float(value) for key, value in payload["weights"].items()},
            group_weights={
                str(key): float(value)
                for key, value in dict(payload.get("group_weights") or {}).items()
            },
            reasons=list(payload["reasons"]),
            affected_records=int(payload.get("affected_records", 0)),
            metrics={
                str(key): float(value)
                for key, value in dict(payload.get("metrics") or {}).items()
            },
        )
        for payload in snapshot["policy_adjustments"]
    ]

    for node_entry in snapshot["nodes"]:
        node = node_from_dict(node_entry["payload"])
        node.running_tasks = {}
        control.nodes[node.node_id] = node
        last_seen_epoch = float(node_entry["last_seen_epoch"])
        heartbeat_age = max(0.0, time.time() - last_seen_epoch)
        control.last_heartbeat_epoch[node.node_id] = last_seen_epoch
        control.last_heartbeat_at[node.node_id] = time.monotonic() - heartbeat_age

    for payload in snapshot["tasks"]:
        task = task_from_dict(payload)
        if task.status in {TaskStatus.RUNNING, TaskStatus.RESERVED, TaskStatus.LEASED}:
            task.status = TaskStatus.PENDING
        control.tasks[task.task_id] = task
        if task.status == TaskStatus.PENDING and task.task_id not in control.pending_queue:
            control.pending_queue.append(task.task_id)

    control.decision_log = [
        SchedulingDecision.from_dict(payload) for payload in snapshot["decisions"]
    ]
    control.execution_history = [
        ExecutionRecord(**payload) for payload in snapshot["execution_records"]
    ]

    for lease_payload in snapshot["leases"]:
        task_id = lease_payload["task_id"]
        if task_id in control.tasks and control.tasks[task_id].status != TaskStatus.SUCCEEDED:
            control.tasks[task_id].status = TaskStatus.PENDING
            if task_id not in control.pending_queue:
                control.pending_queue.append(task_id)
        control.state_store.delete_lease(task_id)

    for payload in snapshot.get("task_batches", []):
        batch_tasks = []
        for task_payload in payload.get("tasks", []):
            task_id = str(task_payload.get("task_id") or "")
            batch_tasks.append(control.tasks.get(task_id) or task_from_dict(task_payload))
        batch = TaskBatch.from_dict(payload, tasks=batch_tasks)
        control.task_batches[batch.batch_id] = batch
        control.batch_idempotency[batch.client_batch_id] = batch.batch_id

    for payload in snapshot.get("batch_plans", []):
        plan = BatchSchedulingPlan.from_dict(payload)
        control.batch_plans[plan.plan_id] = plan

    for payload in snapshot.get("reservation_ledgers", []):
        ledger = ReservationLedger.from_dict(payload)
        control.reservation_ledgers[ledger.plan_id] = ledger

    restored_version = int(snapshot["control_state"].get("resource_snapshot_version", 0))
    control.resource_snapshot_version = max(
        restored_version,
        *(node.resource_version for node in control.nodes.values()),
        0,
    )

    for task in control.tasks.values():
        control._persist_task(task)
    for node in control.nodes.values():
        control._persist_node(node)
