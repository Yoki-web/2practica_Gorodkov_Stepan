"""Точка входа CLI; путь CSV является единственным позиционным аргументом."""

import argparse
import csv
import sys

from .config import load_config
from .graph import analyze
from .visualization import ascii_tree, save_visualization


def run(config):
    """Этап 5: сохранить PlantUML/PNG и при необходимости вывести дерево."""
    graph = analyze(config)
    if config.ascii_tree:
        print(ascii_tree(graph))
    save_visualization(graph, config.output)
    print(f"PNG: {config.output}")
    print(f"PlantUML: {config.output.with_suffix('.puml')}")


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
