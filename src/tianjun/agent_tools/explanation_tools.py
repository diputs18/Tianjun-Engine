from __future__ import annotations

from typing import Any

from ..application.control_plane import CentralControlPlane
from ..tools import TianjunToolService


def explain_policy(control_plane: CentralControlPlane, policy_id: str) -> dict[str, Any]:
    return TianjunToolService(control_plane).explain_policy(policy_id)
