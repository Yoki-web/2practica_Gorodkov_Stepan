"""Контракт PlantUML/PNG, конечность ASCII-дерева и поведение CLI."""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.__main__ import run
from src.config import load_config
from src.graph import Graph
from src.visualization import (
    PNG_SIGNATURE, ascii_tree, java_command, render_png, save_visualization,
    to_plantuml,
)


class VisualizationTests(unittest.TestCase):
    """Проверить выходные форматы без установленной Java и без интернета."""

    def setUp(self):
        """Создать ромб с общей зависимостью для проверки всех ребер."""
        self.graph = Graph("A", {"A": ["B", "C"], "B": ["D"],
                                 "C": ["D"], "D": []}, {}, set())

    def test_plantuml_preserves_every_edge(self):
        """PlantUML содержит все узлы, все ребра и стабильные псевдонимы."""
        source = to_plantuml(self.graph)
        self.assertTrue(source.startswith("@startuml\n"))
        self.assertTrue(source.endswith("@enduml\n"))
        self.assertEqual(source.count("rectangle "), 4)
        self.assertEqual(source.count(" --> "), 4)
        self.assertIn("n2 --> n3", source)

    def test_ascii_shared_node(self):
        """Общий узел отображается как ссылка, а ветви состоят из ASCII."""
        expected = "A\n|-- B\n|   `-- D\n`-- C\n    `-- D [shared]"
        self.assertEqual(ascii_tree(self.graph), expected)

    def test_ascii_cycle_and_depth_limit(self):
        """Цикл и обрезанный граф имеют разные явные пометки."""
        cycle = Graph("A", {"A": ["B"], "B": ["A"]}, {}, set())
        self.assertIn("A [cycle]", ascii_tree(cycle))
        self.graph.truncated = {"D"}
        self.assertIn("D [depth limit]", ascii_tree(self.graph))
        self.assertIn("[depth limit]", to_plantuml(self.graph))

    def test_ascii_long_chain(self):
        """ASCII-вывод также работает без рекурсии."""
        size = 1200
        edges = {str(index): [str(index + 1)] for index in range(size)}
        edges[str(size)] = []
        tree = ascii_tree(Graph("0", edges, {}, set()))
        self.assertEqual(len(tree.splitlines()), size + 1)

    def test_missing_plantuml(self):
        """Отсутствующий JAR вызывает понятную ошибку конфигурации среды."""
        with patch.dict(os.environ, {"PLANTUML_JAR": "missing-file.jar"}):
            with self.assertRaisesRegex(ValueError, "PLANTUML_JAR"):
                java_command()

    def test_renderer_failure_and_invalid_png(self):
        """Ненулевой код или ответ не в PNG нельзя сохранить как картинку."""
        for code, content in ((1, PNG_SIGNATURE), (0, b"not PNG")):
            result = subprocess.CompletedProcess([], code, content, b"bad")
            with self.subTest(code=code):
                with patch("src.visualization.java_command", return_value=[]):
                    with patch("subprocess.run", return_value=result):
                        with self.assertRaisesRegex(ValueError, "PNG"):
                            render_png("@startuml\n@enduml")

    def test_renderer_timeout(self):
        """Таймаут процесса обрабатывается без зависания CLI."""
        error = subprocess.TimeoutExpired("java", 60)
        with patch("src.visualization.java_command", return_value=[]):
            with patch("subprocess.run", side_effect=error):
                with self.assertRaisesRegex(ValueError, "PlantUML"):
                    render_png("source")

    def test_save_source_and_image(self):
        """PNG и его исходник записываются с заданным пользователем именем."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "nested" / "graph.png"
            with patch("src.visualization.render_png", return_value=b"image"):
                save_visualization(self.graph, output)
            self.assertEqual(output.read_bytes(), b"image")
            source = output.with_suffix(".puml").read_text(encoding="utf-8")
            self.assertEqual(source, to_plantuml(self.graph))

    def test_cli_ascii_flag_and_stage_specific_output(self):
        """Финальный CLI не выводит настройки/порядок предыдущих этапов."""
        root = Path(__file__).resolve().parents[1]
        config = load_config(root / "examples/diamond.csv")
        for enabled in (True, False):
            stdout = io.StringIO()
            with self.subTest(enabled=enabled), redirect_stdout(stdout):
                with patch("src.__main__.save_visualization"):
                    run(replace(config, ascii_tree=enabled))
            result = stdout.getvalue()
            self.assertEqual("|-- " in result, enabled)
            self.assertIn("PNG:", result)
            self.assertNotIn("Порядок загрузки:", result)
            self.assertNotIn("max_depth=", result)
