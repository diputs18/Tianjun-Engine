from __future__ import annotations

from typing import Any

from ..domain import BatchValidationIssue, BatchValidationReport, Task


class BatchRequestError(ValueError):
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload))
        self.status_code = status_code
        self.payload = payload


def validated_objectives(value: Any, allowed: tuple[str, ...], field: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise BatchRequestError(422, {"error": f"{field} must be an array"})
    unknown = [str(item) for item in value if str(item) not in allowed]
    if unknown:
        raise BatchRequestError(422, {"error": f"unknown {field}: {', '.join(unknown)}"})
    unique = tuple(dict.fromkeys(str(item) for item in value))
    if not unique:
        raise BatchRequestError(422, {"error": f"{field} cannot be empty"})
    return unique


def validated_weights(value: Any, allowed: tuple[str, ...], field: str) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BatchRequestError(422, {"error": f"{field} must be an object"})
    unknown = [str(key) for key in value if str(key) not in allowed]
    if unknown:
        raise BatchRequestError(422, {"error": f"unknown {field}: {', '.join(unknown)}"})
    weights = {str(key): float(weight) for key, weight in value.items()}
    if any(weight < 0.0 for weight in weights.values()) or sum(weights.values()) <= 0.0:
        raise BatchRequestError(422, {"error": f"{field} values must be non-negative with a positive sum"})
    return weights


def rejection_reason(task: Task, nodes: Any) -> str:
    nodes_list = list(nodes)
    if task.demand.gpu > 0 and all(node.available().gpu + 1e-9 < task.demand.gpu for node in nodes_list):
        return "INSUFFICIENT_GPU"
    if task.allowed_regions and all(
        not any(node.matches_deployment_region(region) for region in task.allowed_regions)
        for node in nodes_list
    ):
        return "REGION_FORBIDDEN"
    if task.carbon_budget_g is not None:
        return "CARBON_BUDGET_EXCEEDED"
    if task.deadline is not None:
        return "DEADLINE_INFEASIBLE"
    return "NO_FEASIBLE_NODE"


def csv_row(row: dict[str, str], row_number: int) -> dict[str, Any]:
    def validation_error(field: str, code: str, message: str) -> BatchRequestError:
        report = BatchValidationReport(
            0,
            errors=[BatchValidationIssue(row_number, field, code, message)],
        )
        return BatchRequestError(422, {"error": "batch validation failed", "validation": report.to_dict()})

    def number(name: str, default: float = 0.0) -> float:
        text = str(row.get(name, "")).strip()
        if text == "":
            return default
        try:
            return float(text)
        except ValueError as exc:
            raise validation_error(name, "INVALID_NUMBER", f"{name} must be numeric") from exc

    def boolean(name: str, default: bool) -> bool:
        text = str(row.get(name, "")).strip().lower()
        if text == "":
            return default
        if text not in {"true", "false"}:
            raise validation_error(name, "INVALID_BOOLEAN", f"{name} must be true or false")
        return text == "true"

    payload: dict[str, Any] = {
        "task_id": str(row.get("task_id", "")).strip(),
        "task_type": str(row.get("task_type", "batch")).strip() or "batch",
        "demand": {key: number(key) for key in ("cpu", "memory", "gpu", "storage")},
        "estimated_duration": int(number("estimated_duration", 0)),
        "priority": int(number("priority", 5)),
        "security_level": str(row.get("security_level", "medium")).strip() or "medium",
        "isolation_level": str(row.get("isolation_level", "process")).strip() or "process",
        "allowed_regions": [item for item in str(row.get("allowed_regions", "")).split("|") if item],
        "forbidden_nodes": [item for item in str(row.get("forbidden_nodes", "")).split("|") if item],
        "require_encrypted_transport": boolean("require_encrypted_transport", True),
        "allow_region_shift": boolean("allow_region_shift", True),
        "allow_time_shift": boolean("allow_time_shift", False),
        "carbon_priority": number("carbon_priority", 0.0),
    }
    region = str(row.get("region", "")).strip()
    if region and not payload["allowed_regions"]:
        payload["allowed_regions"] = [region]
    optional_numbers = (
        "budget", "deadline", "input_size_gb", "max_latency_ms",
        "min_bandwidth_mbps", "carbon_budget_g", "deferrable_until_tick",
    )
    for key in optional_numbers:
        text = str(row.get(key, "")).strip()
        if text:
            payload[key] = float(text) if key not in {"deadline", "deferrable_until_tick"} else int(float(text))
    for key in ("data_region", "source_region"):
        text = str(row.get(key, "")).strip()
        if text:
            payload[key] = text
    return payload
