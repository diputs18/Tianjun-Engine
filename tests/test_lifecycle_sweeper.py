from __future__ import annotations

import time

from tianjun.application.control_plane import CentralControlPlane
from tianjun.application.lifecycle import LifecycleSweeper
from tianjun.domain import Node, ResourceVector, Task, TaskStatus


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def test_sweeper_expires_nodes_without_dashboard_or_api_traffic() -> None:
    control = CentralControlPlane(heartbeat_timeout_seconds=0.05)
    control.register_node(Node(
        node_id="idle-node",
        region="dc1",
        capacity=ResourceVector(cpu=2, memory=2, storage=2),
    ))
    sweeper = LifecycleSweeper(control, interval_seconds=0.01)

    sweeper.start()
    try:
        _wait_until(lambda: not control.nodes["idle-node"].online)
        assert sweeper.run_count > 0
        assert sweeper.failure_count == 0
    finally:
        sweeper.stop()
    assert sweeper.running is False


def test_sweeper_expires_lease_and_releases_capacity_without_polling() -> None:
    control = CentralControlPlane(
        heartbeat_timeout_seconds=60.0,
        lease_timeout_seconds=0.05,
    )
    control.register_node(Node(
        node_id="worker",
        region="dc1",
        capacity=ResourceVector(cpu=2, memory=2, storage=2),
    ))
    control.submit_task(Task(
        task_id="leased-task",
        task_type="batch",
        demand=ResourceVector(cpu=1, memory=1, storage=1),
        estimated_duration=2,
    ))
    assert control.request_lease("worker") is not None
    control.leases["leased-task"].expires_at_epoch = time.time() - 1.0
    sweeper = LifecycleSweeper(control, interval_seconds=0.01)

    sweeper.start()
    try:
        _wait_until(lambda: "leased-task" not in control.leases)
        assert control.tasks["leased-task"].status == TaskStatus.PENDING
        assert control.nodes["worker"].used().cpu == 0
    finally:
        sweeper.stop()


def test_sweeper_start_and_stop_are_idempotent() -> None:
    sweeper = LifecycleSweeper(CentralControlPlane(), interval_seconds=0.01)
    sweeper.start()
    first_thread = sweeper._thread
    sweeper.start()
    assert sweeper._thread is first_thread
    sweeper.stop()
    sweeper.stop()
    assert sweeper.running is False
