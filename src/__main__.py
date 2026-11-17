"""Точка входа CLI; путь CSV является единственным позиционным аргументом."""

import argparse
import csv
import sys

from .config import load_config
from .maven import MavenRepository


def run(config):
    """Этап 2: вывести все прямые зависимости указанной версии Maven."""
    if config.test_mode:
        raise ValueError("Тестовый репозиторий реализуется на этапе 3")
    repository = MavenRepository(config.repository)
    for item in repository.direct(f"{config.package}:{config.version}"):
        print(f"{item.coordinate} scope={item.scope} optional={item.optional}")


def main(argv=None):
    """Обработать аргументы, исполнить этап и вернуть код завершения."""
    parser = argparse.ArgumentParser(description="Maven: граф зависимостей")
    parser.add_argument("config", help="путь CSV-файла с настройками")
    args = parser.parse_args(argv)
    try:
        run(load_config(args.config))
    except (ValueError, OSError, csv.Error) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
