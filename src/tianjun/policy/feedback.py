from __future__ import annotations

import re
from typing import Any

FeedbackPayload = dict[str, Any]

_TARGET_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("latency", ("延迟", "时延", "响应", "实时", "卡顿", "latency", "slow", "ms")),
    ("cost", ("成本", "预算", "费用", "便宜", "贵", "降本", "cost", "budget", "cheap")),
    ("security", ("安全", "隔离", "加密", "合规", "权限", "密钥", "security", "secure")),
    ("qos", ("质量", "可靠", "稳定", "sla", "成功率", "可用性", "qos", "reliable")),
    ("workflow", ("流程", "步骤", "审批", "确认", "自动", "workflow", "process")),
    ("module", ("模块", "组件", "调度器", "模型", "网络", "算力", "component", "module")),
]

_NEGATIVE_WORDS = (
    "太高",
    "太慢",
    "太贵",
    "不满意",
    "不行",
    "失败",
    "不稳定",
    "风险",
    "降低",
    "减少",
    "优化",
    "高了",
    "慢",
    "贵",
    "bad",
    "worse",
    "failed",
)
_POSITIVE_WORDS = (
    "满意",
    "可以",
    "不错",
    "达标",
    "接受",
    "保持",
    "ok",
    "good",
    "fine",
)


def parse_feedback_instruction(
    *,
    policy_id: str,
    instruction: str,
    target: str | None = None,
    sentiment: str | None = None,
    preference_delta: dict[str, float] | None = None,
) -> FeedbackPayload:
    """Normalize free-form user feedback into the strict UserFeedback schema.

    This is deliberately deterministic for the prototype. An LLM may call this tool with only
    `instruction`; the control plane will infer target/sentiment/weight deltas and keep the
    normalized payload auditable.
    """
    text = " ".join(str(instruction or "").strip().split())
    if not text:
        raise ValueError("feedback instruction must not be empty")

    resolved_target = _valid_target(target) or _infer_target(text)
    resolved_sentiment = _valid_sentiment(sentiment) or _infer_sentiment(text)
    deltas = _infer_deltas(text, resolved_target, resolved_sentiment)
    for key, value in (preference_delta or {}).items():
        deltas[str(key)] = float(value)

    return {
        "policy_id": str(policy_id),
        "target": resolved_target,
        "sentiment": resolved_sentiment,
        "instruction": text,
        "preference_delta": deltas,
    }


def _infer_target(text: str) -> str:
    lower = text.lower()
    best_target = "overall"
    best_count = 0
    for target, keywords in _TARGET_KEYWORDS:
        count = sum(1 for keyword in keywords if (keyword.lower() in lower if keyword.isascii() else keyword in text))
        if count > best_count:
            best_target = target
            best_count = count
    return best_target


def _infer_sentiment(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in _NEGATIVE_WORDS if word.isascii()) or any(
        word in text for word in _NEGATIVE_WORDS if not word.isascii()
    ):
        return "negative"
    if any(word in lower for word in _POSITIVE_WORDS if word.isascii()) or any(
        word in text for word in _POSITIVE_WORDS if not word.isascii()
    ):
        return "positive"
    return "neutral"


def _infer_deltas(text: str, target: str, sentiment: str) -> dict[str, float]:
    direction = 1.0 if sentiment != "positive" else 0.5
    deltas: dict[str, float] = {}
    if target == "latency":
        deltas["latency_weight"] = 0.22 * direction
        if any(word in text for word in ("成本增加", "预算增加", "可以接受成本", "可以加钱")):
            deltas["cost_weight"] = -0.08
        elif any(word in text for word in ("不能加钱", "预算不变", "成本不能涨")):
            deltas["cost_weight"] = 0.08
    elif target == "cost":
        deltas["cost_weight"] = 0.22 * direction
        if any(word in text for word in ("不能影响时延", "时延不变", "SLA不变", "sla不变")):
            deltas["latency_weight"] = 0.08
            deltas["quality_weight"] = 0.08
    elif target == "security":
        deltas["security_weight"] = 0.22 * direction
    elif target == "qos":
        deltas["quality_weight"] = 0.22 * direction
        if any(word in text for word in ("网络", "抖动", "丢包")):
            deltas["network_weight"] = 0.10
    elif target == "workflow":
        deltas["workflow_weight"] = 0.18 * direction
    elif target == "module":
        deltas["module_weight"] = 0.18 * direction

    percentage = _percentage(text)
    if percentage is not None:
        deltas[f"{target}_change_ratio"] = percentage
    return deltas


def _percentage(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return None if match is None else float(match.group(1)) / 100.0


def _valid_target(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text if text in {"overall", "latency", "cost", "qos", "security", "module", "workflow"} else None


def _valid_sentiment(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text if text in {"positive", "negative", "neutral"} else None
