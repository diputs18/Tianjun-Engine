from __future__ import annotations

from math import log, sqrt
from typing import Iterable


def critic_weights(rows: Iterable[Iterable[float]]) -> list[float]:
    """Return CRITIC objective weights for an already benefit-oriented matrix."""
    matrix = [list(map(float, row)) for row in rows]
    if not matrix or not matrix[0]:
        return []
    normalized = _column_minmax(matrix)
    columns = list(map(list, zip(*normalized)))
    std = [_std(column) for column in columns]
    information = []
    for index, column in enumerate(columns):
        conflict = sum(1.0 - _correlation(column, other) for other in columns)
        information.append(std[index] * conflict)
    return _normalize(information)


def entropy_weights(rows: Iterable[Iterable[float]]) -> list[float]:
    """Return entropy weights for an already benefit-oriented matrix."""
    matrix = [list(map(float, row)) for row in rows]
    if not matrix or not matrix[0]:
        return []
    normalized = _column_minmax(matrix)
    columns = list(map(list, zip(*normalized)))
    count = len(matrix)
    if count <= 1:
        return [1.0 / len(columns)] * len(columns)
    diversity = []
    for column in columns:
        total = sum(column)
        probabilities = [value / total for value in column] if total > 0 else [1.0 / count] * count
        entropy = -sum(value * log(value) for value in probabilities if value > 0) / log(count)
        diversity.append(max(0.0, 1.0 - entropy))
    return _normalize(diversity)


def _column_minmax(matrix: list[list[float]]) -> list[list[float]]:
    columns = list(map(list, zip(*matrix)))
    bounds = [(min(column), max(column)) for column in columns]
    return [
        [(value - low) / (high - low) if high > low else 1.0 for value, (low, high) in zip(row, bounds)]
        for row in matrix
    ]


def _std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _correlation(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator > 1e-12 else 0.0


def _normalize(values: list[float]) -> list[float]:
    total = sum(max(0.0, value) for value in values)
    if total <= 1e-12:
        return [1.0 / len(values)] * len(values)
    return [max(0.0, value) / total for value in values]
