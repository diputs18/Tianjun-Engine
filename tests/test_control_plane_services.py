from __future__ import annotations

from tianjun.application.control_plane import CentralControlPlane
from tianjun.application.node_registry import NodeRegistry
from tianjun.application.policy_workflow import PolicyWorkflowService
from tianjun.application.requirement_dialogue import RequirementDialogueService
from tianjun.application.task_lease_service import TaskLeaseService
from tianjun.domain import Node, ResourceVector, Task, TaskStatus


def test_control_plane_exposes_service_boundaries() -> None:
    control_plane = CentralControlPlane()

    assert isinstance(control_plane.node_registry, NodeRegistry)
    assert isinstance(control_plane.task_lease_service, TaskLeaseService)
    assert isinstance(control_plane.policy_workflow, PolicyWorkflowService)
    assert isinstance(control_plane.requirement_dialogue, RequirementDialogueService)
    assert control_plane.node_registry.node_count == 0
    assert control_plane.task_lease_service.active_lease_count == 0


def test_node_registry_handles_registration_and_heartbeat_through_facade() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(Node(node_id="node-a", region="dc1", capacity=ResourceVector(cpu=4)))

    heartbeat = control_plane.record_heartbeat("node-a", health_score=0.5, labels={"edge"})

    assert control_plane.node_registry.node_count == 1
    assert control_plane.nodes["node-a"].health_score == 0.5
    assert control_plane.nodes["node-a"].labels == {"edge"}
    assert heartbeat["node_id"] == "node-a"


def test_task_lease_service_handles_task_lifecycle_through_facade() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(
        Node(
            node_id="node-a",
            region="dc1",
            capacity=ResourceVector(cpu=4, memory=8, storage=20),
        )
    )
    task = Task(
        task_id="task-a",
        task_type="batch",
        demand=ResourceVector(cpu=1, memory=1, storage=1),
        estimated_duration=2,
    )

    submitted = control_plane.submit_task(task)
    preview = control_plane.preview_task(task)
    scheduled = control_plane.schedule_pending_task("task-a")

    assert submitted["task_id"] == "task-a"
    assert preview is not None
    assert scheduled["status"] == "committed"
    assert scheduled["lease"]["node_id"] == "node-a"
    assert control_plane.task_lease_service.active_lease_count == 1
    assert control_plane.tasks["task-a"].status == TaskStatus.RUNNING
    assert control_plane.request_lease("node-a") is None


def test_task_lease_service_rejects_duplicate_task_ids() -> None:
    control_plane = CentralControlPlane()
    task = Task(task_id="dup", task_type="batch", demand=ResourceVector(cpu=1), estimated_duration=1)

    control_plane.submit_task(task)

    try:
        control_plane.submit_task(Task(task_id="dup", task_type="batch", demand=ResourceVector(cpu=1), estimated_duration=1))
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("duplicate task id was accepted")


def test_task_lease_service_rejects_unknown_task_schedule() -> None:
    control_plane = CentralControlPlane()

    try:
        control_plane.schedule_pending_task("missing")
    except ValueError as exc:
        assert "Unknown task" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unknown task was scheduled")


def test_task_lease_service_returns_rejected_when_no_node_is_feasible() -> None:
    control_plane = CentralControlPlane()
    task = Task(task_id="no-node", task_type="batch", demand=ResourceVector(cpu=1), estimated_duration=1)
    control_plane.submit_task(task)

    result = control_plane.schedule_pending_task("no-node")

    assert result["status"] == "rejected"
    assert result["lease"] is None


def test_request_lease_respects_target_node_id() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(Node(node_id="node-a", region="dc1", capacity=ResourceVector(cpu=4)))
    control_plane.register_node(Node(node_id="node-b", region="dc1", capacity=ResourceVector(cpu=4)))
    task = Task(
        task_id="targeted",
        task_type="batch",
        demand=ResourceVector(cpu=1),
        estimated_duration=1,
        target_node_id="node-b",
    )
    control_plane.submit_task(task)

    assert control_plane.request_lease("node-a") is None
    lease = control_plane.request_lease("node-b")

    assert lease is not None
    assert lease["node_id"] == "node-b"


def test_requirement_dialogue_service_handles_sessions_through_facade() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(
        Node(
            node_id="east-a",
            region="dc1",
            service_region="east",
            capacity=ResourceVector(cpu=4, memory=8),
        )
    )

    parsed = control_plane.parse_requirement("east batch job with 1 cpu")
    started = control_plane.start_requirement_session("east batch job with 1 cpu")
    continued = control_plane.continue_requirement_session(
        started["session_id"],
        "latency under 100ms and budget 10",
    )
    loaded = control_plane.get_requirement_session(started["session_id"])

    assert "dialogue_status" in parsed
    assert control_plane.requirement_dialogue.session_count == 1
    assert continued["session_id"] == started["session_id"]
    assert loaded["region_availability"]["registered_regions"]["east"] == 1
