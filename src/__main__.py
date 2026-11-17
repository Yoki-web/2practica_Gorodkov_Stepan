"""Точка входа CLI; путь CSV является единственным позиционным аргументом."""

import argparse
import csv
import sys
from dataclasses import asdict

from .config import load_config


def run(config):
    """Этап 1: вывести все проверенные параметры в формате ключ=значение."""
    for key, value in asdict(config).items():
        print(f"{key}={value}")


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
