"""PlantUML, локальный PNG и нерекурсивное ASCII-дерево зависимостей."""

import os
import subprocess
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RENDER_TIMEOUT = 60


def escape_label(value):
    """Экранировать метку PlantUML независимо от источника графа."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def to_plantuml(graph):
    """Сформировать стабильную диаграмму со всеми узлами и ребрами графа."""
    lines = ["@startuml", "!pragma layout smetana", "left to right direction"]
    aliases = {node: f"n{index}" for index, node in enumerate(graph.edges)}
    for node, alias in aliases.items():
        suffix = " [depth limit]" if node in graph.truncated else ""
        label = escape_label(node + suffix)
        lines.append(f'rectangle "{label}" as {alias}')
    for node, children in graph.edges.items():
        for child in children:
            lines.append(f"{aliases[node]} --> {aliases[child]}")
    return "\n".join(lines + ["@enduml", ""])


def java_command():
    """Найти Java и внешний PlantUML JAR, не загружая бинарники в Git."""
    jar = Path(os.environ.get("PLANTUML_JAR", "plantuml.jar"))
    if not jar.is_file():
        raise ValueError("Укажите путь к plantuml.jar в PLANTUML_JAR")
    java_home = os.environ.get("JAVA_HOME")
    java = str(Path(java_home) / "bin" / "java") if java_home else "java"
    return [java, "-Djava.awt.headless=true", "-jar", str(jar.resolve()),
            "-charset", "UTF-8", "-tpng", "-pipe"]


def render_png(source):
    """Локально вызвать PlantUML и проверить результат перед сохранением."""
    try:
        result = subprocess.run(
            java_command(), input=source.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=RENDER_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"Не удалось запустить PlantUML: {error}") from error
    if result.returncode or not result.stdout.startswith(PNG_SIGNATURE):
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"PlantUML не создал PNG: {details}")
    return result.stdout


def save_visualization(graph, output):
    """Сохранить исходник .puml рядом с требуемым изображением .png."""
    source = to_plantuml(graph)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".puml").write_text(source, encoding="utf-8")
    image = render_png(source)
    output.write_bytes(image)


def node_marker(node, path, expanded, graph):
    """Различить цикл, повторную ссылку и границу глубины."""
    if node in path:
        return " [cycle]"
    if node in expanded:
        return " [shared]"
    if node in graph.truncated:
        return " [depth limit]"
    return ""


def push_children(stack, graph, node, prefix, path):
    """Положить детей в стек в обратном порядке для стабильного вывода."""
    children = graph.edges[node]
    last_index = len(children) - 1
    for index in reversed(range(len(children))):
        stack.append((children[index], prefix, index == last_index, path))


def ascii_tree(graph):
    """Вывести конечное ASCII-дерево; общие узлы и циклы не дублируются."""
    root_marker = " [depth limit]" if graph.root in graph.truncated else ""
    lines = [graph.root + root_marker]
    expanded = {graph.root}
    stack = []
    push_children(stack, graph, graph.root, "", frozenset({graph.root}))
    while stack:
        node, prefix, last, path = stack.pop()
        marker = node_marker(node, path, expanded, graph)
        connector = "`-- " if last else "|-- "
        lines.append(prefix + connector + node + marker)
        if marker:
            continue
        expanded.add(node)
        child_prefix = prefix + ("    " if last else "|   ")
        push_children(stack, graph, node, child_prefix, path | {node})
    return "\n".join(lines)
