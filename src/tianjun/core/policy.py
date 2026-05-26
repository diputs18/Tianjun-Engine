from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..domain import round_payload

WorkloadType = Literal["inference", "training", "streaming", "analytics", "batch"]
SecurityLevel = Literal["low", "medium", "high"]
RequirementPriority = Literal["latency", "cost", "quality", "balanced", "security"]
PolicyStatus = Literal["draft", "simulated", "approved", "committed", "failed"]
FeedbackTarget = Literal["overall", "latency", "cost", "qos", "security", "module", "workflow"]
FeedbackSentiment = Literal["positive", "negative", "neutral"]


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


@dataclass(slots=True)
class UserRequirement:
    objective: str
    workload_type: WorkloadType
    region_preference: list[str] = field(default_factory=list)
    cpu_cores: float | None = None
    memory_gb: float | None = None
    gpu_count: int | None = None
    latency_target_ms: float | None = None
    bandwidth_mbps: float | None = None
    budget_limit: float | None = None
    security_level: SecurityLevel = "medium"
    priority: RequirementPriority = "balanced"
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0
    deployment: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserRequirement":
        return cls(
            objective=str(data.get("objective", "")),
            workload_type=_workload_type(data.get("workload_type", "batch")),
            region_preference=_str_list(data.get("region_preference")),
            cpu_cores=_optional_float(data.get("cpu_cores")),
            memory_gb=_optional_float(data.get("memory_gb")),
            gpu_count=_optional_int(data.get("gpu_count")),
            latency_target_ms=_optional_float(data.get("latency_target_ms")),
            bandwidth_mbps=_optional_float(data.get("bandwidth_mbps")),
            budget_limit=_optional_float(data.get("budget_limit")),
            security_level=_security_level(data.get("security_level", "medium")),
            priority=_priority(data.get("priority", "balanced")),
            missing_fields=_str_list(data.get("missing_fields")),
            confidence=float(data.get("confidence", 0.0)),
            deployment=dict(data.get("deployment", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "objective": self.objective,
                "workload_type": self.workload_type,
                "region_preference": list(self.region_preference),
                "cpu_cores": self.cpu_cores,
                "memory_gb": self.memory_gb,
                "gpu_count": self.gpu_count,
                "latency_target_ms": self.latency_target_ms,
                "bandwidth_mbps": self.bandwidth_mbps,
                "budget_limit": self.budget_limit,
                "security_level": self.security_level,
                "priority": self.priority,
                "missing_fields": list(self.missing_fields),
                "confidence": self.confidence,
                "deployment": dict(self.deployment),
            }
        )


@dataclass(slots=True)
class ComputeSelection:
    node_id: str | None
    region: str | None
    labels: list[str] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "node_id": self.node_id,
                "region": self.region,
                "labels": list(self.labels),
                "score": self.score,
                "reason": self.reason,
            }
        )


@dataclass(slots=True)
class NetworkSelection:
    source_region: str | None
    target_region: str | None
    stable_latency_ms: float | None
    guaranteed_bandwidth_mbps: float | None
    delivery_probability: float
    risk_score: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "source_region": self.source_region,
                "target_region": self.target_region,
                "stable_latency_ms": self.stable_latency_ms,
                "guaranteed_bandwidth_mbps": self.guaranteed_bandwidth_mbps,
                "delivery_probability": self.delivery_probability,
                "risk_score": self.risk_score,
            }
        )


@dataclass(slots=True)
class ResourceConfig:
    cpu_cores: float
    memory_gb: float
    gpu_count: int
    storage_gb: float
    executor_mode: str = "noop"

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "cpu_cores": self.cpu_cores,
                "memory_gb": self.memory_gb,
                "gpu_count": self.gpu_count,
                "storage_gb": self.storage_gb,
                "executor_mode": self.executor_mode,
            }
        )


@dataclass(slots=True)
class QoSConfig:
    latency_target_ms: float | None
    bandwidth_mbps: float | None
    priority: RequirementPriority
    sla_probability: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "latency_target_ms": self.latency_target_ms,
                "bandwidth_mbps": self.bandwidth_mbps,
                "priority": self.priority,
                "sla_probability": self.sla_probability,
            }
        )


@dataclass(slots=True)
class SecurityConfig:
    isolation_level: Literal["none", "process", "container", "namespace"]
    data_residency: list[str] = field(default_factory=list)
    allowed_regions: list[str] = field(default_factory=list)
    forbidden_nodes: list[str] = field(default_factory=list)
    require_encrypted_transport: bool = True
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "isolation_level": self.isolation_level,
                "data_residency": list(self.data_residency),
                "allowed_regions": list(self.allowed_regions),
                "forbidden_nodes": list(self.forbidden_nodes),
                "require_encrypted_transport": self.require_encrypted_transport,
                "risk_score": self.risk_score,
            }
        )


@dataclass(slots=True)
class LoadEffect:
    current_load: float
    projected_load: float
    load_balance_score: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "current_load": self.current_load,
                "projected_load": self.projected_load,
                "load_balance_score": self.load_balance_score,
            }
        )


@dataclass(slots=True)
class LatencyEffect:
    target_ms: float | None
    expected_ms: float | None
    transfer_ticks: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "target_ms": self.target_ms,
                "expected_ms": self.expected_ms,
                "transfer_ticks": self.transfer_ticks,
                "confidence": self.confidence,
            }
        )


@dataclass(slots=True)
class CostEffect:
    expected_cost: float
    budget_limit: float | None
    budget_margin: float | None
    cost_score: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "expected_cost": self.expected_cost,
                "budget_limit": self.budget_limit,
                "budget_margin": self.budget_margin,
                "cost_score": self.cost_score,
            }
        )


@dataclass(slots=True)
class QoSEffect:
    sla_probability: float
    reliability_score: float
    service_quality_score: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "sla_probability": self.sla_probability,
                "reliability_score": self.reliability_score,
                "service_quality_score": self.service_quality_score,
            }
        )


@dataclass(slots=True)
class SecurityEffect:
    security_level: SecurityLevel
    security_score: float
    violation_penalty: float
    risk_score: float

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "security_level": self.security_level,
                "security_score": self.security_score,
                "violation_penalty": self.violation_penalty,
                "risk_score": self.risk_score,
            }
        )


@dataclass(slots=True)
class ExpectedEffect:
    load: LoadEffect
    latency: LatencyEffect
    cost: CostEffect
    service_quality: QoSEffect
    security: SecurityEffect

    def to_dict(self) -> dict[str, Any]:
        return {
            "load": self.load.to_dict(),
            "latency": self.latency.to_dict(),
            "cost": self.cost.to_dict(),
            "service_quality": self.service_quality.to_dict(),
            "security": self.security.to_dict(),
        }


@dataclass(slots=True)
class PolicyExplanation:
    summary: str
    factors: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "factors": list(self.factors),
            "risks": list(self.risks),
            "questions": list(self.questions),
        }


@dataclass(slots=True)
class ComputeNetworkPolicy:
    policy_id: str
    requirement: UserRequirement
    selected_compute: ComputeSelection
    selected_network: NetworkSelection
    resource_config: ResourceConfig
    qos_config: QoSConfig
    security_config: SecurityConfig
    expected_effect: ExpectedEffect
    explanation: PolicyExplanation
    status: PolicyStatus = "draft"
    task_id: str | None = None
    decision: dict[str, Any] | None = None
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "status": self.status,
            "task_id": self.task_id,
            "created_at": round(self.created_at, 4),
            "requirement": self.requirement.to_dict(),
            "selected_compute": self.selected_compute.to_dict(),
            "selected_network": self.selected_network.to_dict(),
            "resource_config": self.resource_config.to_dict(),
            "qos_config": self.qos_config.to_dict(),
            "security_config": self.security_config.to_dict(),
            "expected_effect": self.expected_effect.to_dict(),
            "functional_components": self.functional_components(),
            "explanation": self.explanation.to_dict(),
            "decision": self.decision,
        }

    def functional_components(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "compute",
                "name": self.selected_compute.node_id or "unassigned",
                "region": self.selected_compute.region,
                "reason": self.selected_compute.reason,
            },
            {
                "type": "network",
                "name": "stable_path",
                "source_region": self.selected_network.source_region,
                "target_region": self.selected_network.target_region,
                "stable_latency_ms": self.selected_network.stable_latency_ms,
                "guaranteed_bandwidth_mbps": self.selected_network.guaranteed_bandwidth_mbps,
            },
            {
                "type": "qos",
                "name": self.qos_config.priority,
                "latency_target_ms": self.qos_config.latency_target_ms,
                "sla_probability": self.qos_config.sla_probability,
            },
            {
                "type": "security",
                "name": self.security_config.isolation_level,
                "data_residency": list(self.security_config.data_residency),
                "encrypted_transport": self.security_config.require_encrypted_transport,
            },
            {
                "type": "executor",
                "name": self.resource_config.executor_mode,
                "cpu_cores": self.resource_config.cpu_cores,
                "memory_gb": self.resource_config.memory_gb,
                "gpu_count": self.resource_config.gpu_count,
            },
        ]


@dataclass(slots=True)
class PolicySimulationResult:
    policy_id: str
    feasible: bool
    status: str
    expected: ExpectedEffect
    risks: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "feasible": self.feasible,
            "status": self.status,
            "expected": self.expected.to_dict(),
            "risks": list(self.risks),
            "questions": list(self.questions),
            "diagnostics": round_payload(self.diagnostics),
        }


@dataclass(slots=True)
class UserFeedback:
    policy_id: str
    target: FeedbackTarget
    sentiment: FeedbackSentiment
    instruction: str
    preference_delta: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserFeedback":
        return cls(
            policy_id=str(data["policy_id"]),
            target=_feedback_target(data.get("target", "overall")),
            sentiment=_feedback_sentiment(data.get("sentiment", "neutral")),
            instruction=str(data.get("instruction", "")),
            preference_delta={
                str(key): float(value)
                for key, value in dict(data.get("preference_delta", {})).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return round_payload(
            {
                "policy_id": self.policy_id,
                "target": self.target,
                "sentiment": self.sentiment,
                "instruction": self.instruction,
                "preference_delta": dict(self.preference_delta),
            }
        )


def _workload_type(value: Any) -> WorkloadType:
    allowed = {"inference", "training", "streaming", "analytics", "batch"}
    text = str(value or "batch")
    return text if text in allowed else "batch"  # type: ignore[return-value]


def _security_level(value: Any) -> SecurityLevel:
    text = str(value or "medium")
    return text if text in {"low", "medium", "high"} else "medium"  # type: ignore[return-value]


def _priority(value: Any) -> RequirementPriority:
    text = str(value or "balanced")
    allowed = {"latency", "cost", "quality", "balanced", "security"}
    return text if text in allowed else "balanced"  # type: ignore[return-value]


def _feedback_target(value: Any) -> FeedbackTarget:
    text = str(value or "overall")
    allowed = {"overall", "latency", "cost", "qos", "security", "module", "workflow"}
    return text if text in allowed else "overall"  # type: ignore[return-value]


def _feedback_sentiment(value: Any) -> FeedbackSentiment:
    text = str(value or "neutral")
    return text if text in {"positive", "negative", "neutral"} else "neutral"  # type: ignore[return-value]
