"""Точка входа CLI; путь CSV является единственным позиционным аргументом."""

import argparse
import csv
import sys

from .config import load_config
from .graph import analyze


def run(config):
    """Этап 3: вывести список смежности построенного BFS-графа."""
    graph = analyze(config)
    for node, children in graph.edges.items():
        print(f"{node} -> {', '.join(children) or '(нет зависимостей)'}")


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
