"""Этап 1. Настройки CSV."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


FIELDS = (
    "package", "repository", "test_mode", "version", "output",
    "ascii_tree", "max_depth",
)
CSV_COLUMNS = 2
TOKEN = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
PACKAGE = rf"{TOKEN}:{TOKEN}"


@dataclass(frozen=True)
class Config:
    """Настройки программы."""

    package: str
    repository: str
    test_mode: bool
    version: str
    output: Path
    ascii_tree: bool
    max_depth: int


def read_rows(path):
    """Прочитать и проверить строки CSV."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream, strict=True)
        if next(rows, None) != ["key", "value"]:
            raise ValueError("CSV должен начинаться строкой key,value")
        values = {}
        for row in rows:
            if len(row) != CSV_COLUMNS:
                raise ValueError("В каждой строке CSV нужны два столбца")
            key, value = (item.strip() for item in row)
            if key not in FIELDS or key in values:
                raise ValueError(f"Неизвестный или повторный ключ: {key}")
            if not value:
                raise ValueError(f"Пустое значение: {key}")
            values[key] = value
    missing = set(FIELDS) - values.keys()
    if missing:
        raise ValueError(f"Отсутствуют параметры: {', '.join(sorted(missing))}")
    return values


def boolean(value, key):
    """Разобрать true/false."""
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{key}: требуется true или false")
    return normalized == "true"


def depth(value):
    """Разобрать глубину от нуля."""
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("max_depth: требуется целое число >= 0")
    return int(value)


def check_coordinate(package, version, test_mode):
    """Проверить имя пакета и версию."""
    pattern = r"[A-Z]" if test_mode else PACKAGE
    if not re.fullmatch(pattern, package):
        raise ValueError("package: нужна A-Z или Maven groupId:artifactId")
    if not re.fullmatch(TOKEN, version):
        raise ValueError("version: нужна фиксированная версия пакета")
    if version in {"LATEST", "RELEASE"} or version.endswith("-SNAPSHOT"):
        raise ValueError("version: динамические версии не поддерживаются")


def repository_path(value, test_mode, base):
    """Проверить источник графа."""
    if test_mode:
        path = (base / value).resolve()
        if not path.is_file():
            raise ValueError(f"repository: файл не найден: {path}")
        return str(path)
    return repository_url(value)


def repository_url(value):
    """Проверить адрес HTTP(S)."""
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise ValueError("repository: требуется HTTP(S) URL")
    if url.query or url.fragment or url.username or url.password:
        raise ValueError("repository: URL без query, fragment и учетных данных")
    try:
        url.port
    except ValueError as error:
        raise ValueError("repository: некорректный порт") from error
    if any(char.isspace() for char in value):
        raise ValueError("repository: пробелы в URL запрещены")
    return value.rstrip("/")


def output_path(value, base):
    """Проверить путь PNG."""
    path = (base / value).resolve()
    if path.suffix.lower() != ".png" or path.is_dir():
        raise ValueError("output: требуется имя файла с расширением .png")
    if any(char in value for char in ('\x00', '<', '>', '"', '|', '?', '*')):
        raise ValueError("output: недопустимые символы имени файла")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError("output: родительский путь не является каталогом")
    return path


def load_config(filename):
    """Собрать настройки из CSV."""
    path = Path(filename).resolve()
    values = read_rows(path)
    test_mode = boolean(values["test_mode"], "test_mode")
    check_coordinate(values["package"], values["version"], test_mode)
    return Config(
        package=values["package"],
        repository=repository_path(
            values["repository"], test_mode, path.parent,
        ),
        test_mode=test_mode,
        version=values["version"],
        output=output_path(values["output"], path.parent),
        ascii_tree=boolean(values["ascii_tree"], "ascii_tree"),
        max_depth=depth(values["max_depth"]),
    )
