from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


@dataclass(slots=True)
class NodeRegistry:
    """Boundary for node inventory, heartbeat, health, and topology state."""

    control_plane: CentralControlPlane

    @property
    def node_count(self) -> int:
        return len(self.control_plane.nodes)
