from __future__ import annotations

import time
from typing import Any

from ..execution.executors import ExecutorRegistry
from ..domain import Node
from ..scenarios import task_from_dict


class LightweightNodeAgent:
    def __init__(
        self,
        node: Node,
        control_plane_client: Any,
        *,
        executors: ExecutorRegistry | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.node = node
        self.client = control_plane_client
        self.executors = executors or ExecutorRegistry()
        self.poll_interval_seconds = poll_interval_seconds
        self.completed_task_ids: list[str] = []

    def register(self) -> dict[str, Any]:
        return self.client.register_node(self.node)

    def heartbeat(self) -> dict[str, Any]:
        return self.client.heartbeat(
            self.node.node_id,
            health_score=self.node.health_score,
            online=self.node.online,
            cost_per_tick=self.node.cost_per_tick,
            region=self.node.region,
            labels=sorted(self.node.labels),
            performance_factors=dict(self.node.performance_factors),
        )

    def run_once(self) -> dict[str, Any] | None:
        self.heartbeat()
        lease = self.client.request_lease(self.node.node_id)
        if lease is None:
            return None

        task = task_from_dict(lease["task"])
        result = self.executors.run(task.execution, task=task, node=self.node, lease=lease)
        record = self.client.report_result(self.node.node_id, task.task_id, result)
        self.completed_task_ids.append(task.task_id)
        return {
            "node_id": self.node.node_id,
            "task_id": task.task_id,
            "lease": lease,
            "execution": result.to_dict(),
            "record": record,
        }

    def run_until_idle(self, max_cycles: int = 50, idle_cycles_before_stop: int = 3) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        idle_cycles = 0
        for _ in range(max_cycles):
            outcome = self.run_once()
            if outcome is None:
                idle_cycles += 1
                report = self.client.get_report()
                if report["totals"]["pending_tasks"] == 0 and report["totals"]["leased_tasks"] == 0:
                    if idle_cycles >= idle_cycles_before_stop:
                        break
                if self.poll_interval_seconds > 0:
                    time.sleep(self.poll_interval_seconds)
                continue

            idle_cycles = 0
            results.append(outcome)
            if self.poll_interval_seconds > 0:
                time.sleep(self.poll_interval_seconds)
        return results
