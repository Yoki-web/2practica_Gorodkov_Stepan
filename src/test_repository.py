"""Локальный CSV-репозиторий с именами пакетов A-Z."""

import csv
import re
from pathlib import Path

from .pom import Dependency


ROW_SIZE = 2


def read_graph(path):
    """Прочитать package,dependencies; зависимости разделяются пробелами."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != ["package", "dependencies"]:
            raise ValueError("Тестовый CSV: заголовок package,dependencies")
        graph = {}
        for row in reader:
            if len(row) != ROW_SIZE:
                raise ValueError("Тестовый CSV: нужны два столбца")
            package, children = row[0].strip(), row[1].split()
            if package in graph:
                raise ValueError(f"Повторное описание пакета {package}")
            if any(not re.fullmatch("[A-Z]", item)
                   for item in [package] + children):
                raise ValueError("Тестовые пакеты называются буквами A-Z")
            graph[package] = list(dict.fromkeys(children))
    referenced = {child for children in graph.values() for child in children}
    if referenced - graph.keys():
        raise ValueError("Тестовый CSV: отсутствует описание зависимости")
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
