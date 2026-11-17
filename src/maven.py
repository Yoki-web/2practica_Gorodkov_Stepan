"""Получение Maven POM по HTTP(S) без вызовов менеджера пакетов."""

from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import check_coordinate
from .pom import (
    PomModel, dependency_key, dependency_name, make_dependency, parse_xml,
    properties_for, raw_dependency, text,
)


TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
MAX_POM_BYTES = 5 * 1024 * 1024
MANAGED_PATH = "dependencyManagement/dependencies/dependency"


def fetch_bytes(url):
    """Загрузить POM; повторить временный сетевой сбой не более трех раз."""
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return request_bytes(url)
        except (URLError, OSError) as error:
            last_error = error
    raise ValueError(f"Не удалось получить POM {url}: {last_error}")


def request_bytes(url):
    """Выполнить один HTTP-запрос с ограничением времени и размера POM."""
    request = Request(url, headers={"User-Agent": "maven-graph-practice/1.0"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content = response.read(MAX_POM_BYTES + 1)
    if len(content) > MAX_POM_BYTES:
        raise ValueError(f"POM превышает допустимый размер: {url}")
    return content


def pom_url(repository, coordinate):
    """Построить стандартный путь Maven для конкретной версии пакета."""
    group, artifact, version = coordinate.split(":")
    check_coordinate(f"{group}:{artifact}", version, False)
    path = group.replace(".", "/")
    return f"{repository}/{path}/{artifact}/{version}/{artifact}-{version}.pom"


def parent_coordinate(root):
    """Вернуть координаты родительского POM либо None."""
    node = root.find("parent")
    if node is None:
        return None
    return ":".join(text(node, key) for key in (
        "groupId", "artifactId", "version",
    ))


def management_rows(root, properties):
    """Прочитать управление зависимостями, включая импорты BOM."""
    return [raw_dependency(node, properties)
            for node in root.findall(MANAGED_PATH)]


def bom_coordinates(rows):
    """Выделить координаты импортированных BOM в порядке объявления."""
    return [dependency_name(row) + ":" + row["version"] for row in rows
            if row["scope"] == "import" and row["type"] == "pom"]


def assemble_model(root, properties, parent, models):
    """Объединить родительскую модель, BOM и локальные декларации."""
    rows = management_rows(root, properties)
    managed = {}
    for coordinate in bom_coordinates(rows):
        for key, value in models[coordinate].managed.items():
            managed.setdefault(key, value)
    managed.update(parent.managed)
    for row in rows:
        if row["scope"] != "import":
            managed[dependency_key(row)] = row
    declarations = dict(parent.declarations)
    for node in root.findall("dependencies/dependency"):
        row = raw_dependency(node, properties)
        declarations[dependency_key(row)] = row
    return PomModel(properties, managed, declarations)


class MavenRepository:
    """Кешируемый HTTP-репозиторий с итеративным разрешением parent/BOM."""

    def __init__(self, repository, fetcher=fetch_bytes):
        """Сохранить URL и транспорт; тесты подставляют локальный транспорт."""
        self.repository = repository.rstrip("/")
        self.fetcher = fetcher
        self.roots = {}
        self.models = {}

    def root(self, coordinate):
        """Скачать и разобрать POM не более одного раза за запуск."""
        if coordinate not in self.roots:
            url = pom_url(self.repository, coordinate)
            self.roots[coordinate] = parse_xml(self.fetcher(url))
        return self.roots[coordinate]

    def prerequisites(self, root, coordinate):
        """Найти еще не загруженные parent/BOM текущего POM."""
        parent_name = parent_coordinate(root)
        if parent_name and parent_name not in self.models:
            return [parent_name]
        parent = self.models.get(parent_name, PomModel())
        properties = properties_for(root, coordinate, parent)
        rows = management_rows(root, properties)
        return [name for name in bom_coordinates(rows)
                if name not in self.models]

    def model(self, coordinate):
        """Построить модель без рекурсии и отклонить циклы parent/BOM."""
        pending = [coordinate]
        while pending:
            current = pending[-1]
            if current in self.models:
                pending.pop()
                continue
            root = self.root(current)
            required = self.prerequisites(root, current)
            if required:
                next_name = required[0]
                if next_name in pending:
                    raise ValueError(f"POM: цикл parent/BOM: {next_name}")
                pending.append(next_name)
                continue
            parent = self.models.get(parent_coordinate(root), PomModel())
            properties = properties_for(root, current, parent)
            self.models[current] = assemble_model(
                root, properties, parent, self.models,
            )
            pending.pop()
        return self.models[coordinate]

    def direct(self, coordinate):
        """Вернуть все прямые зависимости с их областями и optional."""
        model = self.model(coordinate)
        return [make_dependency(row, model.managed)
                for row in model.declarations.values()]
