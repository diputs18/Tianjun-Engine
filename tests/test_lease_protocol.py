from __future__ import annotations

import threading
import time

import pytest

from tianjun.application.control_plane import CentralControlPlane
from tianjun.domain import Node, ResourceVector, Task, TaskStatus
from tianjun.storage.sqlite_state_store import SQLiteStateStore


def _control(*, lease_timeout_seconds: float = 60.0) -> CentralControlPlane:
    control = CentralControlPlane(lease_timeout_seconds=lease_timeout_seconds)
    control.register_node(Node(
        node_id="node-a",
        region="dc1",
        capacity=ResourceVector(cpu=4, memory=8, storage=20),
    ))
    return control


def _submit(control: CentralControlPlane, task_id: str = "task-a") -> None:
    control.submit_task(Task(
        task_id=task_id,
        task_type="batch",
        demand=ResourceVector(cpu=1, memory=1, storage=1),
        estimated_duration=2,
    ))


def test_lease_ack_and_result_retry_are_idempotent() -> None:
    control = _control()
    _submit(control)
    lease = control.request_lease("node-a")
    assert lease is not None
    assert lease["lease_id"].startswith("lease-")
    assert lease["acknowledged_at_epoch"] is None

    acknowledged = control.acknowledge_lease(
        node_id="node-a",
        task_id="task-a",
        lease_id=lease["lease_id"],
    )
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["acknowledged_at_epoch"] is not None
    assert control.request_lease("node-a") is None

    first = control.report_task_result(
        node_id="node-a",
        task_id="task-a",
        lease_id=lease["lease_id"],
        result_id="result-a",
        success=True,
        duration_seconds=1.0,
    )
    replay = control.report_task_result(
        node_id="node-a",
        task_id="task-a",
        lease_id=lease["lease_id"],
        result_id="result-a",
        success=True,
        duration_seconds=1.0,
    )

    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["result_id"] == first["result_id"]
    assert len(control.execution_history) == 1


def test_progress_implicitly_acknowledges_and_renews_lease() -> None:
    control = _control(lease_timeout_seconds=5.0)
    _submit(control)
    lease = control.request_lease("node-a")
    assert lease is not None
    original_expiry = lease["expires_at_epoch"]
    control.leases["task-a"].expires_at_epoch = time.time() + 0.1

    progress = control.report_task_progress(
        node_id="node-a",
        task_id="task-a",
        lease_id=lease["lease_id"],
        stage="executing",
        progress=0.5,
    )

    assert progress["progress"] == 0.5
    active = control.leases["task-a"]
    assert active.acknowledged_at_epoch is not None
    assert active.expires_at_epoch > original_expiry


def test_expired_lease_releases_capacity_and_requeues_task() -> None:
    control = _control(lease_timeout_seconds=1.0)
    _submit(control)
    lease = control.request_lease("node-a")
    assert lease is not None
    control.leases["task-a"].expires_at_epoch = time.time() - 1.0

    expired = control.task_lease_service.expire_stale_leases()

    assert expired == ["task-a"]
    assert control.leases == {}
    assert control.nodes["node-a"].used().cpu == 0
    assert control.tasks["task-a"].status == TaskStatus.PENDING
    assert control.pending_queue == ["task-a"]


def test_concurrent_lease_requests_share_one_identity() -> None:
    control = _control()
    _submit(control)
    barrier = threading.Barrier(8)
    results: list[dict | None] = []
    result_lock = threading.Lock()

    def request() -> None:
        barrier.wait(timeout=2)
        result = control.request_lease("node-a")
        with result_lock:
            results.append(result)

    workers = [threading.Thread(target=request) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)

    assert all(not worker.is_alive() for worker in workers)
    assert len(control.leases) == 1
    assert len({item["lease_id"] for item in results if item is not None}) == 1
    assert len([item for item in results if item is not None]) == 8


def test_ack_rejects_wrong_lease_identity() -> None:
    control = _control()
    _submit(control)
    lease = control.request_lease("node-a")
    assert lease is not None

    with pytest.raises(ValueError, match="identity"):
        control.acknowledge_lease(
            node_id="node-a",
            task_id="task-a",
            lease_id="lease-wrong",
        )


def test_idempotent_result_receipt_survives_restart(tmp_path) -> None:
    path = tmp_path / "receipts.db"
    store = SQLiteStateStore(path)
    control = CentralControlPlane(state_store=store)
    control.register_node(Node(
        node_id="node-a",
        region="dc1",
        capacity=ResourceVector(cpu=2, memory=2, storage=2),
    ))
    _submit(control)
    lease = control.request_lease("node-a")
    assert lease is not None
    first = control.report_task_result(
        node_id="node-a",
        task_id="task-a",
        lease_id=lease["lease_id"],
        result_id="persistent-result",
        success=True,
        duration_seconds=1.0,
    )
    store.close()

    restored_store = SQLiteStateStore(path)
    try:
        restored = CentralControlPlane(state_store=restored_store)
        replay = restored.report_task_result(
            node_id="node-a",
            task_id="task-a",
            lease_id=lease["lease_id"],
            result_id="persistent-result",
            success=True,
            duration_seconds=1.0,
        )
        assert replay["idempotent_replay"] is True
        assert replay["result_id"] == first["result_id"]
        assert len(restored.execution_history) == 1
    finally:
        restored_store.close()
