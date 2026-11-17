"""Проверки CSV и ошибок всех семи настроек, без сетевых запросов."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from src.__main__ import main
from src.config import FIELDS, load_config


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
        self.values.update(test_mode="true", package="A", repository="x.csv")
        self.write_config()
        with self.assertRaisesRegex(ValueError, "repository"):
            load_config(self.path)
        (self.path.parent / "x.csv").write_text("A,B\n", encoding="utf-8")
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
