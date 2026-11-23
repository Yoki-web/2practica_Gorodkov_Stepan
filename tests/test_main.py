"""Тесты конфигурации, Maven, графа и визуализации."""

import csv
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from src.config import Config, FIELDS, load_config
from src.graph import (
    Graph, TestRepository, analyze, build_graph, load_order, read_graph,
)
from src.main import main, run
from src.maven import Dependency, MavenRepository, expand, fetch_bytes
from src.maven import parse_xml, pom_url
from src.visualizer import (
    PNG_SIGNATURE, ascii_tree, java_command, render_png, save_visualization,
    to_plantuml,
)


class ConfigTests(unittest.TestCase):
    """Проверить корректную конфигурацию и каждую группу ошибочных данных."""

    def setUp(self):
        """Создать независимый временный CSV для каждого теста."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.csv"
        self.values = dict(zip(FIELDS, (
            "junit:junit", "https://repo.maven.apache.org/maven2", "false",
            "4.13.2", "graph.png", "true", "10",
        )))

    def write_config(self):
        """Записать текущие значения в стандартном формате CSV."""
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("key", "value"))
            writer.writerows(self.values.items())

    def test_valid_config(self):
        """Настройки преобразуются к нужным типам и абсолютным путям."""
        self.write_config()
        config = load_config(self.path)
        self.assertEqual(config.package, "junit:junit")
        self.assertEqual(config.max_depth, 10)
        self.assertTrue(config.ascii_tree)
        self.assertFalse(config.test_mode)
        self.assertEqual(config.output.parent, self.path.parent)

    def test_errors_for_every_parameter(self):
        """Неверные значения каждого из семи ключей отклоняются."""
        invalid = {
            "package": ["junit", "../bad:x"],
            "repository": ["file:///repo", "https://x:bad", "https://x?q=1"],
            "test_mode": ["yes", "1"],
            "version": ["[1,2)", "../1", "LATEST", "1-SNAPSHOT"],
            "output": ["graph.svg", "bad?.png"],
            "ascii_tree": ["yes", "0"],
            "max_depth": ["-1", "1.5", "infinity"],
        }
        for key, values in invalid.items():
            original = self.values[key]
            for value in values:
                with self.subTest(key=key, value=value):
                    self.values[key] = value
                    self.write_config()
                    with self.assertRaisesRegex(ValueError, key):
                        load_config(self.path)
            self.values[key] = original

    def test_missing_empty_duplicate_and_extra_fields(self):
        """Контракт CSV исключает пропущенные, пустые и лишние настройки."""
        self.write_config()
        original = self.path.read_text(encoding="utf-8")
        variants = (
            original.replace("max_depth,10\n", ""),
            original.replace("version,4.13.2", "version,"),
            original + "version,1\n", original + "extra,value\n",
            original.replace("key,value", "setting,value"),
            original + "bad,row,extra\n",
        )
        for content in variants:
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(self.path)

    def test_test_repository_validation(self):
        """Тестовый режим требует A-Z и существующий локальный файл."""
        self.values.update(test_mode="true", package="A", repository="x.txt")
        self.write_config()
        with self.assertRaisesRegex(ValueError, "repository"):
            load_config(self.path)
        (self.path.parent / "x.txt").write_text("A ->\n", encoding="utf-8")
        self.assertTrue(load_config(self.path).test_mode)

    def test_zero_depth(self):
        """Нулевая глубина разрешена для анализа одного корня."""
        self.values["max_depth"] = "0"
        self.write_config()
        self.assertEqual(load_config(self.path).max_depth, 0)

    def test_cli_reports_error_without_traceback(self):
        """Ошибка пользователя дает stderr и ненулевой код завершения."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = main([str(self.path)])
        self.assertEqual(result, 1)
        self.assertIn("Ошибка:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


def project(body):
    """Сформировать небольшой POM с настоящим пространством имен Maven."""
    return ('<project xmlns="http://maven.apache.org/POM/4.0.0">'
            + body + '</project>').encode()


def declaration(name="child", version="1", extra=""):
    """Сформировать XML одной тестовой зависимости."""
    return (f"<dependency><groupId>org.test</groupId>"
            f"<artifactId>{name}</artifactId><version>{version}</version>"
            f"{extra}</dependency>")


class MavenTests(unittest.TestCase):
    """Проверить URL, свойства, родителя, BOM, области и ошибки POM."""

    def setUp(self):
        """Создать транспорт с картой URL и учетом запросов."""
        self.files = {}
        self.requests = []
        self.repo = MavenRepository("https://example.org", self.fetch)

    def fetch(self, url):
        """Вернуть заранее заданный POM, не обращаясь в интернет."""
        self.requests.append(url)
        return self.files[url]

    def add(self, coordinate, body):
        """Добавить POM в локальное отображение HTTP-репозитория."""
        self.files[pom_url(self.repo.repository, coordinate)] = project(body)

    def test_exact_version_url_and_cache(self):
        """Указанная версия входит в URL; повторный запрос читает кеш."""
        self.add("org.test:root:2.5", "<dependencies>"
                 + declaration() + "</dependencies>")
        result = self.repo.direct("org.test:root:2.5")
        self.repo.direct("org.test:root:2.5")
        self.assertEqual(result[0].coordinate, "org.test:child:1")
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.requests[0].endswith("/root/2.5/root-2.5.pom"))

    def test_parent_properties_and_dependency_management(self):
        """Версия наследуется из свойств и dependencyManagement родителя."""
        self.add("org.test:parent:1", "<properties><v>3</v></properties>"
                 "<dependencyManagement><dependencies>"
                 + declaration(version="${v}")
                 + "</dependencies></dependencyManagement>")
        self.add("org.test:root:1", "<parent><groupId>org.test</groupId>"
                 "<artifactId>parent</artifactId><version>1</version>"
                 "</parent><dependencies>" + declaration(version="")
                 + "</dependencies>")
        self.assertEqual(self.repo.direct("org.test:root:1")[0].version, "3")

    def test_bom_import(self):
        """Импортированный BOM задает отсутствующую версию зависимости."""
        self.add("org.test:bom:1", "<dependencyManagement><dependencies>"
                 + declaration(version="8")
                 + "</dependencies></dependencyManagement>")
        self.add("org.test:root:1", "<dependencyManagement><dependencies>"
                 + declaration("bom", "1", "<scope>import</scope>"
                               "<type>pom</type>")
                 + "</dependencies></dependencyManagement><dependencies>"
                 + declaration(version="") + "</dependencies>")
        self.assertEqual(self.repo.direct("org.test:root:1")[0].version, "8")

    def test_child_overrides_parent_property(self):
        """Свойство дочернего POM меняет версию унаследованной зависимости."""
        self.add("org.test:parent:1", "<properties><v>3</v></properties>"
                 "<dependencies>" + declaration(version="${v}")
                 + "</dependencies>")
        self.add("org.test:root:1", "<parent><groupId>org.test</groupId>"
                 "<artifactId>parent</artifactId><version>1</version>"
                 "</parent><properties><v>4</v></properties>")
        self.assertEqual(self.repo.direct("org.test:root:1")[0].version, "4")

    def test_all_direct_scopes_and_optional_are_preserved(self):
        """Этап 2 выводит и тестовые, и необязательные прямые зависимости."""
        self.add("org.test:root:1", "<dependencies>"
                 + declaration(extra="<scope>test</scope>"
                               "<optional>true</optional>")
                 + "</dependencies>")
        item = self.repo.direct("org.test:root:1")[0]
        self.assertEqual(item.scope, "test")
        self.assertTrue(item.optional)

    def test_parent_cycle(self):
        """Цикл наследования POM завершается понятной ошибкой."""
        self.add("org.test:root:1", "<parent><groupId>org.test</groupId>"
                 "<artifactId>root</artifactId><version>1</version></parent>")
        with self.assertRaisesRegex(ValueError, "цикл"):
            self.repo.direct("org.test:root:1")

    def test_main_jar_is_not_replaced_by_test_jar(self):
        """Test-jar с тем же именем не затирает compile-зависимость."""
        self.add("org.test:root:1", "<dependencies>" + declaration()
                 + declaration(extra="<scope>test</scope>"
                               "<type>test-jar</type>")
                 + "</dependencies>")
        items = self.repo.direct("org.test:root:1")
        self.assertEqual([item.scope for item in items], ["compile", "test"])

    def test_properties_errors_and_nested_expansion(self):
        """Подстановка поддерживает цепочки, но не циклы и неизвестные имена."""
        self.assertEqual(expand("${a}", {"a": "${b}", "b": "2"}), "2")
        for properties in (
            {}, {"a": "${a}"}, {"a": "${b}", "b": "${a}"},
            {"a": "${a}x"},
        ):
            with self.subTest(properties=properties):
                with self.assertRaises(ValueError):
                    expand("${a}", properties)

    def test_malformed_xml_and_doctype(self):
        """Поврежденные и неподдерживаемые XML отклоняются."""
        for content in (b"<project>", b"<other/>", b"<!DOCTYPE x><project/>"):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    parse_xml(content)

    def test_network_error(self):
        """Ошибка HTTP-транспорта преобразуется в диагностическое сообщение."""
        with patch("src.maven.urlopen", side_effect=URLError("unavailable")):
            with self.assertRaisesRegex(ValueError, "POM"):
                fetch_bytes("https://example.org/missing.pom")

    def test_missing_version(self):
        """Неразрешенную версию нельзя молча заменить произвольной версией."""
        self.add("org.test:root:1", "<dependencies>"
                 + declaration(version="") + "</dependencies>")
        with self.assertRaisesRegex(ValueError, "version"):
            self.repo.direct("org.test:root:1")


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


def local_config():
    """Подготовить тестовый режим независимо от настроек пользователя."""
    root = Path(__file__).resolve().parents[1]
    return Config(
        package="A", repository=str(root / "data/test_repo.txt"),
        test_mode=True, version="1", output=root / "generated/test.png",
        ascii_tree=True, max_depth=10,
    )


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
        """Проверить формат, имена, повторные узлы и ссылки."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.txt"
            path.write_text("A -> B\nB ->\n")
            repository = TestRepository(path, "2")
            self.assertEqual(repository.direct("A:2")[0].coordinate, "B:2")
            for rows in ("A -> B\n", "A ->\nA ->\n", "a ->\n", "A B C\n"):
                with self.subTest(rows=rows):
                    path.write_text(rows, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_graph(path)

    def test_leaf(self):
        """Пакет без зависимостей сохраняется как единственный узел."""
        graph = build_graph("A:1", simple_repository({"A": []}), 10)
        self.assertEqual(graph.edges, {"A:1": []})
        self.assertFalse(graph.truncated)

    def test_data_scenarios(self):
        """Проверить четыре примера в общем файле тестового репозитория."""
        config = local_config()
        diamond = analyze(config)
        self.assertEqual(load_order(diamond), ["D:1", "B:1", "C:1", "A:1"])
        cycle = analyze(replace(config, package="E"))
        self.assertEqual(cycle.edges["G:1"], ["E:1"])
        with self.assertRaisesRegex(ValueError, "Цикл"):
            load_order(cycle)
        chain = analyze(replace(config, package="H", max_depth=1))
        self.assertEqual(chain.edges, {"H:1": ["I:1"], "I:1": []})
        leaf = analyze(replace(config, package="L"))
        self.assertEqual(leaf.edges, {"L:1": []})


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
                with patch("src.visualizer.java_command", return_value=[]):
                    with patch("subprocess.run", return_value=result):
                        with self.assertRaisesRegex(ValueError, "PNG"):
                            render_png("@startuml\n@enduml")

    def test_renderer_timeout(self):
        """Таймаут процесса обрабатывается без зависания CLI."""
        error = subprocess.TimeoutExpired("java", 60)
        with patch("src.visualizer.java_command", return_value=[]):
            with patch("subprocess.run", side_effect=error):
                with self.assertRaisesRegex(ValueError, "PlantUML"):
                    render_png("source")

    def test_save_source_and_image(self):
        """PNG и его исходник записываются с заданным пользователем именем."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "nested" / "graph.png"
            with patch("src.visualizer.render_png", return_value=b"image"):
                save_visualization(self.graph, output)
            self.assertEqual(output.read_bytes(), b"image")
            source = output.with_suffix(".puml").read_text(encoding="utf-8")
            self.assertEqual(source, to_plantuml(self.graph))

    def test_renderer_error_preserves_previous_output(self):
        """При ошибке PlantUML оба файла прежнего запуска сохраняются."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "graph.png"
            source = output.with_suffix(".puml")
            output.write_bytes(b"previous image")
            source.write_text("previous graph", encoding="utf-8")
            error = ValueError("Ошибка PlantUML")
            with patch("src.visualizer.render_png", side_effect=error):
                with self.assertRaisesRegex(ValueError, "PlantUML"):
                    save_visualization(self.graph, output)
            self.assertEqual(source.read_text(encoding="utf-8"),
                             "previous graph")
            self.assertEqual(output.read_bytes(), b"previous image")

    def test_cli_ascii_flag_and_stage_specific_output(self):
        """Финальный CLI не выводит настройки/порядок предыдущих этапов."""
        config = local_config()
        for enabled in (True, False):
            stdout = io.StringIO()
            with self.subTest(enabled=enabled), redirect_stdout(stdout):
                with patch("src.main.save_visualization"):
                    run(replace(config, ascii_tree=enabled))
            result = stdout.getvalue()
            self.assertEqual("|-- " in result, enabled)
            self.assertIn("PNG:", result)
            self.assertNotIn("Порядок загрузки:", result)
            self.assertNotIn("max_depth=", result)
