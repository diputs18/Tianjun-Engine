from __future__ import annotations

from typing import Any

from ..application.control_plane import CentralControlPlane
from ..tools import TianjunToolService


def analyze_user_intent(control_plane: CentralControlPlane, message: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return TianjunToolService(control_plane).analyze_user_intent(message, overrides=overrides)


def start_requirement_dialogue(control_plane: CentralControlPlane, message: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return TianjunToolService(control_plane).start_requirement_dialogue(message, overrides=overrides)


def continue_requirement_dialogue(control_plane: CentralControlPlane, session_id: str, message: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return TianjunToolService(control_plane).continue_requirement_dialogue(session_id, message, overrides=overrides)


def draft_compute_network_policy(
    control_plane: CentralControlPlane,
    requirement: dict[str, Any] | None = None,
    *,
    message: str | None = None,
    session_id: str | None = None,
    overrides: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return TianjunToolService(control_plane).draft_compute_network_policy(
        requirement=requirement,
        message=message,
        session_id=session_id,
        overrides=overrides,
        execution=execution,
    )


def simulate_policy(control_plane: CentralControlPlane, policy_id: str) -> dict[str, Any]:
    return TianjunToolService(control_plane).simulate_policy(policy_id)


def commit_policy(control_plane: CentralControlPlane, policy_id: str, *, confirmed: bool = False) -> dict[str, Any]:
    return TianjunToolService(control_plane).commit_policy(policy_id, confirmed_by_user_button=confirmed)


def schedule_pending_task(control_plane: CentralControlPlane, task_id: str, *, confirmed: bool = False) -> dict[str, Any]:
    return TianjunToolService(control_plane).schedule_pending_task(task_id, confirmed_by_user_button=confirmed)
