from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


@dataclass(slots=True)
class TaskLeaseService:
    """Boundary for task submission, scheduling, lease issue, and run reporting."""

    control_plane: CentralControlPlane

    @property
    def active_lease_count(self) -> int:
        return len(self.control_plane.leases)
