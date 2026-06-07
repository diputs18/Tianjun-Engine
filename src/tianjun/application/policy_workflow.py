from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..core import ComputeNetworkPolicy, UserFeedback, UserRequirement
from ..policy.feedback import parse_feedback_instruction
from ..policy.simulator import simulate_policy
from ..scenarios import execution_from_dict, task_from_dict

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


@dataclass(slots=True)
class PolicyWorkflowService:
    """Boundary for policy draft, comparison, simulation, commit, and feedback optimization."""

    control_plane: CentralControlPlane

    @property
    def policy_count(self) -> int:
        return len(self.control_plane.policies)

    def draft_policy_from_session(
        self,
        session_id: str,
        *,
        execution_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            session = control.requirement_dialogue.session_or_raise(session_id)
            result = self.draft_policy(
                session.requirement.to_dict(),
                execution_payload=execution_payload,
            )
            result["requirement_session"] = {
                "session_id": session.session_id,
                "status": session.status,
                "questions": list(session.questions),
            }
            return result

    def compare_policy_options_from_session(
        self,
        session_id: str,
        *,
        execution_payload: dict[str, Any] | None = None,
        option_profiles: list[str] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            session = control.requirement_dialogue.session_or_raise(session_id)
            return self.compare_policy_options(
                session.requirement.to_dict(),
                execution_payload=execution_payload,
                option_profiles=option_profiles,
                requirement_session={
                    "session_id": session.session_id,
                    "status": session.status,
                    "questions": list(session.questions),
                },
            )

    def draft_policy(
        self,
        requirement_payload: dict[str, Any],
        *,
        execution_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            requirement = UserRequirement.from_dict(requirement_payload)
            execution = None if execution_payload is None else execution_from_dict(execution_payload)
            policy, task = control.policy_generator.draft_policy(
                requirement,
                scheduler=control.scheduler,
                nodes=control.nodes.values(),
                current_tick=control.current_tick(),
                execution=execution,
            )
            control.policies[policy.policy_id] = policy
            control.policy_tasks[policy.policy_id] = task
            return policy.to_dict()

    def compare_policy_options(
        self,
        requirement_payload: dict[str, Any],
        *,
        execution_payload: dict[str, Any] | None = None,
        option_profiles: list[str] | None = None,
        requirement_session: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            control._expire_stale_nodes()
            base_requirement = UserRequirement.from_dict(requirement_payload)
            execution = None if execution_payload is None else execution_from_dict(execution_payload)
            profiles = self.normalize_option_profiles(option_profiles)
            options: list[dict[str, Any]] = []
            for index, profile in enumerate(profiles):
                requirement = self.requirement_for_option_profile(base_requirement, profile)
                policy, task = control.policy_generator.draft_policy(
                    requirement,
                    scheduler=control.scheduler,
                    nodes=control.nodes.values(),
                    current_tick=control.current_tick(),
                    policy_id=f"{control.policy_generator._new_policy_id()}_{profile}",
                    execution=execution,
                )
                control.policies[policy.policy_id] = policy
                control.policy_tasks[policy.policy_id] = task
                policy_payload = policy.to_dict()
                simulation = simulate_policy(policy).to_dict()
                options.append(
                    self.policy_option_payload(
                        label=chr(ord("A") + index),
                        profile=profile,
                        policy=policy_payload,
                        simulation=simulation,
                    )
                )
            recommended = self.recommended_policy_option(options)
            return {
                "status": "compared",
                "requirement": base_requirement.to_dict(),
                "requirement_session": requirement_session,
                "option_profiles": profiles,
                "options": options,
                "recommended_option": recommended,
                "recommended_policy_id": None if recommended is None else recommended["policy_id"],
                "explanation": self.policy_options_explanation(options, recommended),
            }

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        with self.control_plane.lock:
            return self.policy_or_raise(policy_id).to_dict()

    def simulate_policy(self, policy_id: str) -> dict[str, Any]:
        with self.control_plane.lock:
            policy = self.policy_or_raise(policy_id)
            result = simulate_policy(policy)
            return result.to_dict()

    def commit_policy(self, policy_id: str) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            policy = self.policy_or_raise(policy_id)
            if policy.status == "failed" or policy.selected_compute.node_id is None:
                raise ValueError(f"Policy {policy_id} has no feasible candidate to commit.")
            task = control.policy_tasks.get(policy_id)
            if task is None:
                task = control.policy_generator.task_from_requirement(
                    policy.requirement,
                    task_id=policy.task_id or f"task_{policy_id}",
                )
                control.policy_tasks[policy_id] = task
            if policy.selected_compute.node_id:
                task.target_node_id = policy.selected_compute.node_id
            task.max_retries = 0
            if task.task_id in control.tasks:
                submitted = control.tasks[task.task_id].to_dict()
                status = "already_committed"
            else:
                submitted = control.submit_task(task_from_dict(task.to_dict()))
                status = "committed"
            policy.status = "committed"
            return {
                "status": status,
                "policy": policy.to_dict(),
                "submitted_task": submitted,
            }

    def parse_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        with self.control_plane.lock:
            policy_id = str(feedback_payload.get("policy_id", ""))
            if policy_id:
                self.policy_or_raise(policy_id)
            normalized = self.normalize_feedback_payload(feedback_payload)
            return normalized

    def record_user_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            normalized = self.normalize_feedback_payload(feedback_payload)
            feedback = UserFeedback.from_dict(normalized)
            self.policy_or_raise(feedback.policy_id)
            control.user_feedback.append(feedback)
            return {
                "status": "recorded",
                "feedback": feedback.to_dict(),
            }

    def optimize_policy_from_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
        control = self.control_plane
        with control.lock:
            normalized = self.normalize_feedback_payload(feedback_payload)
            feedback = UserFeedback.from_dict(normalized)
            base_policy = self.policy_or_raise(feedback.policy_id)
            control.user_feedback.append(feedback)
            requirement = control.policy_generator.merge_requirement_update(base_policy.requirement, feedback.instruction)
            if feedback.target in {
                "latency",
                "cost",
                "security",
                "qos",
                "balance",
                "fragmentation",
                "locality",
                "network",
            } and len(feedback.instruction) < 80:
                requirement = control.policy_generator.apply_feedback(requirement, feedback)
            base_task = control.policy_tasks.get(feedback.policy_id)
            policy, task = control.policy_generator.draft_policy(
                requirement,
                scheduler=control.scheduler,
                nodes=control.nodes.values(),
                current_tick=control.current_tick(),
                execution=None if base_task is None else base_task.execution,
            )
            control.policies[policy.policy_id] = policy
            control.policy_tasks[policy.policy_id] = task
            return {
                "status": "optimized",
                "feedback": feedback.to_dict(),
                "base_policy_id": feedback.policy_id,
                "policy": policy.to_dict(),
            }

    def policy_or_raise(self, policy_id: str) -> ComputeNetworkPolicy:
        policy = self.control_plane.policies.get(policy_id)
        if policy is None:
            raise ValueError(f"Unknown policy {policy_id}.")
        return policy

    @staticmethod
    def normalize_feedback_payload(feedback_payload: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(feedback_payload.get("policy_id", ""))
        instruction = str(feedback_payload.get("instruction", ""))
        if not policy_id:
            raise ValueError("feedback policy_id is required")
        return parse_feedback_instruction(
            policy_id=policy_id,
            instruction=instruction,
            target=feedback_payload.get("target"),
            sentiment=feedback_payload.get("sentiment"),
            preference_delta=feedback_payload.get("preference_delta"),
        )

    @staticmethod
    def normalize_option_profiles(option_profiles: list[str] | None) -> list[str]:
        aliases = {
            "latency": "latency_first",
            "latency_first": "latency_first",
            "low_latency": "latency_first",
            "cost": "cost_first",
            "cost_first": "cost_first",
            "low_cost": "cost_first",
            "balanced": "balanced_reliability",
            "reliability": "balanced_reliability",
            "reliability_first": "balanced_reliability",
            "quality": "balanced_reliability",
            "quality_first": "balanced_reliability",
            "balanced_reliability": "balanced_reliability",
        }
        requested = option_profiles or ["latency_first", "cost_first", "balanced_reliability"]
        profiles: list[str] = []
        for item in requested:
            profile = aliases.get(str(item).strip().lower())
            if profile and profile not in profiles:
                profiles.append(profile)
        return profiles[:4] or ["latency_first", "cost_first", "balanced_reliability"]

    @staticmethod
    def requirement_for_option_profile(requirement: UserRequirement, profile: str) -> UserRequirement:
        data = requirement.to_dict()
        vector = dict(data.get("priority_vector") or {})
        if profile == "latency_first":
            data["priority"] = "latency"
            vector.update({
                "latency": max(vector.get("latency", 0.0), 1.0),
                "network": max(vector.get("network", 0.0), 0.78),
            })
        elif profile == "cost_first":
            data["priority"] = "cost"
            vector.update({
                "cost": max(vector.get("cost", 0.0), 1.0),
                "balance": max(vector.get("balance", 0.0), 0.45),
            })
        elif profile == "balanced_reliability":
            data["priority"] = "quality"
            vector.update({
                "quality": max(vector.get("quality", 0.0), 0.9),
                "network": max(vector.get("network", 0.0), 0.55),
                "balance": max(vector.get("balance", 0.0), 0.45),
            })
        data["priority_vector"] = vector
        data["objective"] = f"{requirement.objective} | option_profile={profile}"
        data["missing_fields"] = []
        data["confidence"] = max(requirement.confidence, 0.72)
        return UserRequirement.from_dict(data)

    @staticmethod
    def policy_option_payload(
        *,
        label: str,
        profile: str,
        policy: dict[str, Any],
        simulation: dict[str, Any],
    ) -> dict[str, Any]:
        effect = policy.get("expected_effect") or {}
        latency = effect.get("latency") or {}
        cost = effect.get("cost") or {}
        quality = effect.get("service_quality") or {}
        security = effect.get("security") or {}
        compute = policy.get("selected_compute") or {}
        network = policy.get("selected_network") or {}
        return {
            "label": label,
            "profile": profile,
            "profile_name": {
                "latency_first": "低时延优先",
                "cost_first": "低成本优先",
                "balanced_reliability": "均衡 / 高可靠优先",
            }.get(profile, profile),
            "policy_id": policy.get("policy_id"),
            "status": policy.get("status"),
            "feasible": bool(simulation.get("feasible") and compute.get("node_id")),
            "selected_node": compute.get("node_id"),
            "selected_region": compute.get("region") or network.get("target_region"),
            "expected_latency_ms": latency.get("expected_ms"),
            "expected_cost": cost.get("expected_cost"),
            "budget_margin": cost.get("budget_margin"),
            "sla_probability": quality.get("sla_probability"),
            "security_score": security.get("security_score"),
            "total_score": compute.get("score"),
            "risks": list(simulation.get("risks") or (policy.get("explanation") or {}).get("risks") or []),
            "policy": policy,
            "simulation": simulation,
        }

    @staticmethod
    def recommended_policy_option(options: list[dict[str, Any]]) -> dict[str, Any] | None:
        feasible = [option for option in options if option.get("feasible")]
        if not feasible:
            return options[0] if options else None

        def score(option: dict[str, Any]) -> float:
            total = float(option.get("total_score") or 0.0)
            sla = float(option.get("sla_probability") or 0.0)
            security = float(option.get("security_score") or 0.0)
            cost = float(option.get("expected_cost") or 0.0)
            latency = float(option.get("expected_latency_ms") or 0.0)
            return (total * 0.46) + (sla * 0.24) + (security * 0.12) - (cost * 0.006) - (latency * 0.0015)

        return max(feasible, key=score)

    @staticmethod
    def policy_options_explanation(options: list[dict[str, Any]], recommended: dict[str, Any] | None) -> str:
        if not options:
            return "没有生成可对比的策略候选。"
        if recommended is None or not recommended.get("feasible"):
            return "当前多个策略取向下都缺少可正式下发的候选节点，建议放宽地域、资源、预算、网络或安全约束。"
        return (
            f"推荐优先选择方案 {recommended['label']}（{recommended['profile_name']}），"
            "因为它在可行性、SLA 概率、成本和综合评分之间取得了当前最稳的平衡。"
        )
