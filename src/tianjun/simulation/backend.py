from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..domain import Node, Task
from ..execution.executors import ExecutionResult, ExecutorRegistry
from ..inventory import load_inventory_config, nodes_from_inventory
from ..node_agent.clients import HttpControlPlaneClient
from ..scenarios import task_from_dict

LogFn = Callable[[str], None]


@dataclass(slots=True)
class SimulatedRun:
    """A leased task that is being advanced by a simulated node runtime."""

    node: Node
    task: Task
    lease: dict[str, Any]
    result: ExecutionResult
    stages: list[dict[str, Any]]
    stage_index: int = 0
    stage_elapsed: float = 0.0
    elapsed: float = 0.0
    reported_start: bool = False
    started_at: float = field(default_factory=time.monotonic)

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @property
    def node_id(self) -> str:
        return self.node.node_id

    def current_stage(self) -> dict[str, Any]:
        if self.stage_index >= len(self.stages):
            return {"stage": "finalizing", "seconds": 0.0, "status": "ok"}
        return self.stages[self.stage_index]

    def stage_name(self) -> str:
        return str(self.current_stage().get("stage", "running"))

    def total_duration(self) -> float:
        return max(0.1, sum(float(stage.get("seconds", 0.0)) for stage in self.stages))

    def progress(self) -> float:
        return min(1.0, max(0.0, self.elapsed / self.total_duration()))

    def advance(self, delta_seconds: float) -> tuple[bool, bool]:
        """Advance run by scaled time. Returns (stage_changed, finished)."""
        if self.stage_index >= len(self.stages):
            return False, True
        self.elapsed += max(0.0, delta_seconds)
        self.stage_elapsed += max(0.0, delta_seconds)
        changed = False
        while self.stage_index < len(self.stages):
            duration = max(0.0, float(self.current_stage().get("seconds", 0.0)))
            if duration > 0 and self.stage_elapsed < duration:
                break
            self.stage_elapsed = max(0.0, self.stage_elapsed - duration)
            self.stage_index += 1
            changed = True
            if self.stage_index >= len(self.stages):
                return changed, True
            if duration > 0:
                break
        return changed, self.stage_index >= len(self.stages)

    def progress_metrics(self) -> dict[str, Any]:
        sim = self.result.metadata.get("simulation", {}) if self.result.metadata else {}
        metrics = dict(sim.get("metrics", {}))
        metrics.update({
            "stage": self.stage_name(),
            "elapsed_seconds": round(self.elapsed, 3),
            "planned_seconds": round(self.total_duration(), 3),
        })
        # These are live telemetry hints for the Dashboard. They are demand-aware:
        # a CPU-only task must not show synthetic GPU pressure just because the
        # workload type is "inference".
        stage = self.stage_name()
        utilization = {
            "lease_acquired": {"cpu": 0.05, "memory": 0.02, "gpu": 0.0, "storage": 0.0},
            "provisioning": {"cpu": 0.20, "memory": 0.10, "gpu": 0.0, "storage": 0.15},
            "image_pulling": {"cpu": 0.25, "memory": 0.15, "gpu": 0.0, "storage": 0.45},
            "model_loading": {"cpu": 0.35, "memory": 0.60, "gpu": 0.20, "storage": 0.70},
            "warmup": {"cpu": 0.50, "memory": 0.70, "gpu": 0.65, "storage": 0.70},
            "load_test": {"cpu": 0.65, "memory": 0.78, "gpu": 0.90, "storage": 0.72},
            "executing": {"cpu": 0.72, "memory": 0.46, "gpu": 0.70, "storage": 0.36},
            "finalizing": {"cpu": 0.18, "memory": 0.20, "gpu": 0.10, "storage": 0.20},
            "serving": {"cpu": 0.55, "memory": 0.72, "gpu": 0.76, "storage": 0.65},
        }.get(stage, {"cpu": 0.25, "memory": 0.25, "gpu": 0.25, "storage": 0.25})
        demand = self.task.demand
        if demand.gpu <= 0:
            utilization["gpu"] = 0.0
        if demand.cpu <= 0:
            utilization["cpu"] = 0.0
        if demand.memory <= 0:
            utilization["memory"] = 0.0
        if demand.storage <= 0:
            utilization["storage"] = 0.0
        metrics["simulated_utilization"] = utilization
        return metrics


class SimulatedNodeRuntime:
    """Long-running, config-driven simulated node runtime.

    It registers nodes, heartbeats continuously, leases tasks, advances a staged
    execution lifecycle over time, and only reports the final result after all
    stages have elapsed. This intentionally behaves like a node runtime rather
    than a one-shot queue drain script.
    """

    def __init__(
        self,
        *,
        nodes: list[Node],
        client: HttpControlPlaneClient,
        executors: ExecutorRegistry,
        poll_interval_seconds: float = 1.0,
        time_scale: float = 0.08,
        log: LogFn | None = None,
    ) -> None:
        self.nodes = nodes
        self.client = client
        self.executors = executors
        self.poll_interval_seconds = poll_interval_seconds
        self.time_scale = max(0.001, float(time_scale))
        self.log = log or (lambda message: None)
        self.active: dict[str, SimulatedRun] = {}
        self.completed: list[dict[str, Any]] = []

    def register_nodes(self) -> None:
        for node in self.nodes:
            self.client.register_node(node)
            self.log(f"node online: {node.node_id} ({node.region})")

    def mark_nodes_offline(self) -> None:
        """Tell the control plane these simulated agents have stopped.

        This keeps the Dashboard faithful to process lifecycle: when the
        simulation backend exits normally or is stopped with Ctrl+C, the nodes
        should stop being displayed as online immediately instead of waiting for
        the heartbeat timeout. If the process is killed abruptly, the control
        plane still falls back to heartbeat timeout expiry.
        """
        for node in self.nodes:
            try:
                self.client.heartbeat(
                    node.node_id,
                    health_score=node.health_score,
                    online=False,
                    cost_per_tick=node.cost_per_tick,
                    region=node.region,
                    labels=sorted(node.labels),
                    performance_factors=dict(node.performance_factors),
                )
                self.log(f"node offline: {node.node_id}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"node offline failed: {node.node_id}: {exc}")

    def tick(self) -> None:
        for node in self.nodes:
            self._heartbeat(node)
        self._advance_runs()
        busy_nodes = {run.node_id for run in self.active.values()}
        for node in self.nodes:
            if node.node_id not in busy_nodes:
                self._try_lease(node)

    def _heartbeat(self, node: Node) -> None:
        self.client.heartbeat(
            node.node_id,
            health_score=node.health_score,
            online=True,
            cost_per_tick=node.cost_per_tick,
            region=node.region,
            labels=sorted(node.labels),
            performance_factors=dict(node.performance_factors),
        )

    def _try_lease(self, node: Node) -> None:
        lease = self.client.request_lease(node.node_id)
        if lease is None:
            return
        task = task_from_dict(lease["task"])
        result = self.executors.run(task.execution, task=task, node=node, lease=lease)
        stages = self._stages_from_result(result)
        run = SimulatedRun(node=node, task=task, lease=lease, result=result, stages=stages)
        self.active[task.task_id] = run
        self._report_progress(run, message="lease acquired")
        self.log(f"lease acquired: {task.task_id} -> {node.node_id}")

    def _advance_runs(self) -> None:
        if not self.active:
            return
        delta = self.poll_interval_seconds / self.time_scale
        for task_id, run in list(self.active.items()):
            previous_stage = run.stage_name()
            changed, finished = run.advance(delta)
            if finished:
                record = self.client.report_result(run.node_id, run.task_id, run.result)
                self.completed.append({"node_id": run.node_id, "task_id": run.task_id, "record": record})
                self.active.pop(task_id, None)
                self.log(f"completed: {run.task_id} -> {run.node_id} ({'success' if run.result.success else 'failed'})")
                continue
            if changed or not run.reported_start:
                run.reported_start = True
                self._report_progress(run, message=f"stage {previous_stage} -> {run.stage_name()}" if changed else "stage started")
            else:
                self._report_progress(run, message="stage progress")

    def _report_progress(self, run: SimulatedRun, *, message: str) -> None:
        self.client.report_progress(
            run.node_id,
            run.task_id,
            stage=run.stage_name(),
            status="running",
            progress=run.progress(),
            message=message,
            metrics=run.progress_metrics(),
        )
        self.log(f"progress: {run.task_id} {run.stage_name()} {int(run.progress() * 100)}%")

    def _stages_from_result(self, result: ExecutionResult) -> list[dict[str, Any]]:
        sim = result.metadata.get("simulation", {}) if result.metadata else {}
        stages = [dict(item) for item in sim.get("lifecycle_events", []) if isinstance(item, dict)]
        if not stages:
            stages = [
                {"stage": "lease_acquired", "status": "ok", "seconds": 0.0},
                {"stage": "provisioning", "status": "ok", "seconds": 2.0},
                {"stage": "load_test", "status": "ok" if result.success else "failed", "seconds": max(1.0, result.duration_seconds)},
            ]
        # Make zero-second stages visible for at least one tick except lease_acquired.
        normalized: list[dict[str, Any]] = []
        for index, stage in enumerate(stages):
            item = dict(stage)
            if index > 0 and float(item.get("seconds", 0.0)) <= 0:
                item["seconds"] = self.poll_interval_seconds / self.time_scale
            normalized.append(item)
        return normalized


def run_simulation_backend(
    *,
    config_path: str | Path,
    server: str,
    node_ids: list[str] | None = None,
    max_cycles: int | None = None,
    poll_interval_seconds: float = 1.0,
    time_scale: float | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run config-driven simulated node agents against a Tianjun control plane.

    Without max_cycles this function runs until interrupted. With max_cycles it
    stops after the requested number of ticks, which is useful for tests and CI.
    """
    config = load_inventory_config(config_path)
    wanted = set(node_ids or [])
    nodes = [node for node in nodes_from_inventory(config) if not wanted or node.node_id in wanted]
    if not nodes:
        raise ValueError("simulation backend has no nodes to register; check config or --node-id.")

    def log(message: str) -> None:
        if verbose:
            print(f"[sim] {message}", flush=True)

    client = HttpControlPlaneClient(server)
    runtime = SimulatedNodeRuntime(
        nodes=nodes,
        client=client,
        executors=ExecutorRegistry(simulation_config=config),
        poll_interval_seconds=poll_interval_seconds,
        time_scale=float(time_scale if time_scale is not None else config.get("time_scale", 0.08)),
        log=log,
    )
    runtime.register_nodes()
    log("simulation backend is running; press Ctrl+C to stop")

    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            runtime.tick()
            cycles += 1
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)
    except KeyboardInterrupt:
        log("stopped by user")
    finally:
        runtime.mark_nodes_offline()

    report = client.get_report()
    return {
        "status": "stopped" if max_cycles is None else "max_cycles_reached",
        "registered_nodes": [node.node_id for node in nodes],
        "active_runs": [run.task_id for run in runtime.active.values()],
        "completed": runtime.completed,
        "cycles": cycles,
        "totals": report.get("totals", {}),
    }
