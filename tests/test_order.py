"""Проверка порядка загрузки для различных форм тестового графа."""

import unittest

from src.graph import Graph
from src.order import load_order


class OrderTests(unittest.TestCase):
    """Порядок должен соблюдать все ребра и отвергать циклы."""

    def test_diamond(self):
        """Общая зависимость стоит раньше обоих использующих ее пакетов."""
        graph = Graph("A", {"A": ["B", "C"], "B": ["D"],
                            "C": ["D"], "D": []}, {}, set())
        result = load_order(graph)
        self.assertEqual(result, ["D", "B", "C", "A"])
        for node, children in graph.edges.items():
            for child in children:
                self.assertLess(result.index(child), result.index(node))

    def test_leaf_and_chain(self):
        """Лист загружается сам; цепочка упорядочивается от конца к корню."""
        leaf = Graph("A", {"A": []}, {}, set())
        chain = Graph("A", {"A": ["B"], "B": ["C"], "C": []}, {}, set())
        self.assertEqual(load_order(leaf), ["A"])
        self.assertEqual(load_order(chain), ["C", "B", "A"])

    def test_cycles(self):
        """Обычный цикл и петля исключают корректный топологический порядок."""
        for edges in ({"A": ["A"]}, {"A": ["B"], "B": ["A"]}):
            with self.subTest(edges=edges):
                with self.assertRaisesRegex(ValueError, "Цикл"):
                    load_order(Graph("A", edges, {}, set()))
