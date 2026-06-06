from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


@dataclass(slots=True)
class RequirementDialogueService:
    """Boundary for requirement parsing and multi-turn clarification sessions."""

    control_plane: CentralControlPlane

    @property
    def session_count(self) -> int:
        return len(self.control_plane.requirement_sessions)
