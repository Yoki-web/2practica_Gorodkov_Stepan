"""Итеративный BFS с ограничением глубины и учетом исключений на путях."""

from collections import deque
from dataclasses import dataclass

from .maven import MavenRepository
from .test_repository import TestRepository


RUNTIME_SCOPES = {"compile", "runtime"}


@dataclass
class Graph:
    """Ориентированный граф: ребро идет от пакета к его зависимости."""

    root: str
    edges: dict
    depths: dict
    truncated: set


def excluded(name, exclusions):
    """Проверить Maven-исключения group:artifact с поддержкой символа *."""
    group, artifact = name.split(":")
    candidates = {name, f"{group}:*", f"*:{artifact}", "*:*"}
    return bool(candidates & exclusions)


def runtime_dependencies(repository, coordinate, exclusions):
    """Выбрать обязательные compile/runtime-зависимости для потребителя."""
    result = []
    for dependency in repository.direct(coordinate):
        if dependency.scope not in RUNTIME_SCOPES or dependency.optional:
            continue
        if exclusions and excluded(dependency.name, exclusions):
            continue
        result.append(dependency)
    return result


def add_edge(graph, source, target, depth):
    """Добавить уникальное ребро и зарегистрировать новый узел графа."""
    if target not in graph.edges[source]:
        graph.edges[source].append(target)
    graph.edges.setdefault(target, [])
    graph.depths.setdefault(target, depth)


def build_graph(root, repository, max_depth):
    """Обойти граф очередью BFS; повторный узел не вызывает зацикливания."""
    graph = Graph(root, {root: []}, {root: 0}, set())
    initial = (root, frozenset())
    queue = deque([(root, 0, frozenset())])
    visited = {initial}
    while queue:
        current, depth, blocked = queue.popleft()
        if depth >= max_depth:
            graph.truncated.add(current)
            continue
        for item in runtime_dependencies(repository, current, blocked):
            child = item.coordinate
            add_edge(graph, current, child, depth + 1)
            child_blocked = blocked | item.exclusions
            state = (child, child_blocked)
            if state not in visited:
                visited.add(state)
                queue.append((child, depth + 1, child_blocked))
    return graph


def analyze(config):
    """Создать выбранный источник и построить граф указанной версии."""
    if config.test_mode:
        repository = TestRepository(config.repository, config.version)
        if config.package not in repository.graph:
            raise ValueError(f"Тестовый пакет не найден: {config.package}")
    else:
        repository = MavenRepository(config.repository)
    return build_graph(
        f"{config.package}:{config.version}", repository, config.max_depth,
    )
