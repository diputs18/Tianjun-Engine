from __future__ import annotations

from typing import Any

from ..application.control_plane import CentralControlPlane
from ..tools import TianjunToolService


def _payload(policy_id: str, instruction: str, target: str | None, sentiment: str | None, preference_delta: dict[str, float] | None) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "target": target,
        "sentiment": sentiment,
        "instruction": instruction,
        "preference_delta": preference_delta or {},
    }


def parse_user_feedback(
    control_plane: CentralControlPlane,
    *,
    policy_id: str,
    instruction: str,
    target: str | None = None,
    sentiment: str | None = None,
    preference_delta: dict[str, float] | None = None,
) -> dict[str, Any]:
    return TianjunToolService(control_plane).parse_user_feedback(_payload(policy_id, instruction, target, sentiment, preference_delta))


def collect_user_feedback(
    control_plane: CentralControlPlane,
    *,
    policy_id: str,
    instruction: str,
    target: str | None = None,
    sentiment: str | None = None,
    preference_delta: dict[str, float] | None = None,
) -> dict[str, Any]:
    return control_plane.record_user_feedback(_payload(policy_id, instruction, target, sentiment, preference_delta))


def optimize_policy_from_feedback(
    control_plane: CentralControlPlane,
    *,
    policy_id: str,
    instruction: str,
    target: str | None = None,
    sentiment: str | None = None,
    preference_delta: dict[str, float] | None = None,
) -> dict[str, Any]:
    return TianjunToolService(control_plane).optimize_policy_from_feedback(_payload(policy_id, instruction, target, sentiment, preference_delta))
