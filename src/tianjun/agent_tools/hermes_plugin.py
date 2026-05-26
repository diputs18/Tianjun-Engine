from __future__ import annotations

from typing import Any

from ..application.control_plane import CentralControlPlane
from ..tools import TianjunToolService


def build_tool_registry(control_plane: CentralControlPlane) -> dict[str, Any]:
    """Backward-compatible in-process registry for Hermes-like runtimes.

    The actual implementation is delegated to TianjunToolService so Dashboard,
    MCP and Hermes use one tool contract and one control-plane mapping.
    """
    service = TianjunToolService(control_plane)
    return {
        "contract": service.contract(),
        "tools": {
            "get_cluster_state": lambda: service.get_cluster_state(),
            "analyze_user_intent": lambda message, overrides=None: service.analyze_user_intent(message, overrides),
            "start_requirement_dialogue": lambda message, overrides=None: service.start_requirement_dialogue(message, overrides),
            "continue_requirement_dialogue": lambda session_id, message, overrides=None: service.continue_requirement_dialogue(session_id, message, overrides),
            "draft_compute_network_policy": lambda **kwargs: service.draft_compute_network_policy(**kwargs),
            "simulate_policy": lambda policy_id: service.simulate_policy(policy_id),
            "explain_policy": lambda policy_id: service.explain_policy(policy_id),
            "commit_policy": lambda policy_id, confirmed=False: service.commit_policy(policy_id, confirmed_by_user_button=confirmed),
            "schedule_pending_task": lambda task_id, confirmed=False: service.schedule_pending_task(task_id, confirmed_by_user_button=confirmed),
            "parse_user_feedback": lambda **kwargs: service.parse_user_feedback(kwargs),
            "collect_user_feedback": lambda **kwargs: control_plane.record_user_feedback(kwargs),
            "optimize_policy_from_feedback": lambda **kwargs: service.optimize_policy_from_feedback(kwargs),
        },
    }
