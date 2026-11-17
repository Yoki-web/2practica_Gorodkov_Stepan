"""Тесты получения конкретных версий и эффективных POM без сети."""

import unittest
from unittest.mock import patch
from urllib.error import URLError

from src.maven import MavenRepository, fetch_bytes, pom_url
from src.pom import expand, parse_xml


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

    def test_properties_errors_and_nested_expansion(self):
        """Подстановка поддерживает цепочки, но не циклы и неизвестные имена."""
        self.assertEqual(expand("${a}", {"a": "${b}", "b": "2"}), "2")
        for properties in ({}, {"a": "${a}"}, {"a": "${b}", "b": "${a}"}):
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
