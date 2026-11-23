"""Этап 2. Чтение POM."""

import re
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import check_coordinate


PROPERTY = re.compile(r"\$\{([^}]+)\}")
SUPPORTED_SCOPES = {
    "compile", "runtime", "test", "provided", "system", "import",
}


@dataclass(frozen=True)
class Dependency:
    """Данные зависимости."""

    name: str
    version: str
    scope: str = "compile"
    optional: bool = False
    exclusions: frozenset = frozenset()

    @property
    def coordinate(self):
        """Координаты с версией."""
        return f"{self.name}:{self.version}"


@dataclass
class PomModel:
    """Свойства, версии и зависимости POM."""

    properties: dict = field(default_factory=dict)
    managed: dict = field(default_factory=dict)
    declarations: dict = field(default_factory=dict)


def parse_xml(content):
    """Разобрать XML POM."""
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("POM: DTD и сущности не поддерживаются")
    try:
        root = element_tree.fromstring(content)
    except element_tree.ParseError as error:
        raise ValueError(f"POM: неверный XML: {error}") from error
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if root.tag != "project":
        raise ValueError("POM: ожидается корневой элемент project")
    return root


def text(node, path, default=""):
    """Прочитать текст тега."""
    return (node.findtext(path) or default).strip()


def expand(value, properties):
    """Раскрыть ссылки на свойства."""
    for attempt in range(len(properties) + 1):
        if not PROPERTY.search(value):
            return value
        for key in PROPERTY.findall(value):
            if key not in properties:
                raise ValueError(f"POM: неизвестное свойство: {key}")
            value = value.replace("${" + key + "}", properties[key])
    if PROPERTY.search(value):
        raise ValueError("POM: цикл свойств")
    return value


def properties_for(root, coordinate, parent):
    """Собрать свойства проекта и родителя."""
    properties = dict(parent.properties)
    element = root.find("properties")
    if element is not None:
        properties.update({item.tag: item.text or "" for item in element})
    group, artifact, version = coordinate.split(":")
    for key, value in zip(("groupId", "artifactId", "version"), (
        group, artifact, version,
    )):
        properties[f"project.{key}"] = value
        properties[f"pom.{key}"] = value
    parent_node = root.find("parent")
    if parent_node is not None:
        for key in ("groupId", "artifactId", "version"):
            properties[f"project.parent.{key}"] = text(parent_node, key)
            properties[f"parent.{key}"] = text(parent_node, key)
    return properties


def raw_dependency(node):
    """Прочитать поля зависимости."""
    keys = (
        "groupId", "artifactId", "version", "scope", "optional", "type",
        "classifier",
    )
    values = {key: text(node, key) for key in keys}
    values["exclusions"] = frozenset(
        text(item, "groupId") + ":" + text(item, "artifactId")
        for item in node.findall("exclusions/exclusion")
    )
    return values


def resolve_row(values, properties):
    """Подставить свойства в поля."""
    result = {key: expand(value, properties) for key, value in values.items()
              if key != "exclusions"}
    result["exclusions"] = frozenset(
        expand(item, properties) for item in values.get("exclusions", ())
    )
    return result


def dependency_key(values):
    """Ключ с типом и классификатором."""
    return (
        values["groupId"], values["artifactId"],
        values.get("type") or "jar", values.get("classifier") or "",
    )


def dependency_name(values):
    """Имя groupId:artifactId."""
    return values["groupId"] + ":" + values["artifactId"]


def make_dependency(values, managed, properties):
    """Собрать и проверить зависимость."""
    values = resolve_row(values, properties)
    name = dependency_name(values)
    defaults = resolve_row(managed.get(dependency_key(values), {}), properties)
    fields = {key: value or defaults.get(key, "")
              for key, value in values.items()}
    version = fields["version"]
    check_coordinate(name, version, False)
    scope = fields["scope"] or "compile"
    if scope not in SUPPORTED_SCOPES:
        raise ValueError(f"POM: неизвестная область зависимости: {scope}")
    optional = fields["optional"] or "false"
    if optional not in {"true", "false"}:
        raise ValueError("POM: optional должен быть true или false")
    return Dependency(
        name, version, scope, optional == "true",
        frozenset(fields["exclusions"]),
    )


TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
MAX_POM_BYTES = 5 * 1024 * 1024
MANAGED_PATH = "dependencyManagement/dependencies/dependency"


def fetch_bytes(url):
    """Скачать POM с повторами."""
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return request_bytes(url)
        except (URLError, OSError) as error:
            last_error = error
    raise ValueError(f"Не удалось получить POM {url}: {last_error}")


def request_bytes(url):
    """Сделать один HTTP-запрос."""
    request = Request(url, headers={"User-Agent": "maven-graph-practice/1.0"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content = response.read(MAX_POM_BYTES + 1)
    if len(content) > MAX_POM_BYTES:
        raise ValueError(f"POM превышает допустимый размер: {url}")
    return content


def pom_url(repository, coordinate):
    """Собрать адрес POM по версии."""
    group, artifact, version = coordinate.split(":")
    check_coordinate(f"{group}:{artifact}", version, False)
    path = group.replace(".", "/")
    return f"{repository}/{path}/{artifact}/{version}/{artifact}-{version}.pom"


def parent_coordinate(root):
    """Найти координаты родителя."""
    node = root.find("parent")
    if node is None:
        return None
    return ":".join(text(node, key) for key in (
        "groupId", "artifactId", "version",
    ))


def management_rows(root, properties):
    """Прочитать dependencyManagement."""
    return [resolve_row(raw_dependency(node), properties)
            for node in root.findall(MANAGED_PATH)]


def bom_coordinates(rows):
    """Найти импортируемые BOM."""
    return [dependency_name(row) + ":" + row["version"] for row in rows
            if row["scope"] == "import" and row["type"] == "pom"]


def assemble_model(root, properties, parent, models):
    """Собрать модель POM."""
    rows = management_rows(root, properties)
    managed = {}
    for coordinate in bom_coordinates(rows):
        bom = models[coordinate]
        for key, value in bom.managed.items():
            managed.setdefault(key, resolve_row(value, bom.properties))
    managed.update(parent.managed)
    for node in root.findall(MANAGED_PATH):
        row = raw_dependency(node)
        resolved = resolve_row(row, properties)
        if resolved["scope"] != "import":
            managed[dependency_key(resolved)] = row
    declarations = dict(parent.declarations)
    for node in root.findall("dependencies/dependency"):
        row = raw_dependency(node)
        declarations[dependency_key(resolve_row(row, properties))] = row
    return PomModel(properties, managed, declarations)


class MavenRepository:
    """Maven-источник с кешем."""

    def __init__(self, repository, fetcher=fetch_bytes):
        """Задать адрес и загрузчик."""
        self.repository = repository.rstrip("/")
        self.fetcher = fetcher
        self.roots = {}
        self.models = {}

    def root(self, coordinate):
        """Взять XML из кеша или сети."""
        if coordinate not in self.roots:
            url = pom_url(self.repository, coordinate)
            self.roots[coordinate] = parse_xml(self.fetcher(url))
        return self.roots[coordinate]

    def prerequisites(self, root, coordinate):
        """Найти нужные parent и BOM."""
        parent_name = parent_coordinate(root)
        if parent_name and parent_name not in self.models:
            return [parent_name]
        parent = self.models.get(parent_name, PomModel())
        properties = properties_for(root, coordinate, parent)
        rows = management_rows(root, properties)
        return [name for name in bom_coordinates(rows)
                if name not in self.models]

    def model(self, coordinate):
        """Собрать модель без рекурсии."""
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
        """Вернуть прямые зависимости."""
        model = self.model(coordinate)
        return [make_dependency(row, model.managed, model.properties)
                for row in model.declarations.values()]
