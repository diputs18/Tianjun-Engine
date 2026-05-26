from __future__ import annotations

from typing import Any

from ..application.control_plane import CentralControlPlane
from ..tools import TianjunToolService


def get_cluster_state(control_plane: CentralControlPlane) -> dict[str, Any]:
    return TianjunToolService(control_plane).get_cluster_state()
