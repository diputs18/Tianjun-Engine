from __future__ import annotations

from ..core import ComputeNetworkPolicy, PolicySimulationResult


def simulate_policy(policy: ComputeNetworkPolicy) -> PolicySimulationResult:
    """Validate a drafted policy and return auditable effect diagnostics.

    This is not a packet-level network simulator. It converts the deterministic
    scheduler decision into a transparent feasibility and risk assessment, so the
    user can see why a policy is safe enough to commit or which dimensions need
    another round of clarification/optimization.
    """
    feasible = policy.status != "failed" and policy.selected_compute.node_id is not None
    diagnostics = _diagnostics(policy)
    risks = list(policy.explanation.risks)
    risks.extend(diagnostics["derived_risks"])
    risks = _dedupe(risks)
    risk_count = len(risks)
    status = "feasible" if feasible and risk_count == 0 else "feasible_with_risks" if feasible else "infeasible"
    policy.status = "simulated" if feasible else "failed"
    return PolicySimulationResult(
        policy_id=policy.policy_id,
        feasible=feasible,
        status=status,
        expected=policy.expected_effect,
        risks=risks,
        questions=list(policy.explanation.questions),
        diagnostics=diagnostics,
    )


def _diagnostics(policy: ComputeNetworkPolicy) -> dict[str, object]:
    effect = policy.expected_effect
    target = effect.latency.target_ms
    expected_latency = effect.latency.expected_ms
    budget = effect.cost.budget_limit
    expected_cost = effect.cost.expected_cost
    latency_margin = None if target is None or expected_latency is None else target - expected_latency
    budget_margin = None if budget is None else budget - expected_cost
    derived_risks: list[str] = []
    if latency_margin is not None and latency_margin < 0:
        derived_risks.append("仿真诊断：时延目标存在缺口。")
    if budget_margin is not None and budget_margin < 0:
        derived_risks.append("仿真诊断：成本目标存在缺口。")
    if effect.service_quality.sla_probability < 0.72:
        derived_risks.append("仿真诊断：SLA 概率偏低，建议考虑更可靠节点或放宽约束。")
    if effect.security.risk_score > 0.35:
        derived_risks.append("仿真诊断：安全风险偏高，建议提升隔离等级或收窄地域。")

    return {
        "latency_margin_ms": latency_margin,
        "budget_margin": budget_margin,
        "projected_load": effect.load.projected_load,
        "sla_probability": effect.service_quality.sla_probability,
        "security_risk_score": effect.security.risk_score,
        "commit_recommendation": _commit_recommendation(policy, derived_risks),
        "derived_risks": derived_risks,
    }


def _commit_recommendation(policy: ComputeNetworkPolicy, derived_risks: list[str]) -> str:
    if policy.status == "failed" or policy.selected_compute.node_id is None:
        return "do_not_commit"
    if derived_risks or policy.explanation.risks:
        return "review_before_commit"
    return "safe_to_commit"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
