"""Порядок загрузки: зависимости раньше использующих их пакетов."""

from collections import deque


def reverse_edges(graph):
    """Для каждой зависимости найти использующие ее пакеты."""
    dependents = {node: [] for node in graph.edges}
    for node, children in graph.edges.items():
        for child in children:
            dependents[child].append(node)
    return dependents


def load_order(graph):
    """Итеративно упорядочить DAG алгоритмом Кана; цикл дает ошибку."""
    remaining = {node: len(children) for node, children in graph.edges.items()}
    dependents = reverse_edges(graph)
    ready = deque(node for node, count in remaining.items() if not count)
    result = []
    while ready:
        node = ready.popleft()
        result.append(node)
        for parent in dependents[node]:
            remaining[parent] -= 1
            if not remaining[parent]:
                ready.append(parent)
    if len(result) != len(graph.edges):
        raise ValueError("Цикл: порядок загрузки зависимостей невозможен")
    return result
