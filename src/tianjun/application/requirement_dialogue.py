from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane

from ..policy.clarifier import ConversationTurn, RequirementSession, clarification_questions, session_status


@dataclass(slots=True)
class RequirementDialogueService:
    """Boundary for requirement parsing and multi-turn clarification sessions."""

    control_plane: CentralControlPlane

    @property
    def session_count(self) -> int:
        return len(self.control_plane.requirement_sessions)

    def parse_requirement(
        self,
        message: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            requirement = control.policy_generator.parse_requirement(message, overrides=overrides)
            payload = requirement.to_dict()
            payload["questions"] = clarification_questions(requirement, control.nodes.values())
            payload["dialogue_status"] = session_status(requirement, payload["questions"])
            return payload

    def start_requirement_session(
        self,
        message: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            requirement = control.policy_generator.parse_requirement(message, overrides=overrides)
            questions = clarification_questions(requirement, control.nodes.values())
            session = RequirementSession(
                session_id=control._new_session_id(),
                requirement=requirement,
                turns=[ConversationTurn(role="user", content=str(message))],
                questions=questions,
                status=session_status(requirement, questions),
            )
            if questions:
                session.turns.append(ConversationTurn(role="assistant", content="\n".join(questions)))
            control.requirement_sessions[session.session_id] = session
            return self.requirement_session_payload(session)

    def continue_requirement_session(
        self,
        session_id: str,
        message: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            session = self.session_or_raise(session_id)
            requirement = control.policy_generator.merge_requirement_update(
                session.requirement,
                message,
                overrides=overrides,
            )
            questions = clarification_questions(requirement, control.nodes.values())
            session.requirement = requirement
            session.questions = questions
            session.status = session_status(requirement, questions)
            session.updated_at = time.time()
            session.turns.append(ConversationTurn(role="user", content=str(message)))
            if questions:
                session.turns.append(ConversationTurn(role="assistant", content="\n".join(questions)))
            else:
                session.turns.append(ConversationTurn(role="assistant", content="Requirement slots are complete; a compute-network policy draft can be generated."))
            return self.requirement_session_payload(session)

    def get_requirement_session(self, session_id: str) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            return self.requirement_session_payload(self.session_or_raise(session_id))

    def requirement_session_payload(self, session: RequirementSession) -> dict[str, Any]:
        control = self.control_plane
        control._expire_stale_nodes()
        payload = session.to_dict()
        requested_regions = list(session.requirement.region_preference)
        registered_regions: dict[str, int] = {}
        online_regions: dict[str, int] = {}
        for node in control.nodes.values():
            service_region = node.service_region or node.location or node.region
            registered_regions[service_region] = registered_regions.get(service_region, 0) + 1
            if node.online:
                online_regions[service_region] = online_regions.get(service_region, 0) + 1
        payload["region_availability"] = {
            "requested_regions": requested_regions,
            "registered_regions": registered_regions,
            "online_regions": online_regions,
            "unregistered_regions": [region for region in requested_regions if region not in registered_regions],
            "offline_regions": [
                region
                for region in requested_regions
                if region in registered_regions and region not in online_regions
            ],
        }
        return payload

    def session_or_raise(self, session_id: str) -> RequirementSession:
        session = self.control_plane.requirement_sessions.get(session_id)
        if session is None:
            raise ValueError(f"Unknown requirement session {session_id}.")
        return session
