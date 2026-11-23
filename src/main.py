"""Запуск из терминала."""

import argparse
import csv
import sys

from .config import load_config
from .graph import analyze
from .visualizer import ascii_tree, save_visualization


def run(config):
    """Этап 5. Построить и показать граф."""
    graph = analyze(config)
    if config.ascii_tree:
        print(ascii_tree(graph))
    save_visualization(graph, config.output)
    print(f"PNG: {config.output}")
    print(f"PlantUML: {config.output.with_suffix('.puml')}")


def main(argv=None):
    """Прочитать аргумент и запустить анализ."""
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
