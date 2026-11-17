"""Разбор XML POM и подстановка свойств стандартной библиотекой."""

import re
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass, field

from .config import check_coordinate


PROPERTY = re.compile(r"\$\{([^}]+)\}")
SUPPORTED_SCOPES = {
    "compile", "runtime", "test", "provided", "system", "import",
}


@dataclass(frozen=True)
class Dependency:
    """Координаты зависимости и метаданные ее ребра в графе."""

    name: str
    version: str
    scope: str = "compile"
    optional: bool = False
    exclusions: frozenset = frozenset()

    @property
    def coordinate(self):
        """Вернуть полные координаты groupId:artifactId:version."""
        return f"{self.name}:{self.version}"


@dataclass
class PomModel:
    """Эффективные свойства, управление версиями и декларации POM."""

    properties: dict = field(default_factory=dict)
    managed: dict = field(default_factory=dict)
    declarations: dict = field(default_factory=dict)


def parse_xml(content):
    """Прочитать POM с namespace или без него, отклоняя DTD."""
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
    """Получить текст элемента без внешних пробелов."""
    return (node.findtext(path) or default).strip()


def expand(value, properties):
    """Итеративно раскрыть свойства, обнаружив неизвестные ссылки и циклы."""
    seen = set()
    while PROPERTY.search(value):
        if value in seen:
            raise ValueError(f"POM: цикл свойств: {value}")
        seen.add(value)
        for key in PROPERTY.findall(value):
            if key not in properties:
                raise ValueError(f"POM: неизвестное свойство: {key}")
            value = value.replace("${" + key + "}", properties[key])
    return value


def properties_for(root, coordinate, parent):
    """Объединить свойства родителя, проекта и стандартные координаты."""
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


def raw_dependency(node, properties):
    """Прочитать поля одной зависимости и список исключений."""
    keys = (
        "groupId", "artifactId", "version", "scope", "optional", "type",
        "classifier",
    )
    values = {key: expand(text(node, key), properties) for key in keys}
    values["exclusions"] = frozenset(
        expand(text(item, "groupId"), properties) + ":"
        + expand(text(item, "artifactId"), properties)
        for item in node.findall("exclusions/exclusion")
    )
    return values


def dependency_key(values):
    """Различать обычный JAR и test-jar одного Maven-артефакта."""
    return (
        values["groupId"], values["artifactId"],
        values.get("type") or "jar", values.get("classifier") or "",
    )


def dependency_name(values):
    """Получить имя groupId:artifactId независимо от типа артефакта."""
    return values["groupId"] + ":" + values["artifactId"]


def make_dependency(values, managed):
    """Дополнить отсутствующие поля управляемыми значениями и проверить их."""
    name = dependency_name(values)
    defaults = managed.get(dependency_key(values), {})
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
