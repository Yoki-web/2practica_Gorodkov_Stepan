"""BFS, тестовый репозиторий и порядок загрузки."""

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .maven import Dependency, MavenRepository


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
            if graph.depths[current] >= max_depth:
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


def parse_test_line(line):
    """Прочитать строку A -> B, C или A -> для листа."""
    match = re.fullmatch(r"([A-Z])\s*->\s*([A-Z](?:\s*,\s*[A-Z])*)?", line)
    if match is None:
        raise ValueError("Тестовый граф: нужна строка A -> B, C")
    name, children = match.groups()
    children = children.split(",") if children else []
    return name, [item.strip() for item in children]


def read_graph(path):
    """Загрузить тестовый граф и проверить имена и ссылки."""
    graph = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        name, children = parse_test_line(line.strip())
        if name in graph:
            raise ValueError(f"Повторное описание пакета: {name}")
        graph[name] = list(dict.fromkeys(children))
    referenced = {child for children in graph.values() for child in children}
    if referenced - graph.keys():
        raise ValueError("Тестовый граф: отсутствует описание зависимости")
    return graph


class TestRepository:
    """Адаптер тестового графа к интерфейсу получения зависимостей."""

    def __init__(self, path, version):
        """Загрузить граф; всем его пакетам назначить указанную версию."""
        self.graph = read_graph(path)
        self.version = version

    def direct(self, coordinate):
        """Получить зависимости пакета либо сообщить об отсутствующем узле."""
        package, version = coordinate.split(":")
        if version != self.version or package not in self.graph:
            raise ValueError(f"Нет пакета в тестовом репозитории: {coordinate}")
        return [Dependency(child, version) for child in self.graph[package]]
