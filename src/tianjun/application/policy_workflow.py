from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


@dataclass(slots=True)
class PolicyWorkflowService:
    """Boundary for policy draft, comparison, simulation, commit, and feedback optimization."""

    control_plane: CentralControlPlane

    @property
    def policy_count(self) -> int:
        return len(self.control_plane.policies)
