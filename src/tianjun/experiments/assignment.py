from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


RESOURCE_KEYS = ("cpu", "memory", "gpu", "storage")


@dataclass(slots=True)
class AssignmentCandidate:
    task_id: str
    node_id: str
    utility: float
    demand: dict[str, float]
    objectives: dict[str, float] = field(default_factory=dict)
    payload: Any = None


@dataclass(slots=True)
class AssignmentSolution:
    selected: list[AssignmentCandidate]
    objective_totals: dict[str, float]
    assigned_count: int
    utility: float
    status: str


def milp_oracle(
    candidates: list[AssignmentCandidate],
    capacities: dict[str, dict[str, float]],
) -> AssignmentSolution:
    """Solve the small task-node assignment exactly with SciPy/HiGHS MILP."""
    if not candidates:
        return AssignmentSolution([], {}, 0, 0.0, "empty")
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import lil_matrix
    except ImportError as exc:  # pragma: no cover - optional experiment dependency
        raise RuntimeError("MILP Oracle requires the optional 'experiments' dependencies") from exc

    tasks = sorted({item.task_id for item in candidates})
    nodes = sorted(capacities)
    rows = len(tasks) + len(nodes) * len(RESOURCE_KEYS)
    matrix = lil_matrix((rows, len(candidates)), dtype=float)
    upper = []
    task_row = {task_id: index for index, task_id in enumerate(tasks)}
    for task_id in tasks:
        upper.append(1.0)
    resource_row: dict[tuple[str, str], int] = {}
    offset = len(tasks)
    for node_id in nodes:
        for key in RESOURCE_KEYS:
            resource_row[(node_id, key)] = offset
            upper.append(float(capacities[node_id].get(key, 0.0)))
            offset += 1
    for column, item in enumerate(candidates):
        matrix[task_row[item.task_id], column] = 1.0
        for key in RESOURCE_KEYS:
            matrix[resource_row[(item.node_id, key)], column] = float(item.demand.get(key, 0.0))
    assignment_reward = max(1.0, sum(abs(item.utility) for item in candidates) + 1.0)
    objective = np.array([-(assignment_reward + item.utility) for item in candidates], dtype=float)
    result = milp(
        c=objective,
        integrality=np.ones(len(candidates)),
        bounds=Bounds(np.zeros(len(candidates)), np.ones(len(candidates))),
        constraints=LinearConstraint(matrix.tocsr(), np.zeros(rows), np.array(upper)),
        options={"time_limit": 30.0},
    )
    if result.x is None:
        return AssignmentSolution([], {}, 0, 0.0, f"milp_{result.message}")
    selected = [item for item, value in zip(candidates, result.x) if value >= 0.5]
    return _solution(selected, "optimal" if result.success else "time_limit_feasible")


def nsga2_assignments(
    candidates: list[AssignmentCandidate],
    capacities: dict[str, dict[str, float]],
    *,
    seed: int = 20260718,
    population_size: int = 64,
    generations: int = 80,
) -> list[AssignmentSolution]:
    """Deterministic compact NSGA-II baseline for offline experiments."""
    by_task: dict[str, list[AssignmentCandidate]] = {}
    for item in candidates:
        by_task.setdefault(item.task_id, []).append(item)
    tasks = sorted(by_task)
    if not tasks:
        return []
    rng = random.Random(seed)

    def random_genome() -> list[int]:
        return [rng.randrange(-1, len(by_task[task_id])) for task_id in tasks]

    def decode(genome: list[int]) -> AssignmentSolution:
        remaining = {node: dict(values) for node, values in capacities.items()}
        selected = []
        order = sorted(range(len(tasks)), key=lambda index: max((item.utility for item in by_task[tasks[index]]), default=0), reverse=True)
        for index in order:
            choice = genome[index]
            if choice < 0:
                continue
            item = by_task[tasks[index]][choice % len(by_task[tasks[index]])]
            if all(float(item.demand.get(key, 0.0)) <= float(remaining[item.node_id].get(key, 0.0)) + 1e-9 for key in RESOURCE_KEYS):
                selected.append(item)
                for key in RESOURCE_KEYS:
                    remaining[item.node_id][key] = float(remaining[item.node_id].get(key, 0.0)) - float(item.demand.get(key, 0.0))
        return _solution(selected, "nsga2")

    population = [random_genome() for _ in range(max(8, population_size))]
    for _ in range(max(1, generations)):
        evaluated = [(genome, decode(genome)) for genome in population]
        front = _nondominated([solution for _, solution in evaluated])
        elite_ids = {id(solution) for solution in front}
        elites = [genome for genome, solution in evaluated if id(solution) in elite_ids]
        if not elites:
            elites = [max(evaluated, key=lambda pair: (pair[1].assigned_count, pair[1].utility))[0]]
        next_population = [list(genome) for genome in elites[:population_size]]
        while len(next_population) < population_size:
            left, right = rng.choice(elites), rng.choice(elites)
            split = rng.randrange(1, len(tasks)) if len(tasks) > 1 else 1
            child = list(left[:split] + right[split:])
            if rng.random() < 0.35:
                index = rng.randrange(len(tasks))
                child[index] = rng.randrange(-1, len(by_task[tasks[index]]))
            next_population.append(child)
        population = next_population
    return _nondominated([decode(genome) for genome in population])


def _solution(selected: list[AssignmentCandidate], status: str) -> AssignmentSolution:
    objectives: dict[str, float] = {}
    for item in selected:
        for key, value in item.objectives.items():
            objectives[key] = objectives.get(key, 0.0) + float(value)
    return AssignmentSolution(selected, objectives, len(selected), sum(item.utility for item in selected), status)


def _nondominated(solutions: list[AssignmentSolution]) -> list[AssignmentSolution]:
    keys = sorted({key for solution in solutions for key in solution.objective_totals})
    result = []
    for current in solutions:
        current_vector = [current.assigned_count, current.utility, *(current.objective_totals.get(key, 0.0) for key in keys)]
        dominated = False
        for other in solutions:
            if other is current:
                continue
            other_vector = [other.assigned_count, other.utility, *(other.objective_totals.get(key, 0.0) for key in keys)]
            if all(a >= b - 1e-12 for a, b in zip(other_vector, current_vector)) and any(a > b + 1e-12 for a, b in zip(other_vector, current_vector)):
                dominated = True
                break
        if not dominated:
            result.append(current)
    unique: dict[tuple[tuple[str, str], ...], AssignmentSolution] = {}
    for solution in result:
        key = tuple(sorted((item.task_id, item.node_id) for item in solution.selected))
        unique[key] = solution
    return list(unique.values())
