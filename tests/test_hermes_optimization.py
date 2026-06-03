from __future__ import annotations

from tianjun.core import UserFeedback
from tianjun.domain import Node, ResourceVector
from tianjun.policy.clarifier import clarification_questions
from tianjun.policy.feedback import parse_feedback_instruction
from tianjun.policy.generator import ComputeNetworkPolicyGenerator


def generator() -> ComputeNetworkPolicyGenerator:
    return ComputeNetworkPolicyGenerator()


def test_implicit_workload_language_is_classified_without_llm() -> None:
    policy = generator()
    assert policy.parse_requirement("上海搞个在线问答服务").workload_type == "inference"
    assert policy.parse_requirement("北京帮我跑个 embedding").workload_type == "inference"
    assert policy.parse_requirement("深圳做一批批量打标签").workload_type == "analytics"


def test_region_aliases_short_codes_and_typo_recovery_are_supported() -> None:
    policy = generator()
    assert policy.parse_requirement("苏州部署在线服务").region_preference == ["east"]
    assert policy.parse_requirement("在 cd 部署在线服务").region_preference == ["west"]
    assert policy.parse_requirement("部署在成嘟的在线服务").region_preference == ["west"]
    assert policy.parse_requirement("武汉部署在线服务").region_preference == ["wuhan"]


def test_multi_objective_priority_vector_reaches_scheduler_metrics() -> None:
    policy = generator()
    requirement = policy.parse_requirement("上海在线问答服务，低时延但不能超预算，预算 20 万元")
    assert requirement.priority == "latency"
    assert requirement.priority_vector["latency"] > 0
    assert requirement.priority_vector["cost"] > 0
    task = policy.task_from_requirement(requirement, task_id="intent-vector")
    assert task.intent_weights["performance"] > 0
    assert task.intent_weights["network"] > 0
    assert task.intent_weights["cost"] > 0


def test_weighted_slot_confidence_reflects_missing_inference_latency() -> None:
    policy = generator()
    missing_latency = policy.parse_requirement("上海部署低时延在线问答服务")
    explicit_latency = policy.parse_requirement("上海部署低时延在线问答服务，响应低于 50ms")
    assert "latency_target_ms" in missing_latency.missing_fields
    assert explicit_latency.confidence > missing_latency.confidence
    assert missing_latency.slot_confidence["latency_target_ms"] == 0.0
    assert explicit_latency.slot_confidence["latency_target_ms"] == 1.0


def test_feedback_uses_real_metric_keys_and_intensity() -> None:
    slight = parse_feedback_instruction(policy_id="p", instruction="响应稍微慢了一点")
    severe = parse_feedback_instruction(policy_id="p", instruction="响应完全无法接受，太慢了")
    assert set(slight["preference_delta"]).issubset({"performance", "completion", "network"})
    assert severe["preference_delta"]["performance"] > slight["preference_delta"]["performance"]
    locality = parse_feedback_instruction(policy_id="p", instruction="数据不在本地，需要就近调度")
    assert locality["preference_delta"]["locality"] > 0


def test_feedback_metric_preferences_reach_task_weights() -> None:
    policy = generator()
    requirement = policy.parse_requirement("上海分析任务，4 核 CPU")
    payload = parse_feedback_instruction(policy_id="p", instruction="节点负载太高了，需要更均衡")
    feedback = UserFeedback.from_dict(payload)
    optimized = policy.apply_feedback(requirement, feedback)
    task = policy.task_from_requirement(optimized, task_id="feedback-vector")
    assert optimized.metric_preferences["balance"] > 0
    assert task.intent_weights["balance"] > 0


def test_clarification_prioritizes_unavailable_region_relaxation() -> None:
    policy = generator()
    requirement = policy.parse_requirement("武汉部署低时延在线问答服务")
    node = Node(
        node_id="east-a",
        region="dc1",
        location="shanghai",
        capacity=ResourceVector(cpu=8, memory=32, storage=100),
    )
    questions = clarification_questions(requirement, [node])
    assert questions[0].startswith("当前在线节点无法满足地域")
