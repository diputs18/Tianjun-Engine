from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from ..application.control_plane import CentralControlPlane
from ..execution.executors import ExecutionResult
from ..domain import Node, Task
from ..scenarios import node_from_dict, task_from_dict


class DirectControlPlaneClient:
    def __init__(self, control_plane: CentralControlPlane) -> None:
        self.control_plane = control_plane

    def register_node(self, node: Node) -> dict[str, Any]:
        return self.control_plane.register_node(node_from_dict(node.to_dict()))

    def submit_task(self, task: Task) -> dict[str, Any]:
        return self.control_plane.submit_task(task_from_dict(task.to_dict()))

    def heartbeat(self, node_id: str, **payload: Any) -> dict[str, Any]:
        return self.control_plane.record_heartbeat(node_id, **payload)

    def request_lease(self, node_id: str) -> dict[str, Any] | None:
        return self.control_plane.request_lease(node_id)

    def report_progress(
        self,
        node_id: str,
        task_id: str,
        *,
        stage: str,
        status: str = "running",
        progress: float | None = None,
        message: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.control_plane.report_task_progress(
            node_id=node_id,
            task_id=task_id,
            stage=stage,
            status=status,
            progress=progress,
            message=message,
            metrics=metrics,
        )

    def report_result(self, node_id: str, task_id: str, result: ExecutionResult) -> dict[str, Any]:
        return self.control_plane.report_task_result(
            node_id=node_id,
            task_id=task_id,
            success=result.success,
            duration_seconds=result.duration_seconds,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            failure_reason=None if result.success else f"returncode_{result.returncode}",
            cost=result.cost,
            metadata=result.metadata,
        )

    def get_report(self) -> dict[str, Any]:
        return self.control_plane.build_report()


class HttpControlPlaneClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def register_node(self, node: Node) -> dict[str, Any]:
        return self._post_json("/nodes/register", node.to_dict())

    def submit_task(self, task: Task) -> dict[str, Any]:
        return self._post_json("/tasks", task.to_dict())

    def heartbeat(self, node_id: str, **payload: Any) -> dict[str, Any]:
        body = {"node_id": node_id}
        body.update(payload)
        return self._post_json("/nodes/heartbeat", body)

    def request_lease(self, node_id: str) -> dict[str, Any] | None:
        return self._post_json("/leases/next", {"node_id": node_id})

    def report_progress(
        self,
        node_id: str,
        task_id: str,
        *,
        stage: str,
        status: str = "running",
        progress: float | None = None,
        message: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post_json(
            "/task-runs/progress",
            {
                "node_id": node_id,
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "progress": progress,
                "message": message,
                "metrics": metrics or {},
            },
        )

    def report_result(self, node_id: str, task_id: str, result: ExecutionResult) -> dict[str, Any]:
        return self._post_json(
            "/task-runs/result",
            {
                "node_id": node_id,
                "task_id": task_id,
                "success": result.success,
                "duration_seconds": result.duration_seconds,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "failure_reason": None if result.success else f"returncode_{result.returncode}",
                "cost": result.cost,
                "metadata": result.metadata,
            },
        )

    def get_report(self) -> dict[str, Any]:
        req = request.Request(f"{self.base_url}/report", method="GET")
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:
            message = exc.read().decode("utf-8")
            raise RuntimeError(f"HTTP {exc.code} on {path}: {message}") from exc
