from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChatTurn:
    role: str
    content: str
    created_at: float = field(default_factory=time.time)
    tool_name: str | None = None
    tool_payload: dict[str, Any] | None = None

    def to_dict(self, *, include_tool_payload: bool = True) -> dict[str, Any]:
        payload = {
            "role": self.role,
            "content": self.content,
            "created_at": round(self.created_at, 4),
        }
        if self.tool_name:
            payload["tool_name"] = self.tool_name
        if include_tool_payload and self.tool_payload is not None:
            payload["tool_payload"] = self.tool_payload
        return payload


@dataclass(slots=True)
class ChatSession:
    session_id: str
    status: str = "active"
    requirement_session_id: str | None = None
    policy_id: str | None = None
    pending_confirmation: bool = False
    pending_option_selection: bool = False
    policy_options: dict[str, str] = field(default_factory=dict)
    turns: list[ChatTurn] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, *, include_tool_payload: bool = True) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "requirement_session_id": self.requirement_session_id,
            "policy_id": self.policy_id,
            "pending_confirmation": self.pending_confirmation,
            "pending_option_selection": self.pending_option_selection,
            "policy_options": dict(self.policy_options),
            "turns": [
                turn.to_dict(include_tool_payload=include_tool_payload) for turn in self.turns
            ],
            "tool_trace": list(self.tool_trace),
            "created_at": round(self.created_at, 4),
            "updated_at": round(self.updated_at, 4),
        }
