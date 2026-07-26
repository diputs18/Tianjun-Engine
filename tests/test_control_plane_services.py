from __future__ import annotations

from tianjun.application.control_plane import CentralControlPlane
from tianjun.application.node_registry import NodeRegistry
from tianjun.application.policy_workflow import PolicyWorkflowService
from tianjun.application.requirement_dialogue import RequirementDialogueService
from tianjun.application.task_lease_service import TaskLeaseService
from tianjun.core import UserRequirement
from tianjun.domain import NetworkPathProfile, Node, ResourceVector, Task, TaskStatus
from tianjun.storage.sqlite_state_store import SQLiteStateStore


def test_control_plane_exposes_service_boundaries() -> None:
    control_plane = CentralControlPlane()

    assert isinstance(control_plane.node_registry, NodeRegistry)
    assert isinstance(control_plane.task_lease_service, TaskLeaseService)
    assert isinstance(control_plane.policy_workflow, PolicyWorkflowService)
    assert isinstance(control_plane.requirement_dialogue, RequirementDialogueService)
    assert control_plane.node_registry.node_count == 0
    assert control_plane.task_lease_service.active_lease_count == 0


def test_external_mcp_audit_survives_control_plane_restart(tmp_path) -> None:
    database_path = tmp_path / "control-plane.db"
    store = SQLiteStateStore(database_path)
    control_plane = CentralControlPlane(state_store=store)
    control_plane.record_tool_call(
        tool_name="get_cluster_state",
        actor="external_mcp",
        result_status="success",
        request_id="req-persisted",
    )
    store.close()

    restored_store = SQLiteStateStore(database_path)
    try:
        restored = CentralControlPlane(state_store=restored_store)
        runtime = restored.build_report()["toolchain_runtime"]
        assert runtime["external_mcp_call_count"] == 1
        assert runtime["external_mcp_success_count"] == 1
        assert runtime["external_mcp_last_success"]["request_id"] == "req-persisted"
    finally:
        restored_store.close()


def test_sqlite_history_retention_keeps_latest_records(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "retention.db")
    store.MAX_EXECUTION_RECORDS = 2
    try:
        for index in range(3):
            store.append_execution_record({
                "task_id": f"task-{index}",
                "node_id": "node-a",
                "success": True,
            })

        records = store.load_state()["execution_records"]
        assert [record["task_id"] for record in records] == ["task-1", "task-2"]
    finally:
        store.close()


def test_control_plane_facade_delegates_migrated_service_boundaries(monkeypatch) -> None:
    calls: list[str] = []

    def node_register(self, node):
        calls.append("node")
        return {"service": "node"}

    def task_submit(self, task):
        calls.append("task")
        return {"service": "task"}

    def requirement_parse(self, message, *, overrides=None):
        calls.append("requirement")
        return {"service": "requirement"}

    def policy_draft(self, requirement_payload, *, execution_payload=None):
        calls.append("policy")
        return {"service": "policy"}

    monkeypatch.setattr(NodeRegistry, "register_node", node_register)
    monkeypatch.setattr(TaskLeaseService, "submit_task", task_submit)
    monkeypatch.setattr(RequirementDialogueService, "parse_requirement", requirement_parse)
    monkeypatch.setattr(PolicyWorkflowService, "draft_policy", policy_draft)

    control_plane = CentralControlPlane()

    assert control_plane.register_node(object()) == {"service": "node"}
    assert control_plane.submit_task(object()) == {"service": "task"}
    assert control_plane.parse_requirement("hello") == {"service": "requirement"}
    assert control_plane.draft_policy({}) == {"service": "policy"}
    assert calls == ["node", "task", "requirement", "policy"]


def test_node_registry_handles_registration_and_heartbeat_through_facade() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(Node(node_id="node-a", region="dc1", capacity=ResourceVector(cpu=4)))

    heartbeat = control_plane.record_heartbeat("node-a", health_score=0.5, labels={"edge"})

    assert control_plane.node_registry.node_count == 1
    assert control_plane.nodes["node-a"].health_score == 0.5
    assert control_plane.nodes["node-a"].labels == {"edge"}
    assert heartbeat["node_id"] == "node-a"


def test_cloudsim_heartbeat_telemetry_survives_into_node_report() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(Node(node_id="dci-dc1-beijing-vm-0", region="dc1", capacity=ResourceVector(cpu=4, memory=8)))

    control_plane.record_heartbeat(
        "dci-dc1-beijing-vm-0",
        runtime_telemetry={
            "cpu_utilization": 0.42,
            "ram_utilization": 0.31,
            "bandwidth_utilization": 0.18,
        },
        telemetry_source="cloudsim",
        simulation_tick=12.5,
    )

    node = control_plane.build_report()["nodes"][0]
    assert node["runtime_utilization"] == {
        "cpu": 0.42,
        "memory": 0.31,
        "gpu": None,
        "storage": None,
        "bandwidth": 0.18,
    }
    assert node["telemetry_source"] == "cloudsim"
    assert node["simulation_tick"] == 12.5
    assert node["resource_load_source"] == "simulated_telemetry"
    assert node["resource_load_source_label"] == "CloudSim Plus 模拟遥测"
    assert node["telemetry_freshness"] == "current"


def test_cloudsim_label_does_not_exempt_node_from_heartbeat_expiry() -> None:
    control_plane = CentralControlPlane(heartbeat_timeout_seconds=1.0)
    control_plane.register_node(Node(
        node_id="cloudsim-node",
        region="dc1",
        labels={"cloudsim"},
        capacity=ResourceVector(cpu=4),
    ))
    control_plane.last_heartbeat_at["cloudsim-node"] -= 2.0

    node = control_plane.build_report()["nodes"][0]

    assert node["online"] is False
    assert node["telemetry_freshness"] == "unavailable"


def test_report_distinguishes_configured_carbon_from_live_signal() -> None:
    control_plane = CentralControlPlane()
    control_plane.register_node(Node(node_id="node-a", region="dc1", capacity=ResourceVector(cpu=4)))

    configured = control_plane.build_report()["nodes"][0]
    assert configured["carbon_data_source"] == "simulated_profile"
    assert configured["carbon_data_freshness"] == "profile"

    control_plane.record_heartbeat(
        "node-a",
        carbon_intensity_g_per_kwh=320.0,
        carbon_signal_timestamp=100.0,
        telemetry_source="node_agent",
    )
    live = control_plane.build_report()["nodes"][0]
    assert live["carbon_data_source"] == "live_signal"
    assert live["carbon_data_freshness"] == "current"


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
    delivered = control_plane.request_lease("node-a")
    assert delivered is not None
    assert delivered["task_id"] == "task-a"
    control_plane.report_task_progress(
        node_id="node-a",
        task_id="task-a",
        stage="executing",
        status="running",
        progress=0.5,
    )
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


def policy_ready_control_plane() -> tuple[CentralControlPlane, dict]:
    control_plane = CentralControlPlane()
    control_plane.register_node(
        Node(
            node_id="node-a",
            region="east",
            location="shanghai",
            service_region="east",
            labels={"latency-sensitive"},
            capacity=ResourceVector(cpu=8, memory=16, gpu=0, storage=50),
            cost_per_tick=0.1,
            base_reliability=0.99,
            network_paths={"east": NetworkPathProfile(latency_ms=10, bandwidth_mbps=1000)},
        )
    )
    requirement = UserRequirement(
        objective="deploy batch",
        workload_type="batch",
        region_preference=["east"],
        cpu_cores=1,
        memory_gb=1,
        gpu_count=0,
        latency_target_ms=100,
        bandwidth_mbps=10,
        budget_limit=1000,
        confidence=1,
        missing_fields=[],
    ).to_dict()
    return control_plane, requirement


def test_policy_workflow_drafts_policy_through_facade() -> None:
    control_plane, requirement = policy_ready_control_plane()

    policy = control_plane.draft_policy(requirement)

    assert policy["status"] == "draft"
    assert policy["selected_compute"]["node_id"] == "node-a"
    assert control_plane.policy_workflow.policy_count == 1


def test_policy_workflow_compares_options_through_facade() -> None:
    control_plane, requirement = policy_ready_control_plane()

    comparison = control_plane.compare_policy_options(requirement)

    assert comparison["status"] == "compared"
    assert [option["label"] for option in comparison["options"]] == ["A", "B", "C"]
    assert comparison["recommended_policy_id"] in control_plane.policies


def test_policy_workflow_simulates_policy_through_facade() -> None:
    control_plane, requirement = policy_ready_control_plane()
    policy = control_plane.draft_policy(requirement)

    simulation = control_plane.simulate_policy(policy["policy_id"])

    assert simulation["policy_id"] == policy["policy_id"]
    assert simulation["status"] in {"feasible", "feasible_with_risks", "infeasible"}


def test_policy_workflow_commit_requires_existing_policy() -> None:
    control_plane = CentralControlPlane()

    try:
        control_plane.commit_policy("missing")
    except ValueError as exc:
        assert "Unknown policy" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unknown policy was committed")


def test_policy_workflow_commit_creates_pending_task() -> None:
    control_plane, requirement = policy_ready_control_plane()
    policy = control_plane.draft_policy(requirement)

    committed = control_plane.commit_policy(policy["policy_id"])

    assert committed["status"] == "committed"
    assert committed["submitted_task"]["task_id"] in control_plane.tasks
    assert control_plane.tasks[committed["submitted_task"]["task_id"]].status == TaskStatus.PENDING


def test_policy_workflow_feedback_optimization_through_facade() -> None:
    control_plane, requirement = policy_ready_control_plane()
    policy = control_plane.draft_policy(requirement)

    parsed = control_plane.parse_feedback({"policy_id": policy["policy_id"], "instruction": "make it lower latency"})
    optimized = control_plane.optimize_policy_from_feedback({
        "policy_id": policy["policy_id"],
        "instruction": "make it lower latency",
    })

    assert parsed["policy_id"] == policy["policy_id"]
    assert optimized["status"] == "optimized"
    assert optimized["base_policy_id"] == policy["policy_id"]
    assert optimized["policy"]["policy_id"] in control_plane.policies
