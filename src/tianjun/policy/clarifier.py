from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..core import UserRequirement


FIELD_QUESTIONS: dict[str, str] = {
    "workload_type": "请确认业务类型：推理、训练、流式、分析还是批处理？",
    "region_preference": "请确认部署地域或数据驻留要求，例如上海、北京、深圳、成都等。",
    "latency_target_ms": "请给出端到端时延目标，例如 50ms；没有硬性要求也可以说明“无硬性时延”。",
    "budget_limit": "请给出单次任务或服务周期预算上限；如果只是要求低成本，也请说明可接受范围。",
    "security_level": "请确认安全等级：低、中、高；高安全会启用更强隔离和加密约束。",
}


@dataclass(slots=True)
class ConversationTurn:
    role: str
    content: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "created_at": round(self.created_at, 4),
        }


@dataclass(slots=True)
class RequirementSession:
    session_id: str
    requirement: UserRequirement
    turns: list[ConversationTurn] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    status: str = "needs_clarification"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "requirement": self.requirement.to_dict(),
            "questions": list(self.questions),
            "turns": [turn.to_dict() for turn in self.turns],
            "created_at": round(self.created_at, 4),
            "updated_at": round(self.updated_at, 4),
        }


def clarification_questions(requirement: UserRequirement) -> list[str]:
    """Return deduplicated questions for multi-turn slot filling."""
    questions: list[str] = []
    workload_unspecified = bool(requirement.deployment.get("workload_type_unspecified"))
    additional_constraints_declined = bool(requirement.deployment.get("additional_constraints_declined"))
    for field_name in requirement.missing_fields:
        question = FIELD_QUESTIONS.get(field_name)
        if question and question not in questions:
            questions.append(question)

    if requirement.confidence < 0.62 and not workload_unspecified and not questions:
        fallback = "当前需求识别置信度较低，请补充业务类型、地域、资源规格、时延、预算或安全约束中的关键信息。"
        if fallback not in questions:
            questions.append(fallback)

    if workload_unspecified and not questions and not additional_constraints_declined:
        questions.append("任务类型已选择不指定；我将使用通用资源画像继续预演。补充任务类型、资源规格或 SLA 可提高推荐精度，但不是必填项。")

    if not questions and requirement.priority == "balanced" and not additional_constraints_declined:
        questions.append("是否需要优先优化某个目标：时延、成本、服务质量或安全？")
    return questions


def session_status(requirement: UserRequirement, questions: list[str]) -> str:
    workload_unspecified = bool(requirement.deployment.get("workload_type_unspecified"))
    if requirement.missing_fields:
        return "needs_clarification"
    if requirement.confidence < 0.62 and not workload_unspecified:
        return "needs_clarification"
    if questions:
        return "ready_with_optional_questions"
    return "ready"
