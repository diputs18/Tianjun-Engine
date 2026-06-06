from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane
    from ..domain import Node, SchedulingDecision, Task

from ..domain import RunningTask, TaskStatus


@dataclass(slots=True)
class TaskLease:
    task_id: str
    node_id: str
    issued_tick: int
    predicted_finish_tick: int
    predicted_cost: float
    explanation: str
    task: Task
    decision: SchedulingDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "node_id": self.node_id,
            "issued_tick": self.issued_tick,
            "predicted_finish_tick": self.predicted_finish_tick,
            "predicted_cost": round(self.predicted_cost, 4),
            "explanation": self.explanation,
            "task": self.task.to_dict(),
            "decision": self.decision.to_dict(),
        }

@dataclass(slots=True)
class TaskLeaseService:
    """Boundary for task submission, scheduling, lease issue, and run reporting."""

    control_plane: CentralControlPlane

    @property
    def active_lease_count(self) -> int:
        return len(self.control_plane.leases)

    def submit_task(self, task: Task) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            if task.task_id in control.tasks:
                raise ValueError(f"Task {task.task_id} already exists.")
            task.submit_tick = control.current_tick()
            if task.deadline is not None and task.deadline <= task.submit_tick:
                task.deadline = task.submit_tick + task.deadline
            control.tasks[task.task_id] = task
            control.pending_queue.append(task.task_id)
            control._persist_task(task)
            return task.to_dict()

    def preview_task(self, task: Task) -> dict[str, Any] | None:
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            decision = control.scheduler.select_node(
                task,
                control.nodes.values(),
                current_tick=control.current_tick(),
                topology_nodes=control.nodes.values(),
            )
            return None if decision is None else decision.to_dict()

    def schedule_pending_task(self, task_id: str) -> dict[str, Any]:
        """Assign one already-submitted task to its best eligible node."""
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            task = control.tasks.get(task_id)
            if task is None:
                raise ValueError(f"Unknown task {task_id}.")
            if task.status == TaskStatus.RUNNING and task_id in control.leases:
                lease = control.leases[task_id]
                return {
                    "status": "already_scheduled",
                    "task_id": task_id,
                    "node_id": lease.node_id,
                    "total_score": lease.decision.total_score,
                    "preview_decision": lease.decision.to_dict(),
                    "lease": lease.to_dict(),
                }
            if task.status != TaskStatus.PENDING:
                raise ValueError(f"Task {task_id} is {task.status.value}, not pending.")

            tick = control.current_tick()
            decision = control.scheduler.select_node(
                task,
                control.nodes.values(),
                current_tick=tick,
                topology_nodes=control.nodes.values(),
            )
            if decision is None:
                return {
                    "status": "rejected",
                    "task_id": task_id,
                    "node_id": "",
                    "total_score": 0.0,
                    "preview_decision": None,
                    "lease": None,
                    "reason": "no feasible online node",
                    "task": task.to_dict(),
                }
            node = control.nodes[decision.node_id]
            lease = self.activate_task_lease(
                task=task,
                node=node,
                decision=decision,
                tick=tick,
                remove_from_pending=True,
            )
            return {
                "status": "committed",
                "task_id": task_id,
                "node_id": lease.node_id,
                "total_score": decision.total_score,
                "preview_decision": decision.to_dict(),
                "lease": lease.to_dict(),
            }

    def request_lease(self, node_id: str) -> dict[str, Any] | None:
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            node = control.nodes.get(node_id)
            if node is None or not node.online:
                return None

            tick = control.current_tick()
            ordered_task_ids = sorted(
                control.pending_queue,
                key=lambda task_id: self.task_sort_key(control.tasks[task_id]),
            )
            for task_id in ordered_task_ids:
                task = control.tasks[task_id]
                if task.status != TaskStatus.PENDING:
                    continue
                if task.target_node_id and task.target_node_id != node_id:
                    continue
                candidates = [control.nodes[task.target_node_id]] if task.target_node_id and task.target_node_id in control.nodes else list(control.nodes.values())
                decision = control.scheduler.select_node(
                    task,
                    candidates,
                    current_tick=tick,
                    topology_nodes=control.nodes.values(),
                )
                if decision is None or decision.node_id != node_id:
                    continue

                lease = self.activate_task_lease(
                    task=task,
                    node=node,
                    decision=decision,
                    tick=tick,
                    remove_from_pending=True,
                )
                return lease.to_dict()
            return None

    @staticmethod
    def task_sort_key(task: Task) -> tuple[float, int, int, str]:
        deadline_sort = task.deadline if task.deadline is not None else 10**9
        return (-task.priority, deadline_sort, task.submit_tick, task.task_id)

    def activate_task_lease(
        self,
        *,
        task: Task,
        node: Node,
        decision: SchedulingDecision,
        tick: int,
        remove_from_pending: bool,
    ) -> TaskLease:
        control = self.control_plane
        predicted_duration = max(1, decision.predicted_finish_tick - tick)
        network_delay_ticks = int(round(decision.network_snapshot.get("transfer_ticks", 0.0)))
        node.running_tasks[task.task_id] = RunningTask(
            task_id=task.task_id,
            node_id=node.node_id,
            allocation=task.demand,
            start_tick=tick,
            predicted_duration=predicted_duration,
            actual_duration=0,
            finish_tick=decision.predicted_finish_tick,
            success_probability=1.0,
            network_delay_ticks=network_delay_ticks,
            network_risk=float(decision.network_snapshot.get("uncertainty", 0.0)),
            effective_bandwidth_mbps=float(
                decision.network_snapshot.get("guaranteed_bandwidth_mbps", 0.0)
            ),
            delivery_probability=float(decision.network_snapshot.get("delivery_probability", 1.0)),
        )
        task.status = TaskStatus.RUNNING
        task.last_scheduled_node = node.node_id
        task.attempts += 1
        if remove_from_pending and task.task_id in control.pending_queue:
            control.pending_queue.remove(task.task_id)
        control.decision_log.append(decision)

        lease = TaskLease(
            task_id=task.task_id,
            node_id=node.node_id,
            issued_tick=tick,
            predicted_finish_tick=decision.predicted_finish_tick,
            predicted_cost=decision.predicted_cost,
            explanation=decision.explanation,
            task=task,
            decision=decision,
        )
        control.leases[task.task_id] = lease
        control._persist_task(task)
        control._persist_node(node)
        if control.state_store is not None:
            control.state_store.append_decision(decision.to_dict())
            control.state_store.save_lease(lease.to_dict())
        return lease
