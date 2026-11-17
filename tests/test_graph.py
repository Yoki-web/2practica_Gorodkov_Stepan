"""Проверки BFS, глубины, циклов, областей и контекстных исключений."""

import tempfile
import unittest
from pathlib import Path

from src.graph import build_graph
from src.pom import Dependency
from src.test_repository import TestRepository, read_graph


class MemoryRepository:
    """Источник зависимостей в памяти с журналом порядка обхода."""

    def __init__(self, edges):
        """Сохранить тестовые ребра и пустой журнал запросов."""
        self.edges = edges
        self.calls = []

    def direct(self, coordinate):
        """Записать запрос и вернуть заданные зависимости."""
        self.calls.append(coordinate)
        return self.edges.get(coordinate, [])


def simple_repository(edges):
    """Преобразовать списки имен A-Z в зависимости версии 1."""
    return MemoryRepository({
        name + ":1": [Dependency(child, "1") for child in children]
        for name, children in edges.items()
    })


class GraphTests(unittest.TestCase):
    """Сценарии графа проверяют наблюдаемый результат и порядок запросов."""

    def test_breadth_first_order_and_shared_dependency(self):
        """Общая вершина запрашивается один раз после всего своего уровня."""
        repository = simple_repository({"A": "BC", "B": "D", "C": "D"})
        graph = build_graph("A:1", repository, 10)
        self.assertEqual(repository.calls, ["A:1", "B:1", "C:1", "D:1"])
        self.assertEqual(graph.edges["C:1"], ["D:1"])
        self.assertEqual(graph.depths["D:1"], 2)

    def test_cycle_and_self_loop(self):
        """Обратное ребро сохраняется, но обход цикла завершается."""
        for edges in ({"A": "B", "B": "A"}, {"A": "A"}):
            with self.subTest(edges=edges):
                repository = simple_repository(edges)
                graph = build_graph("A:1", repository, 100)
                self.assertEqual(len(repository.calls), len(edges))
                self.assertIn("A:1", next(reversed(graph.edges.values())))

    def test_depth_zero_and_one(self):
        """Граница глубины не вызывает загрузку POM за ее пределами."""
        repository = simple_repository({"A": "B", "B": "C"})
        zero = build_graph("A:1", repository, 0)
        self.assertEqual(zero.edges, {"A:1": []})
        self.assertEqual(repository.calls, [])
        one = build_graph("A:1", repository, 1)
        self.assertEqual(one.edges, {"A:1": ["B:1"], "B:1": []})
        self.assertEqual(repository.calls, ["A:1"])

    def test_long_chain_without_recursion(self):
        """Цепочка длиннее лимита рекурсии обрабатывается очередью."""
        size = 1500
        repository = simple_repository({
            str(index): [str(index + 1)] for index in range(size)
        })
        graph = build_graph("0:1", repository, size + 1)
        self.assertEqual(len(graph.edges), size + 1)

    def test_runtime_scope_and_optional(self):
        """Test/provided и optional не входят в runtime-граф потребителя."""
        repository = MemoryRepository({"A:1": [
            Dependency("B", "1"), Dependency("C", "1", "runtime"),
            Dependency("D", "1", "test"),
            Dependency("E", "1", "provided"),
            Dependency("F", "1", optional=True),
        ]})
        graph = build_graph("A:1", repository, 10)
        self.assertEqual(graph.edges["A:1"], ["B:1", "C:1"])

    def test_exclusions_are_path_specific(self):
        """Запрет на одном пути не убирает зависимость другого пути."""
        repository = MemoryRepository({
            "x:a:1": [
                Dependency("x:b", "1", exclusions=frozenset({"x:d"})),
                Dependency("x:c", "1"),
            ],
            "x:b:1": [Dependency("x:d", "1")],
            "x:c:1": [Dependency("x:b", "1")],
        })
        graph = build_graph("x:a:1", repository, 10)
        self.assertIn("x:d:1", graph.edges["x:b:1"])

    def test_test_repository_and_invalid_files(self):
        """Формат CSV требует A-Z, уникальные узлы и описания всех ссылок."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.csv"
            path.write_text("package,dependencies\nA,B\nB,\n")
            repository = TestRepository(path, "2")
            self.assertEqual(repository.direct("A:2")[0].coordinate, "B:2")
            for rows in ("A,B\n", "A,\nA,\n", "a,\n", "A,B,C\n"):
                with self.subTest(rows=rows):
                    path.write_text("package,dependencies\n" + rows)
                    with self.assertRaises(ValueError):
                        read_graph(path)

    def test_leaf(self):
        """Пакет без зависимостей сохраняется как единственный узел."""
        graph = build_graph("A:1", simple_repository({"A": []}), 10)
        self.assertEqual(graph.edges, {"A:1": []})
        self.assertFalse(graph.truncated)
