from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any

from ..core import (
    ComputeNetworkPolicy,
    ComputeSelection,
    CostEffect,
    ExpectedEffect,
    LatencyEffect,
    LoadEffect,
    NetworkSelection,
    PolicyExplanation,
    QoSConfig,
    QoSEffect,
    ResourceConfig,
    SecurityConfig,
    SecurityEffect,
    UserFeedback,
    UserRequirement,
)
from ..domain import ExecutionMode, Node, ResourceVector, SchedulingDecision, Task, TaskExecutionSpec, clamp
from ..scheduling.engine import ClosedLoopAdaptiveScheduler


REGION_ALIASES = {
    "华东": "shanghai",
    "上海": "shanghai",
    "杭州": "hangzhou",
    "华北": "beijing",
    "北京": "beijing",
    "华南": "shenzhen",
    "深圳": "shenzhen",
    "广州": "guangzhou",
    "东莞": "dongguan",
    "惠州": "huizhou",
    "珠海": "zhuhai",
    "佛山": "foshan",
    "中山": "zhongshan",
    "成都": "chengdu",
    "武汉": "wuhan",
    "西南": "chengdu",
    "华中": "wuhan",
    "华东": "shanghai",
    "上海": "shanghai",
    "杭州": "hangzhou",
    "华北": "beijing",
    "北京": "beijing",
    "华南": "shenzhen",
    "深圳": "shenzhen",
    "广州": "guangzhou",
    "东莞": "dongguan",
    "惠州": "huizhou",
    "珠海": "zhuhai",
    "佛山": "foshan",
    "中山": "zhongshan",
    "成都": "chengdu",
    "武汉": "wuhan",
    "西南": "chengdu",
    "华中": "wuhan",
    "east china": "shanghai",
    "shanghai": "shanghai",
    "hangzhou": "hangzhou",
    "beijing": "beijing",
    "shenzhen": "shenzhen",
    "guangzhou": "guangzhou",
    "dongguan": "dongguan",
    "huizhou": "huizhou",
    "zhuhai": "zhuhai",
    "foshan": "foshan",
    "zhongshan": "zhongshan",
    "chengdu": "chengdu",
    "wuhan": "wuhan",
}

GUANGDONG_REGIONS = ["shenzhen", "guangzhou", "dongguan", "huizhou", "zhuhai", "foshan", "zhongshan"]


class ComputeNetworkPolicyGenerator:
    def __init__(self, default_execution_mode: ExecutionMode = ExecutionMode.NOOP) -> None:
        self.default_execution_mode = default_execution_mode

    def parse_requirement(
        self,
        message: str,
        overrides: dict[str, Any] | None = None,
    ) -> UserRequirement:
        text = " ".join(str(message or "").strip().split())
        if not text:
            raise ValueError("requirement message must not be empty")
        data: dict[str, Any] = {
            "objective": text,
            "workload_type": self._workload_type(text),
            "region_preference": self._regions(text),
            "cpu_cores": self._cpu_cores(text),
            "memory_gb": self._memory(text),
            "gpu_count": self._gpu_count(text),
            "latency_target_ms": self._latency_ms(text),
            "bandwidth_mbps": self._bandwidth_mbps(text),
            "budget_limit": self._budget_limit(text),
            "security_level": self._security_level(text),
            "priority": self._priority(text),
            "deployment": self._deployment_spec(text),
        }
        if overrides:
            data.update({key: value for key, value in overrides.items() if value is not None and not str(key).startswith("__")})
        self._apply_explicit_gpu_exclusion(data, text)
        self._apply_workload_type_preference(data, text)
        self._apply_region_preference(data, text)
        return self.finalize_requirement(data, evidence_text=text)

    def merge_requirement_update(
        self,
        base: UserRequirement,
        message: str,
        overrides: dict[str, Any] | None = None,
    ) -> UserRequirement:
        """Merge one conversational answer into an existing requirement.

        The update may be a short answer such as "上海，预算 20，时延 80ms".
        We only override fields when the new answer contains explicit evidence, so a
        terse clarification cannot accidentally reset the workload to the default batch type.
        """
        text = " ".join(str(message or "").strip().split())
        if not text:
            raise ValueError("requirement update message must not be empty")
        parsed = self.parse_requirement(text, overrides=overrides)
        force_replacement = bool((overrides or {}).get("__clear_prior_constraints"))
        if force_replacement or self._is_replacement_update(text):
            data = parsed.to_dict()
            data["objective"] = text
            if self._cpu_only_update(text):
                data["workload_type"] = "batch"
                data["gpu_count"] = 0
                data["latency_target_ms"] = None
                data["bandwidth_mbps"] = None
                data["budget_limit"] = None
                data["security_level"] = "medium"
                data["priority"] = "balanced"
                data["deployment"] = {}
            if overrides:
                data.update({key: value for key, value in overrides.items() if value is not None and not str(key).startswith("__")})
            self._apply_explicit_gpu_exclusion(data, text)
            self._apply_workload_type_preference(data, text)
            self._apply_region_preference(data, text)
            return self.finalize_requirement(data, evidence_text=text)

        data = base.to_dict()
        data["objective"] = f"{base.objective} | 用户补充: {text}"

        if parsed.workload_type != "batch" or self._has_explicit_batch_intent(text) or self._explicitly_omits_workload_type(text):
            data["workload_type"] = parsed.workload_type
        if parsed.region_preference:
            data["region_preference"] = parsed.region_preference
        for field in ("cpu_cores", "memory_gb", "gpu_count", "latency_target_ms", "bandwidth_mbps", "budget_limit"):
            value = getattr(parsed, field)
            if value is not None:
                data[field] = value
        if parsed.deployment:
            data["deployment"] = self._merge_deployment(dict(data.get("deployment") or {}), parsed.deployment)
        if self._mentions_security(text):
            data["security_level"] = parsed.security_level
        if parsed.priority != "balanced" or base.priority == "balanced":
            data["priority"] = parsed.priority

        if overrides:
            data.update({key: value for key, value in overrides.items() if value is not None and not str(key).startswith("__")})
        self._apply_explicit_gpu_exclusion(data, text)
        self._apply_workload_type_preference(data, text)
        self._apply_region_preference(data, text)
        return self.finalize_requirement(data, evidence_text=data["objective"])

    def _is_replacement_update(self, text: str) -> bool:
        lower = text.lower()
        reset_markers = (
            "这些需求都不需要",
            "以上需求都不需要",
            "之前的需求都不需要",
            "之前约束都不要",
            "清空之前",
            "重新开始",
            "从头开始",
            "不要任何多余需求",
            "不需要任何多余需求",
            "只需要有cpu",
            "只要cpu",
            "仅需cpu",
            "only cpu",
            "cpu only",
        )
        if any(marker in lower or marker in text for marker in reset_markers):
            return True
        # A terse confirmation after the assistant asked whether to clear previous constraints should be treated
        # as a replacement when it contains a complete simple target, e.g. “是的，现在1核，上海即可”.
        confirm_reset = any(token in text for token in ("是的", "对", "确认", "可以"))
        simple_cpu_target = self._cpu_cores(text) is not None and bool(self._regions(text))
        no_complex_terms = not any(
            term in lower or term in text
            for term in ("gpu", "h100", "h800", "a100", "rdma", "nvlink", "kms", "sm4", "sm2", "等保", "金融", "lustre", "cpfs")
        )
        return confirm_reset and simple_cpu_target and no_complex_terms

    def _cpu_only_update(self, text: str) -> bool:
        lower = text.lower()
        return any(
            marker in lower or marker in text
            for marker in ("只需要有cpu", "只要cpu", "仅需cpu", "cpu即可", "only cpu", "cpu only")
        ) or (self._cpu_cores(text) is not None and not self._mentions_gpu_or_accelerator(text))

    def _mentions_gpu_or_accelerator(self, text: str) -> bool:
        lower = text.lower()
        return any(term in lower for term in ("gpu", "h100", "h800", "a100", "a800", "nvlink", "cuda")) or "显卡" in text

    def _apply_explicit_gpu_exclusion(self, data: dict[str, Any], text: str) -> None:
        if self._gpu_count(text) != 0:
            return
        data["gpu_count"] = 0
        deployment = dict(data.get("deployment") or {})
        for key in (
            "gpu_model",
            "acceptable_gpu_models",
            "gpu_memory_gb",
            "gpu_per_node",
            "cluster_gpu_count",
            "initial_gpu_count",
            "target_gpu_count",
            "nvlink_required",
        ):
            deployment.pop(key, None)
        gpu_labels = {"gpu", "a100", "a800", "h100", "h800", "v100", "t4", "l40s", "nvlink", "cuda"}
        labels = [
            label
            for label in deployment.get("required_node_labels", [])
            if str(label).lower() not in gpu_labels
        ]
        if labels:
            deployment["required_node_labels"] = labels
        else:
            deployment.pop("required_node_labels", None)
        any_labels = dict(deployment.get("required_any_node_labels") or {})
        any_labels.pop("gpu_model", None)
        if any_labels:
            deployment["required_any_node_labels"] = any_labels
        else:
            deployment.pop("required_any_node_labels", None)
        data["deployment"] = deployment

    def _apply_workload_type_preference(self, data: dict[str, Any], text: str) -> None:
        deployment = dict(data.get("deployment") or {})
        if self._bare_node_request(text):
            data["workload_type"] = "batch"
            deployment.pop("workload_type_unspecified", None)
            data["deployment"] = deployment
            return
        if (
            self._explicitly_omits_workload_type(text)
            or self._declines_additional_constraints(text)
            or self._generic_node_request_without_workload(text)
        ):
            # Scheduling needs a resource profile; use a transparent baseline
            # without presenting it as a user-selected workload type.
            data["workload_type"] = "batch"
            deployment["workload_type_unspecified"] = True
            if self._declines_additional_constraints(text):
                deployment["additional_constraints_declined"] = True
            data["deployment"] = deployment
            return
        if self._has_explicit_workload_intent(text):
            deployment.pop("workload_type_unspecified", None)
            data["deployment"] = deployment

    def _apply_region_preference(self, data: dict[str, Any], text: str) -> None:
        deployment = dict(data.get("deployment") or {})
        if self._bare_node_request(text):
            data["region_preference"] = []
            deployment.pop("region_unspecified", None)
            data["deployment"] = deployment
            return
        if self._explicitly_omits_region_preference(text) or self._declines_additional_constraints(text):
            data["region_preference"] = []
            deployment["region_unspecified"] = True
            if self._declines_additional_constraints(text):
                deployment["additional_constraints_declined"] = True
            data["deployment"] = deployment
            return
        explicit_regions = self._regions(text)
        if explicit_regions:
            # A region explicitly named by the user is authoritative. An LLM
            # slot suggestion must never silently substitute an available city.
            data["region_preference"] = explicit_regions
            deployment.pop("region_unspecified", None)
            data["deployment"] = deployment

    def _merge_deployment(self, base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        model_labels = {"a100", "a800", "h100", "h800", "v100", "t4", "l40s"}
        for key, value in update.items():
            if value in (None, [], {}):
                continue
            if key == "required_node_labels":
                existing = [str(item).lower() for item in merged.get(key, [])]
                incoming = [str(item).lower() for item in value]
                if any(item in model_labels for item in incoming):
                    existing = [item for item in existing if item not in model_labels]
                combined: list[str] = []
                for item in [*existing, *incoming]:
                    if item not in combined:
                        combined.append(item)
                merged[key] = combined
            elif key in {"acceptable_gpu_models", "acceptable_shared_fs"}:
                existing = [str(item) for item in merged.get(key, [])]
                combined = []
                for item in [*existing, *list(value)]:
                    if item not in combined:
                        combined.append(item)
                merged[key] = combined
            elif key in {"capacity_policy", "compliance", "required_any_node_labels"}:
                nested = dict(merged.get(key) or {})
                for sub_key, sub_value in dict(value).items():
                    if isinstance(sub_value, list):
                        current = list(nested.get(sub_key, []))
                        for item in sub_value:
                            if item not in current:
                                current.append(item)
                        nested[sub_key] = current
                    else:
                        nested[sub_key] = sub_value
                merged[key] = nested
            else:
                merged[key] = value
        return merged

    def finalize_requirement(self, data: dict[str, Any], *, evidence_text: str) -> UserRequirement:
        missing_fields = []
        region_unspecified = bool(dict(data.get("deployment") or {}).get("region_unspecified"))
        if not data.get("region_preference") and not region_unspecified:
            missing_fields.append("region_preference")
        if data.get("latency_target_ms") is None and data.get("priority") == "latency":
            missing_fields.append("latency_target_ms")
        if data.get("budget_limit") is None and data.get("priority") == "cost":
            missing_fields.append("budget_limit")
        workload_unspecified = bool(dict(data.get("deployment") or {}).get("workload_type_unspecified"))
        if data.get("workload_type") == "batch" and not workload_unspecified and not self._has_explicit_batch_intent(str(evidence_text)):
            has_explicit_resource = any(data.get(key) is not None for key in ("cpu_cores", "memory_gb", "gpu_count"))
            has_deployment_detail = bool(data.get("deployment"))
            # A terse request such as “上海 1 核 CPU” is a valid CPU batch task; do not force
            # the user to redundantly say “批处理”. Keep asking only when the workload truly
            # cannot be inferred from any resource evidence.
            if not has_explicit_resource and not has_deployment_detail:
                missing_fields.append("workload_type")

        # If the user explicitly provides CPU resources and does not mention any accelerator,
        # treat the task as CPU-only. This prevents a simple request such as
        # “上海，训练，单核” from inheriting the training default of 1 GPU.
        if (
            data.get("gpu_count") is None
            and data.get("cpu_cores") is not None
            and not self._mentions_gpu_or_accelerator(str(evidence_text))
        ):
            data["gpu_count"] = 0
            data["deployment"] = {
                key: value
                for key, value in dict(data.get("deployment") or {}).items()
                if key not in {
                    "gpu_model",
                    "acceptable_gpu_models",
                    "required_node_labels",
                    "required_any_node_labels",
                    "gpu_memory_gb",
                    "nvlink_required",
                }
            }

        confidence = 0.42
        if data.get("workload_type") and not (data.get("workload_type") == "batch" and "workload_type" in missing_fields):
            confidence += 0.10
        for key in ("region_preference", "latency_target_ms", "budget_limit", "security_level", "priority"):
            if data.get(key):
                confidence += 0.08
        if data.get("cpu_cores") is not None or data.get("memory_gb") is not None or data.get("gpu_count") is not None:
            confidence += 0.06
        confidence -= len(missing_fields) * 0.06
        data["missing_fields"] = missing_fields
        data["confidence"] = clamp(confidence, 0.30, 0.97)
        return UserRequirement.from_dict(data)

    def draft_policy(
        self,
        requirement: UserRequirement,
        *,
        scheduler: ClosedLoopAdaptiveScheduler,
        nodes: Iterable[Node],
        current_tick: int,
        policy_id: str | None = None,
        execution: TaskExecutionSpec | None = None,
    ) -> tuple[ComputeNetworkPolicy, Task]:
        policy_id = policy_id or self._new_policy_id()
        task = self.task_from_requirement(requirement, task_id=f"task_{policy_id}", execution=execution)
        node_list = list(nodes)
        decision = scheduler.select_node(task, node_list, current_tick=current_tick)
        node_by_id = {node.node_id: node for node in node_list}
        policy = self._policy_from_decision(policy_id, requirement, task, decision, node_by_id)
        return policy, task

    def task_from_requirement(
        self,
        requirement: UserRequirement,
        *,
        task_id: str,
        execution: TaskExecutionSpec | None = None,
    ) -> Task:
        defaults = self._effective_resource_defaults(requirement)
        cpu = requirement.cpu_cores if requirement.cpu_cores is not None else defaults["cpu"]
        memory = requirement.memory_gb if requirement.memory_gb is not None else defaults["memory"]
        gpu = requirement.gpu_count if requirement.gpu_count is not None else defaults["gpu"]
        storage = float(requirement.deployment.get("storage_gb") or defaults["storage"])
        preferred_labels = self._preferred_labels(requirement, gpu)
        preferred_labels.update(str(label).lower() for label in requirement.deployment.get("required_node_labels", []))
        priority = {
            "latency": 9,
            "quality": 8,
            "security": 8,
            "balanced": 6,
            "cost": 4,
        }[requirement.priority]
        task_type = "batch_cpu" if requirement.workload_type == "batch" else requirement.workload_type
        regions = list(requirement.region_preference)
        isolation_level = self._isolation_level(requirement.security_level)
        if execution is None:
            execution = TaskExecutionSpec(
                mode=self.default_execution_mode,
                simulation=self._simulation_spec(requirement),
            )
        elif execution.mode == ExecutionMode.SIMULATION and not execution.simulation:
            execution.simulation = self._simulation_spec(requirement)
        return Task(
            task_id=task_id,
            task_type=task_type,
            demand=ResourceVector(cpu=cpu, memory=memory, gpu=float(gpu), storage=storage),
            estimated_duration=defaults["duration"],
            priority=priority,
            budget=requirement.budget_limit,
            deadline=None,
            data_region=regions[0] if regions else None,
            source_region=regions[0] if regions else None,
            input_size_gb=defaults["input_size_gb"],
            max_latency_ms=requirement.latency_target_ms,
            min_bandwidth_mbps=requirement.bandwidth_mbps,
            network_sensitivity=0.9 if requirement.priority == "latency" else defaults["network_sensitivity"],
            preferred_labels=preferred_labels,
            security_level=requirement.security_level,
            isolation_level=isolation_level,
            allowed_regions=set(regions),
            forbidden_nodes=set(),
            require_encrypted_transport=requirement.security_level in {"medium", "high"},
            max_retries=1,
            execution=execution,
        )

    def apply_feedback(
        self,
        requirement: UserRequirement,
        feedback: UserFeedback,
    ) -> UserRequirement:
        data = requirement.to_dict()
        deltas = feedback.preference_delta
        instruction = feedback.instruction

        if feedback.target == "latency" or deltas.get("latency_weight", 0.0) > 0:
            data["priority"] = "latency"
            current = data.get("latency_target_ms")
            data["latency_target_ms"] = max(5.0, float(current) * 0.85) if current else 50.0
            increase = self._percentage(instruction)
            if increase and data.get("budget_limit") is not None:
                data["budget_limit"] = float(data["budget_limit"]) * (1.0 + increase)
        if feedback.target == "cost" or deltas.get("cost_weight", 0.0) > 0:
            data["priority"] = "cost"
            current_budget = data.get("budget_limit")
            if current_budget is not None:
                data["budget_limit"] = max(1.0, float(current_budget) * 0.9)
        if feedback.target == "security" or deltas.get("security_weight", 0.0) > 0:
            data["priority"] = "security"
            data["security_level"] = "high"
        if feedback.target == "qos" or deltas.get("quality_weight", 0.0) > 0:
            data["priority"] = "quality"

        data["objective"] = f"{requirement.objective} | feedback: {feedback.instruction}"
        data["missing_fields"] = []
        data["confidence"] = min(0.98, max(requirement.confidence, 0.72))
        return UserRequirement.from_dict(data)

    def _policy_from_decision(
        self,
        policy_id: str,
        requirement: UserRequirement,
        task: Task,
        decision: SchedulingDecision | None,
        node_by_id: dict[str, Node],
    ) -> ComputeNetworkPolicy:
        if decision is None:
            effects = self._empty_effects(requirement)
            diagnostic_risks = self._no_candidate_risks(requirement, task, list(node_by_id.values()))
            explanation = PolicyExplanation(
                summary="No feasible compute-network candidate matched the current requirement.",
                risks=diagnostic_risks,
                questions=["是否放宽地域、资源规格、网络能力、预算或安全合规约束？"],
            )
            return ComputeNetworkPolicy(
                policy_id=policy_id,
                requirement=requirement,
                selected_compute=ComputeSelection(node_id=None, region=None, reason="no_candidate"),
                selected_network=NetworkSelection(
                    source_region=task.source_region,
                    target_region=None,
                    stable_latency_ms=None,
                    guaranteed_bandwidth_mbps=None,
                    delivery_probability=0.0,
                    risk_score=1.0,
                ),
                resource_config=self._resource_config(task),
                qos_config=QoSConfig(
                    latency_target_ms=requirement.latency_target_ms,
                    bandwidth_mbps=requirement.bandwidth_mbps,
                    priority=requirement.priority,
                    sla_probability=0.0,
                ),
                security_config=self._security_config(requirement, None, 1.0),
                expected_effect=effects,
                explanation=explanation,
                status="failed",
                task_id=task.task_id,
                decision=None,
                created_at=time.time(),
            )

        node = node_by_id[decision.node_id]
        snapshot = decision.network_snapshot
        security_score = float(decision.metric_scores.get("security", 1.0))
        risk_score = clamp(1.0 - security_score)
        load_effect = LoadEffect(
            current_load=node.dominant_utilization(),
            projected_load=node.dominant_utilization_after(task.demand),
            load_balance_score=float(decision.metric_scores.get("balance", 0.0)),
        )
        latency_effect = LatencyEffect(
            target_ms=requirement.latency_target_ms,
            expected_ms=float(snapshot.get("stable_latency_ms", 0.0)),
            transfer_ticks=float(snapshot.get("transfer_ticks", 0.0)),
            confidence=float(snapshot.get("deterministic_confidence", 0.0)),
        )
        budget_margin = (
            None
            if requirement.budget_limit is None
            else float(requirement.budget_limit) - float(decision.predicted_cost)
        )
        cost_effect = CostEffect(
            expected_cost=float(decision.predicted_cost),
            budget_limit=requirement.budget_limit,
            budget_margin=budget_margin,
            cost_score=float(decision.metric_scores.get("cost", 0.0)),
        )
        reliability_score = float(decision.raw_metrics.get("reliability", 0.0))
        qos_effect = QoSEffect(
            sla_probability=clamp(reliability_score * float(snapshot.get("deterministic_confidence", 1.0))),
            reliability_score=reliability_score,
            service_quality_score=clamp(
                (float(decision.metric_scores.get("performance", 0.0)) * 0.35)
                + (float(decision.metric_scores.get("completion", 0.0)) * 0.25)
                + (float(decision.metric_scores.get("network", 0.0)) * 0.25)
                + (reliability_score * 0.15)
            ),
        )
        security_effect = SecurityEffect(
            security_level=requirement.security_level,
            security_score=security_score,
            violation_penalty=0.0,
            risk_score=risk_score,
        )
        effects = ExpectedEffect(
            load=load_effect,
            latency=latency_effect,
            cost=cost_effect,
            service_quality=qos_effect,
            security=security_effect,
        )
        risks = self._risks(requirement, effects)
        questions = self._questions(requirement, effects)
        explanation = PolicyExplanation(
            summary=f"Select {node.node_id} in {node.region} for {requirement.workload_type}.",
            factors=self._factors(decision),
            risks=risks,
            questions=questions,
        )
        return ComputeNetworkPolicy(
            policy_id=policy_id,
            requirement=requirement,
            selected_compute=ComputeSelection(
                node_id=node.node_id,
                region=node.region,
                labels=sorted(node.labels),
                score=float(decision.total_score),
                reason=decision.explanation,
            ),
            selected_network=NetworkSelection(
                source_region=task.source_region,
                target_region=node.region,
                stable_latency_ms=float(snapshot.get("stable_latency_ms", 0.0)),
                guaranteed_bandwidth_mbps=float(snapshot.get("guaranteed_bandwidth_mbps", 0.0)),
                delivery_probability=float(snapshot.get("delivery_probability", 0.0)),
                risk_score=float(snapshot.get("uncertainty", 0.0)),
            ),
            resource_config=self._resource_config(task),
            qos_config=QoSConfig(
                latency_target_ms=requirement.latency_target_ms,
                bandwidth_mbps=requirement.bandwidth_mbps,
                priority=requirement.priority,
                sla_probability=qos_effect.sla_probability,
            ),
            security_config=self._security_config(requirement, node, risk_score),
            expected_effect=effects,
            explanation=explanation,
            status="draft",
            task_id=task.task_id,
            decision=decision.to_dict(),
            created_at=time.time(),
        )

    def _effective_resource_defaults(self, requirement: UserRequirement) -> dict[str, float]:
        defaults = dict(self._resource_defaults(requirement))
        # CPU-only training is common for tiny examples, tests and classical ML jobs.
        # Do not allocate GPU-sized memory/storage defaults unless the user actually
        # asks for an accelerator or a deployment profile that requires one.
        if requirement.workload_type == "training" and requirement.gpu_count == 0:
            batch = self._resource_defaults(UserRequirement(objective="cpu-default", workload_type="batch"))
            defaults.update({
                "memory": batch["memory"],
                "storage": batch["storage"],
                "duration": max(defaults.get("duration", 1.0), batch["duration"]),
                "input_size_gb": batch["input_size_gb"],
                "network_sensitivity": min(defaults.get("network_sensitivity", 0.65), 0.45),
            })
        return defaults

    def _resource_defaults(self, requirement: UserRequirement) -> dict[str, float]:
        defaults = {
            "inference": {
                "cpu": 2.0,
                "memory": 4.0,
                "gpu": 0.0,
                "storage": 4.0,
                "duration": 3.0,
                "input_size_gb": 1.0,
                "network_sensitivity": 0.82,
            },
            "training": {
                "cpu": 8.0,
                "memory": 32.0,
                "gpu": 1.0,
                "storage": 80.0,
                "duration": 12.0,
                "input_size_gb": 6.0,
                "network_sensitivity": 0.65,
            },
            "streaming": {
                "cpu": 4.0,
                "memory": 8.0,
                "gpu": 0.0,
                "storage": 12.0,
                "duration": 5.0,
                "input_size_gb": 1.5,
                "network_sensitivity": 0.95,
            },
            "analytics": {
                "cpu": 6.0,
                "memory": 16.0,
                "gpu": 0.0,
                "storage": 40.0,
                "duration": 7.0,
                "input_size_gb": 4.0,
                "network_sensitivity": 0.55,
            },
            "batch": {
                "cpu": 2.0,
                "memory": 4.0,
                "gpu": 0.0,
                "storage": 10.0,
                "duration": 5.0,
                "input_size_gb": 2.0,
                "network_sensitivity": 0.45,
            },
        }
        return defaults[requirement.workload_type]

    def _preferred_labels(self, requirement: UserRequirement, gpu: int | float) -> set[str]:
        labels: set[str] = set()
        if gpu > 0:
            labels.add("gpu")
        if requirement.security_level == "high":
            labels.add("encrypted-transport")
        # Do not force every inference task onto latency-sensitive nodes. For a tiny CPU-only
        # inference job without an explicit latency/SLA target, general compute nodes are valid.
        if (
            requirement.workload_type == "streaming"
            or requirement.priority == "latency"
            or (requirement.latency_target_ms is not None and requirement.latency_target_ms <= 1000)
        ):
            labels.add("latency-sensitive")
        return labels

    def _resource_config(self, task: Task) -> ResourceConfig:
        mode = ExecutionMode.NOOP.value if task.execution is None else task.execution.mode.value
        return ResourceConfig(
            cpu_cores=task.demand.cpu,
            memory_gb=task.demand.memory,
            gpu_count=int(task.demand.gpu),
            storage_gb=task.demand.storage,
            executor_mode=mode,
        )

    def _security_config(
        self,
        requirement: UserRequirement,
        node: Node | None,
        risk_score: float,
    ) -> SecurityConfig:
        regions = list(requirement.region_preference)
        return SecurityConfig(
            isolation_level=self._isolation_level(requirement.security_level),
            data_residency=regions,
            allowed_regions=regions,
            forbidden_nodes=[],
            require_encrypted_transport=requirement.security_level in {"medium", "high"},
            risk_score=risk_score,
        )

    def _empty_effects(self, requirement: UserRequirement) -> ExpectedEffect:
        return ExpectedEffect(
            load=LoadEffect(current_load=0.0, projected_load=0.0, load_balance_score=0.0),
            latency=LatencyEffect(
                target_ms=requirement.latency_target_ms,
                expected_ms=None,
                transfer_ticks=0.0,
                confidence=0.0,
            ),
            cost=CostEffect(
                expected_cost=0.0,
                budget_limit=requirement.budget_limit,
                budget_margin=None,
                cost_score=0.0,
            ),
            service_quality=QoSEffect(
                sla_probability=0.0,
                reliability_score=0.0,
                service_quality_score=0.0,
            ),
            security=SecurityEffect(
                security_level=requirement.security_level,
                security_score=0.0,
                violation_penalty=1.0,
                risk_score=1.0,
            ),
        )

    def _no_candidate_risks(self, requirement: UserRequirement, task: Task, nodes: list[Node]) -> list[str]:
        risks: list[str] = []
        if not nodes:
            risks.append("当前控制面没有在线可调度节点；请启动 sim-backend 或真实 Agent。")
            return risks
        allowed = set(requirement.region_preference)
        if allowed and not any(node.region in allowed for node in nodes):
            risks.append(f"地域缺口：当前在线节点不在允许地域 {sorted(allowed)}。")
        online_nodes = [node for node in nodes if node.online]
        if not online_nodes:
            risks.append("节点状态缺口：所有已知节点均离线。")
        max_gpu = max((node.available().gpu for node in online_nodes), default=0.0)
        if task.demand.gpu > max_gpu:
            risks.append(f"GPU 容量缺口：单节点可用 GPU 最大 {int(max_gpu)}，当前任务需求 {int(task.demand.gpu)}。")
        max_cpu = max((node.available().cpu for node in online_nodes), default=0.0)
        if task.demand.cpu > max_cpu:
            risks.append(f"CPU 容量缺口：单节点可用 CPU 最大 {max_cpu:g}，当前任务需求 {task.demand.cpu:g}。")
        max_mem = max((node.available().memory for node in online_nodes), default=0.0)
        if task.demand.memory > max_mem:
            risks.append(f"内存容量缺口：单节点可用内存最大 {max_mem:g}GB，当前任务需求 {task.demand.memory:g}GB。")
        if requirement.latency_target_ms is not None:
            risks.append(
                f"时延约束核验：要求稳定时延不超过 {requirement.latency_target_ms:g} ms；"
                "当前没有同时满足该目标与其他约束的可执行节点。"
            )
        if requirement.bandwidth_mbps is not None:
            risks.append(
                f"带宽约束核验：要求保证带宽不低于 {requirement.bandwidth_mbps:g} Mbps；"
                "当前没有同时满足该目标与其他约束的可执行节点。"
            )
        labels = set(task.preferred_labels)
        if labels:
            all_labels = set().union(*(node.labels for node in online_nodes)) if online_nodes else set()
            missing = sorted(labels - all_labels)
            if missing:
                risks.append(f"能力标签缺口：当前节点缺少 {missing}。")
        if requirement.deployment.get("required_any_node_labels"):
            for name, candidates in dict(requirement.deployment.get("required_any_node_labels") or {}).items():
                candidate_set = {str(item).lower() for item in candidates}
                if online_nodes and not any(node.labels.intersection(candidate_set) for node in online_nodes):
                    risks.append(f"可选能力缺口：{name} 需要满足其一 {sorted(candidate_set)}。")
        if requirement.deployment.get("supply_calendar_requested") and not requirement.deployment.get("supply_calendar"):
            risks.append("库存日历缺口：当前 inventory 未配置未来释放库存或锁仓价格，不能生成资源日历。")
        if not risks:
            risks.append("当前资源、地域、网络或安全约束下没有可用候选。")
        return risks

    def _risks(self, requirement: UserRequirement, effects: ExpectedEffect) -> list[str]:
        risks: list[str] = []
        if effects.cost.budget_margin is not None and effects.cost.budget_margin < 0:
            risks.append("预计成本超过预算。")
        if (
            requirement.latency_target_ms is not None
            and effects.latency.expected_ms is not None
            and effects.latency.expected_ms > requirement.latency_target_ms
        ):
            risks.append("预计稳定时延高于目标。")
        if effects.load.projected_load > 0.82:
            risks.append("目标节点提交后负载偏高。")
        if effects.security.risk_score > 0.35:
            risks.append("安全隔离或地域约束仍有风险。")
        if requirement.missing_fields:
            risks.append(f"需求字段仍不完整: {', '.join(requirement.missing_fields)}。")
        return risks

    def _questions(self, requirement: UserRequirement, effects: ExpectedEffect) -> list[str]:
        questions: list[str] = []
        if requirement.deployment.get("additional_constraints_declined"):
            return questions
        if requirement.deployment.get("workload_type_unspecified"):
            questions.append("任务类型未指定；本次使用通用批处理资源画像估算。如需更精确推荐，可选补充任务类型。")
        if requirement.priority == "latency" and requirement.budget_limit is None:
            questions.append("是否接受成本上升以换取更低延迟？")
        if requirement.latency_target_ms is None and requirement.workload_type in {"inference", "streaming"}:
            questions.append("是否需要给出明确的端到端时延目标？")
        if not requirement.region_preference and not requirement.deployment.get("region_unspecified"):
            questions.append("是否有首选部署地域或数据驻留要求？")
        if effects.cost.budget_margin is not None and effects.cost.budget_margin < 0:
            questions.append("是否放宽预算或降低资源规格？")
        return questions

    def _factors(self, decision: SchedulingDecision) -> list[str]:
        ranked = sorted(
            decision.metric_scores.items(),
            key=lambda item: item[1] * decision.weights.get(item[0], 0.0),
            reverse=True,
        )
        return [
            f"{metric}: score={score:.3f}, weight={decision.weights.get(metric, 0.0):.3f}"
            for metric, score in ranked[:4]
        ]

    def _workload_type(self, text: str) -> str:
        lower = text.lower()
        # Training intent must win over mentions of LLM or secondary inference evaluation.
        if any(word in lower for word in ("training", "pretrain", "pre-training", "finetune", "fine-tune", "deepspeed", "zero-3", "zero3")) or any(
            word in text for word in ("训练", "预训练", "微调", "分布式训练", "集合通信")
        ):
            return "training"
        if "streaming" in lower or any(word in text for word in ("流式", "实时流", "视频流")):
            return "streaming"
        if any(word in lower for word in ("inference", "serving")) or any(word in text for word in ("推理", "文生图", "在线服务", "离线推理评测")):
            return "inference"
        if "analytics" in lower or any(word in text for word in ("分析", "数仓", "数据处理")):
            return "analytics"
        if self._has_explicit_batch_intent(text):
            return "batch"
        return "batch"

    @staticmethod
    def _has_explicit_batch_intent(text: str) -> bool:
        lower = text.lower()
        return "batch" in lower or any(
            word in text
            for word in ("批处理", "批任务", "批量任务", "批量处理", "离线批量", "离线任务")
        )

    @staticmethod
    def _explicitly_omits_workload_type(text: str) -> bool:
        lower = text.lower().replace(" ", "")
        return any(
            marker in lower
            for marker in (
                "不指定任务类型",
                "无需指定任务类型",
                "不用指定任务类型",
                "不选择任务类型",
                "任务类型不指定",
                "不限任务类型",
                "不限定任务类型",
                "不指定业务类型",
                "无需指定业务类型",
                "不用指定业务类型",
                "不选择业务类型",
                "业务类型不指定",
                "不限业务类型",
                "不限定业务类型",
                "不需要业务类型",
                "无需业务类型",
                "不用业务类型",
                "业务类型不需要",
                "anyworkload",
                "workloadunspecified",
            )
        )

    @staticmethod
    def _declines_additional_constraints(text: str) -> bool:
        lower = text.lower().replace(" ", "")
        return any(
            marker in lower
            for marker in (
                "不需要这些信息",
                "无需这些信息",
                "不用这些信息",
                "不需要这些条件",
                "无需这些条件",
                "不要额外约束",
                "不需要额外约束",
                "不加限制",
                "其余不限",
                "其他不限",
                "没有其他约束",
            )
        )

    def _generic_node_request_without_workload(self, text: str) -> bool:
        if ("节点" not in text and "算力资源" not in text) or self._has_explicit_workload_intent(text):
            return False
        return bool(
            self._regions(text)
            or self._latency_ms(text) is not None
            or self._bandwidth_mbps(text) is not None
            or self._mentions_security(text)
            or self._cpu_cores(text) is not None
            or self._memory(text) is not None
            or self._gpu_count(text) is not None
        )

    def _bare_node_request(self, text: str) -> bool:
        if "节点" not in text and "算力资源" not in text:
            return False
        return not (
            self._has_explicit_workload_intent(text)
            or self._explicitly_omits_workload_type(text)
            or self._declines_additional_constraints(text)
            or self._explicitly_omits_region_preference(text)
            or self._regions(text)
            or self._latency_ms(text) is not None
            or self._bandwidth_mbps(text) is not None
            or self._mentions_security(text)
            or self._cpu_cores(text) is not None
            or self._memory(text) is not None
            or self._gpu_count(text) is not None
        )

    @staticmethod
    def _explicitly_omits_region_preference(text: str) -> bool:
        lower = text.lower().replace(" ", "")
        return any(
            marker in lower
            for marker in (
                "地域不限",
                "地区不限",
                "不指定地域",
                "不指定地区",
                "不限地域",
                "不限地区",
                "哪里都可以",
                "节点地域不限",
            )
        )

    def _has_explicit_workload_intent(self, text: str) -> bool:
        lower = text.lower()
        return self._has_explicit_batch_intent(text) or any(
            word in lower or word in text
            for word in (
                "training", "pretrain", "finetune", "训练", "预训练", "微调",
                "streaming", "流式", "实时流", "视频流",
                "inference", "serving", "推理", "文生图", "在线服务",
                "analytics", "分析", "数仓", "数据处理",
            )
        )

    def _regions(self, text: str) -> list[str]:
        lower = text.lower()
        regions: list[str] = []
        if any(token in text for token in ("广东省内", "仅限广东", "广东地域", "广东省")):
            regions.extend(GUANGDONG_REGIONS)
        for raw, region in REGION_ALIASES.items():
            haystack = lower if raw.isascii() else text
            needle = raw.lower() if raw.isascii() else raw
            if needle in haystack and region not in regions:
                regions.append(region)
        return regions

    def _cpu_cores(self, text: str) -> float | None:
        if "单核" in text or "一核" in text:
            return 1.0
        patterns = [
            r"(\d+(?:\.\d+)?)\s*(?:v?cpu|V?CPU|核|C)",
            r"CPU\s*(?:不低于|>=|至少)?\s*(\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _deployment_spec(self, text: str) -> dict[str, Any]:
        lower = text.lower()
        spec: dict[str, Any] = {}
        if "资源日历" in text or "释放库存" in text or "锁仓" in text:
            spec["supply_calendar_requested"] = True
        if "文生图" in text or "text-to-image" in lower:
            spec["model_type"] = "text_to_image"
            spec["workload_profile"] = "text_to_image_a100"
        qps = re.search(r"(?:qps|QPS)[^\d]{0,8}(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if qps:
            spec["target_qps"] = float(qps.group(1))
        nodes_gpu = re.search(r"(\d+)\s*节点\s*[×xX*]\s*(\d+)\s*卡", text)
        if nodes_gpu:
            nodes = int(nodes_gpu.group(1)); per_node = int(nodes_gpu.group(2))
            spec["nodes_required"] = nodes
            spec["gpu_per_node"] = per_node
            spec["cluster_gpu_count"] = nodes * per_node
        first_phase = re.search(r"(?:首期|一期)[^\d]{0,16}(\d+)\s*(?:张|块|卡)", text)
        if first_phase:
            spec["initial_gpu_count"] = int(first_phase.group(1))
        target_gpu = re.search(r"(?:目标|全周期|二期|扩容)[^\d]{0,16}(\d+)\s*(?:张|块|卡)", text)
        if target_gpu:
            spec["target_gpu_count"] = int(target_gpu.group(1))
        collective_us = re.search(r"(?:all-reduce|集合通信)[^\d]{0,18}(\d+(?:\.\d+)?)\s*(?:μs|us)", text, re.IGNORECASE)
        if collective_us:
            spec["collective_latency_us"] = float(collective_us.group(1))
        first = re.search(r"(?:首\s*(?:token|图)|first[^\d]{0,8})(?:[^\d]{0,12})(\d+(?:\.\d+)?)\s*ms", text, re.IGNORECASE)
        if first:
            spec["first_response_ms"] = float(first.group(1))
        p99 = re.search(r"P99[^\d]{0,12}(\d+(?:\.\d+)?)\s*ms", text, re.IGNORECASE)
        if p99:
            spec["p99_latency_ms"] = float(p99.group(1))
        gpu_models = []
        for model in ("H800", "H100", "A100", "A800", "L40S", "V100", "T4"):
            if model.lower() in lower:
                gpu_models.append(model)
        if gpu_models:
            # A slash/list of models is an OR constraint. The first mention remains the preferred model.
            spec["gpu_model"] = gpu_models[0]
            spec["acceptable_gpu_models"] = gpu_models
            spec.setdefault("required_any_node_labels", {})["gpu_model"] = [item.lower() for item in gpu_models]
            if len(gpu_models) == 1:
                spec.setdefault("required_node_labels", []).append(gpu_models[0].lower())
        gpu_memory = re.search(
            r"(?:A100|H100|V100|A800|H800|L40S|T4)\s*(\d+(?:\.\d+)?)\s*GB(?!/s)",
            text,
            re.IGNORECASE,
        )
        if not gpu_memory:
            gpu_memory = re.search(r"(\d+(?:\.\d+)?)\s*GB(?!/s)\s*(?:显存|HBM|GPU)", text, re.IGNORECASE)
        if gpu_memory:
            spec["gpu_memory_gb"] = float(gpu_memory.group(1))
        if "nvlink" in lower:
            spec["nvlink_required"] = True
            spec.setdefault("required_node_labels", []).append("nvlink")
        if "nvme" in lower:
            spec["local_nvme_required"] = True
            spec.setdefault("required_node_labels", []).append("nvme")
            spec.setdefault("storage_gb", 1000.0)
        fs_candidates = []
        if "lustre" in lower:
            fs_candidates.append("lustre")
        if "cpfs" in lower:
            fs_candidates.append("cpfs")
        if fs_candidates:
            spec["shared_fs_type"] = fs_candidates[-1]
            spec["acceptable_shared_fs"] = fs_candidates
            if len(fs_candidates) == 1:
                spec.setdefault("required_node_labels", []).append(fs_candidates[0])
            else:
                spec.setdefault("required_any_node_labels", {})["shared_fs"] = fs_candidates
        pb = re.search(r"(\d+(?:\.\d+)?)\s*PB", text, re.IGNORECASE)
        if pb:
            spec["shared_storage_pb"] = float(pb.group(1))
            spec["storage_gb"] = float(pb.group(1)) * 1024 * 1024
        gb_s = re.search(r"(\d+(?:\.\d+)?)\s*GB/s", text, re.IGNORECASE)
        if gb_s:
            spec["storage_throughput_gb_s"] = float(gb_s.group(1))
        rdma = re.search(r"(\d+(?:\.\d+)?)\s*G\s*(?:RDMA|RoCE)", text, re.IGNORECASE)
        if rdma:
            spec["rdma_required"] = True
            spec["rdma_bandwidth_gbps"] = float(rdma.group(1))
            spec.setdefault("required_node_labels", []).append("rdma")
        if "pfc" in lower:
            spec.setdefault("required_node_labels", []).append("pfc")
        if "ecn" in lower:
            spec.setdefault("required_node_labels", []).append("ecn")
        if "动态扩缩容" in text or "autoscal" in lower:
            spec["autoscaling_enabled"] = True
            spec.setdefault("replicas_min", 2)
            spec.setdefault("replicas_max", 8)
        if "不接受 spot" in lower or "不接受Spot" in text or "不要spot" in lower:
            spec.setdefault("capacity_policy", {})["spot_enabled"] = False
            spec["capacity_policy"]["spot_ratio"] = 0.0
        elif "spot" in lower or "按量" in text:
            spec.setdefault("capacity_policy", {})["spot_enabled"] = True
            spot_ratio = re.search(r"(\d+(?:\.\d+)?)\s*%[^。；,，]{0,18}spot", text, re.IGNORECASE)
            if not spot_ratio:
                spot_ratio = re.search(r"spot[^。；,，]{0,18}(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
            spec["capacity_policy"]["spot_ratio"] = (float(spot_ratio.group(1)) / 100.0) if spot_ratio else spec["capacity_policy"].get("spot_ratio", 0.0)
        reclaim = re.search(r"(\d+(?:\.\d+)?)\s*%[^。；,，]{0,12}(?:回收|reclaim)", text, re.IGNORECASE)
        if reclaim:
            spec.setdefault("capacity_policy", {})["max_reclaim_ratio"] = float(reclaim.group(1)) / 100.0
        if "checkpoint" in lower or "断点续训" in text:
            spec.setdefault("capacity_policy", {})["checkpoint_required"] = True
        if "ri" in lower or "预留实例" in text or "预留实例券" in text:
            spec.setdefault("capacity_policy", {}).setdefault("billing_modes", []).append("reserved_instance")
        if "on-demand" in lower or "按需" in text:
            spec.setdefault("capacity_policy", {})["on_demand_fallback"] = True
            spec.setdefault("capacity_policy", {}).setdefault("billing_modes", []).append("on_demand")
        compliance: dict[str, Any] = {}
        profiles: list[str] = []
        if "等保三级" in text or "等保3" in text:
            profiles.append("mlps3")
        if "金融" in text:
            profiles.append("finance")
        if profiles:
            compliance["profiles"] = profiles
            spec.setdefault("required_node_labels", []).extend(profiles)
        if "sm4" in lower or "国密" in text:
            compliance["sm4_required"] = True
            spec.setdefault("required_node_labels", []).append("sm4")
        if "sm2" in lower:
            compliance["sm2_required"] = True
            spec.setdefault("required_node_labels", []).append("sm2")
        if "kms" in lower:
            compliance["kms_required"] = True
            spec.setdefault("required_node_labels", []).append("kms")
        if "公网" in text and ("禁止" in text or "无" in text):
            compliance["public_ip_forbidden"] = True
            compliance["public_egress_forbidden"] = True
            spec.setdefault("required_node_labels", []).append("no-public-egress")
        if "mpls" in lower or "金融专网" in text:
            compliance["financial_private_network_required"] = True
            spec.setdefault("required_node_labels", []).append("finance-vpc")
        port_match = re.search(r"(?:仅开放|只开放|开放)\s*(\d{2,5})", text)
        if port_match:
            compliance["allowed_ingress_ports"] = [int(port_match.group(1))]
        if compliance:
            spec["compliance"] = compliance
        # Deduplicate labels while preserving order.
        if spec.get("required_node_labels"):
            seen = set()
            labels = []
            for item in spec["required_node_labels"]:
                item = str(item).lower()
                if item not in seen:
                    seen.add(item); labels.append(item)
            spec["required_node_labels"] = labels
        return spec

    def _simulation_spec(self, requirement: UserRequirement) -> dict[str, Any]:
        deployment = dict(requirement.deployment or {})
        # Keep CPU-only inference truly CPU-only. Earlier versions always emitted
        # gpu_per_replica=1 for inference simulation, which made a task with
        # gpu_count=0 show GPU load during load testing. Only request GPU when
        # the requirement explicitly asks for it.
        requested_gpus = int(requirement.gpu_count or 0)
        service = {
            "type": requirement.workload_type,
            "model_type": deployment.get("model_type"),
            "target_qps": deployment.get("target_qps"),
            "replicas_min": deployment.get("replicas_min", 1),
            "replicas_max": deployment.get("replicas_max", 1),
            "gpu_per_replica": requested_gpus if requested_gpus > 1 else requested_gpus,
            "cpu_per_replica": max(1, int(requirement.cpu_cores or 1)),
            "first_response_ms": deployment.get("first_response_ms"),
        }
        service = {key: value for key, value in service.items() if value is not None}
        validation = {
            "p99_latency_ms": deployment.get("p99_latency_ms") or requirement.latency_target_ms,
            "target_qps": deployment.get("target_qps"),
        }
        validation = {key: value for key, value in validation.items() if value is not None}
        return {
            "kind": "service_deployment" if requirement.workload_type == "inference" else "task",
            "workload_profile": deployment.get("workload_profile") or requirement.workload_type,
            "service": service,
            "validation": validation,
            "capacity_policy": dict(deployment.get("capacity_policy", {})),
            "compliance": dict(deployment.get("compliance", {})),
            "required_node_labels": list(deployment.get("required_node_labels", [])),
        }

    def _number_before(self, text: str, units: tuple[str, ...]) -> float | None:
        for unit in units:
            match = re.search(rf"(\d+(?:\.\d+)?)\s*{re.escape(unit)}", text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _memory(self, text: str) -> float | None:
        tb_patterns = [
            r"内存\s*(?:不低于|>=|至少)?\s*(\d+(?:\.\d+)?)\s*(?:TB|T)",
            r"memory\s*(\d+(?:\.\d+)?)\s*(?:TB|T)",
            r"(\d+(?:\.\d+)?)\s*(?:TB|T)\s*内存",
            r"\d+(?:\.\d+)?\s*(?:v?cpu|C)\s*/?\s*(\d+(?:\.\d+)?)\s*(?:TB|T)",
        ]
        for pattern in tb_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1)) * 1024.0
        patterns = [
            r"内存\s*(?:不低于|>=|至少)?\s*(\d+(?:\.\d+)?)\s*(?:GB|G)",
            r"memory\s*(\d+(?:\.\d+)?)\s*(?:GB|G)",
            r"(\d+(?:\.\d+)?)\s*(?:GB|G)\s*内存",
            r"\d+(?:\.\d+)?\s*(?:v?cpu|C)\s*/?\s*(\d+(?:\.\d+)?)\s*(?:GB|G)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _gpu_count(self, text: str) -> int | None:
        lower = text.lower().replace(" ", "")
        if any(
            token in lower
            for token in (
                "不要gpu",
                "不需要gpu",
                "不使用gpu",
                "不用gpu",
                "无需gpu",
                "无须gpu",
                "无gpu",
                "不要显卡",
                "不需要显卡",
                "不使用显卡",
                "不用显卡",
                "无需显卡",
                "nogpu",
                "no_gpu",
            )
        ):
            return 0
        patterns = [
            r"(\d+)\s*(?:张|块|卡)\s*(?:gpu|GPU|显卡)?",
            r"(?:gpu|GPU|显卡)[^\d]{0,12}(\d+)",
            r"单节点至少\s*(\d+)\s*卡",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and ("gpu" in lower or "显卡" in text or "卡" in match.group(0) or "nvlink" in lower):
                return int(match.group(1))
        if "gpu" in lower or "显卡" in text or "a100" in lower or "h100" in lower:
            return 1
        return None

    def _latency_ms(self, text: str) -> float | None:
        # Prefer service P99/response latency in ms. Training all-reduce microsecond targets
        # are captured in deployment.collective_latency_us, not as max_latency_ms.
        p99 = re.search(r"(?:P99|p99)[^\d]{0,12}(\d+(?:\.\d+)?)\s*ms", text, re.IGNORECASE)
        if p99:
            return float(p99.group(1))
        patterns = [
            r"(?:端到端|推理|响应|latency)[^\d]{0,16}(\d+(?:\.\d+)?)\s*ms",
            r"低于\s*(\d+(?:\.\d+)?)\s*ms",
            r"小于\s*(\d+(?:\.\d+)?)\s*ms",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        seconds = re.search(r"(\d+(?:\.\d+)?)\s*(?:秒|s|sec|seconds)(?:以内|内|以下|以下)?", text, re.IGNORECASE)
        if seconds and any(word in text for word in ("时延", "延迟", "响应", "推理", "以内", "内", "即可")):
            return float(seconds.group(1)) * 1000.0
        return None

    def _bandwidth_mbps(self, text: str) -> float | None:
        gbps = re.search(r"(?:网络|带宽|rdma|roce|bandwidth)[^\d]{0,16}(\d+(?:\.\d+)?)\s*(?:Gbps|G|Gbit)", text, re.IGNORECASE)
        if gbps:
            return float(gbps.group(1)) * 1000.0
        match = re.search(r"(?:带宽|bandwidth)[^\d]{0,10}(\d+(?:\.\d+)?)\s*(?:mbps|m)", text, re.IGNORECASE)
        return float(match.group(1)) if match else None

    def _budget_limit(self, text: str) -> float | None:
        # Prefer explicit money units and avoid reading percentages such as "30% Spot 回收" as budget.
        patterns = [
            r"(?:预算|成本|budget|cost)[^\d]{0,18}(\d+(?:\.\d+)?)\s*(?:万|万元|k|K|元|rmb|RMB)",
            r"(?:预算上限|月度预算|预算)[^\d]{0,18}(\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                end = match.end(1)
                if end < len(text) and text[end:end+1] == "%":
                    continue
                return value
        return None

    def _security_level(self, text: str) -> str:
        lower = text.lower()
        if "high security" in lower or any(word in text for word in ("高安全", "安全要求高", "强隔离", "高隔离", "合规要求高", "等保", "金融合规", "SM4", "KMS", "国密")):
            return "high"
        if "low security" in lower or any(word in text for word in ("低安全", "安全要求低", "无需隔离")):
            return "low"
        return "medium"

    def _mentions_security(self, text: str) -> bool:
        lower = text.lower()
        return any(word in lower for word in ("security", "secure")) or any(
            word in text for word in ("安全", "隔离", "加密", "合规", "密级")
        )

    def _priority(self, text: str) -> str:
        lower = text.lower()
        if any(word in lower for word in ("latency", "realtime")) or any(word in text for word in ("低延迟", "低时延", "实时")):
            return "latency"
        if any(word in lower for word in ("cheap", "cost")) or any(word in text for word in ("低成本", "成本", "便宜")):
            return "cost"
        if any(word in lower for word in ("security", "secure")) or "安全" in text:
            return "security"
        if any(word in lower for word in ("quality", "reliable")) or any(word in text for word in ("质量", "可靠")):
            return "quality"
        return "balanced"

    def _isolation_level(self, security_level: str) -> str:
        if security_level == "high":
            return "namespace"
        if security_level == "medium":
            return "process"
        return "none"

    def _percentage(self, text: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if not match:
            return None
        return float(match.group(1)) / 100.0

    def _new_policy_id(self) -> str:
        return f"pol_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}"
