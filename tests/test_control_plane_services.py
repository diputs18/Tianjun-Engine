from __future__ import annotations

from tianjun.application.control_plane import CentralControlPlane
from tianjun.application.node_registry import NodeRegistry
from tianjun.application.policy_workflow import PolicyWorkflowService
from tianjun.application.requirement_dialogue import RequirementDialogueService
from tianjun.application.task_lease_service import TaskLeaseService


def test_control_plane_exposes_service_boundaries() -> None:
    control_plane = CentralControlPlane()

    assert isinstance(control_plane.node_registry, NodeRegistry)
    assert isinstance(control_plane.task_lease_service, TaskLeaseService)
    assert isinstance(control_plane.policy_workflow, PolicyWorkflowService)
    assert isinstance(control_plane.requirement_dialogue, RequirementDialogueService)
    assert control_plane.node_registry.node_count == 0
    assert control_plane.task_lease_service.active_lease_count == 0
