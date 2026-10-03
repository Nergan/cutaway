"""Взвешенный поиск пути конвертации.

Граф передаётся снаружи, чтобы модуль не тянул за собой движки конвертера.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Mapping


CostFn = Callable[[str, str], float]

# Перекодирование видео и обход через PDF дороже прямого шага.
_EXPENSIVE_TARGETS = frozenset({"pdf", "mp4", "webm", "gif"})


def default_cost(source: str, target: str) -> float:
    if source == target:
        return 0.1
    if target in _EXPENSIVE_TARGETS:
        return 3.0
    return 1.0


def shortest_path(
    edges: Mapping[str, list[str]],
    start: str,
    goal: str,
    cost: CostFn = default_cost,
) -> list[str] | None:
    """Вернуть путь включая начало и конец. Нет пути — None."""
    if start == goal:
        return [start]
    best: dict[str, float] = {start: 0.0}
    prev: dict[str, str] = {}
    queue: list[tuple[float, str]] = [(0.0, start)]
    while queue:
        spent, node = heapq.heappop(queue)
        if spent != best.get(node):
            continue
        if node == goal:
            break
        for nxt in edges.get(node, []):
            step = cost(node, nxt)
            total = spent + step
            if total < best.get(nxt, float("inf")):
                best[nxt] = total
                prev[nxt] = node
                heapq.heappush(queue, (total, nxt))
    if goal not in prev and start != goal:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def path_cost(path: list[str], cost: CostFn = default_cost) -> float:
    return sum(cost(path[index], path[index + 1]) for index in range(len(path) - 1))
