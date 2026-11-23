# Maven Dependency Visualizer

Практическая работа № 2, вариант 6. Граф зависимостей Maven-пакетов.

## Запуск

Нужны Python 3.10+, Java и [PlantUML JAR](https://plantuml.com/download).
Сборка и установка пакетов pip не требуются. Команды выполняются из корня проекта.

```powershell
$env:PLANTUML_JAR = 'C:\Tools\plantuml.jar'
.\run.bat data\test.csv
python -B -m unittest discover -s tests -v
```

Без bat: `python -B -m src.main data/test.csv`.
В команде укажи свой путь к JAR. Java берется из `JAVA_HOME` или PATH.
Если Python отсутствует в PATH, для `run.bat` задай путь к `python.exe` через `PYTHON`.
PNG и исходник PlantUML сохраняются в `generated/` и не добавляются в Git.

## Настройки

CSV с заголовком `key,value`; все ключи обязательны, пути считаются от CSV.

| Параметр | Значение |
| --- | --- |
| package | `groupId:artifactId`, в тестовом режиме буква A-Z |
| repository | URL Maven-репозитория или путь к тестовому файлу |
| test_mode | `true` для тестового файла, иначе `false` |
| version | Фиксированная версия пакета |
| output | Имя PNG-файла |
| ascii_tree | Вывод ASCII-дерева: `true` или `false` |
| max_depth | Глубина от 0; корень имеет глубину 0 |

## Функции

- `main.py`: `main` принимает путь CSV и сообщает об ошибках, `run` запускает анализ и вывод.
- `config.py`: `read_rows` читает CSV, `boolean` и `depth` преобразуют значения,
  `check_coordinate` проверяет имя и версию, `repository_path`, `repository_url`
  и `output_path` проверяют пути и URL. `load_config` собирает настройки.
- `maven.py`: `pom_url`, `request_bytes`, `fetch_bytes` строят адрес и загружают POM.
  `parse_xml` и `text` читают XML, `expand` и `properties_for` подставляют свойства.
  `raw_dependency` и `resolve_row` читают и раскрывают поля, `dependency_key`
  и `dependency_name` определяют ключ и имя, `make_dependency` собирает зависимость.
  `parent_coordinate`, `management_rows`, `bom_coordinates`, `assemble_model` обрабатывают
  наследование и управляемые версии. `MavenRepository` хранит URL и кеш.
  `root` загружает XML, `prerequisites` ищет parent и BOM, `model` собирает модель,
  `direct` возвращает зависимости. `Dependency.coordinate` возвращает имя с версией.
- `graph.py`: `analyze` выбирает источник, `build_graph` выполняет BFS через очередь.
  `runtime_dependencies` и `excluded` фильтруют зависимости, `add_edge` сохраняет ребра.
  `parse_test_line` и `read_graph` читают тестовый файл. `TestRepository` хранит его граф
  и версию, `direct` возвращает тестовые зависимости. `reverse_edges` строит обратные
  списки смежности, `load_order` вычисляет порядок по Кану.
- `visualizer.py`: `escape_label` экранирует подписи, `to_plantuml` формирует диаграмму,
  `java_command` и `render_png` вызывают локальный PlantUML, `save_visualization` пишет файлы.
  `ascii_tree` печатает дерево через стек, `push_children` и `node_marker` управляют ветками.

## Примеры

```console
python -B -m src.main data/junit.csv
python -B -m src.main data/commons-text.csv
python -B -m src.main data/slf4j-simple.csv
```

В `data/test_repo.txt` строки имеют вид `A -> B, C`, для листа — `D ->`.
В `data/test.csv` можно выбрать корень: A — ромб, E — цикл, H — цепочка,
L — лист. Для H при `max_depth=1` получается только H -> I.

Сравнение с `mvn dependency:tree -Dscope=runtime` (Maven 3.9.9):

| Пакет | Зависимость, совпавшая с Maven |
| --- | --- |
| junit:junit:4.13.2 | org.hamcrest:hamcrest-core:1.3 |
| org.apache.commons:commons-text:1.10.0 | org.apache.commons:commons-lang3:3.12.0 |
| org.slf4j:slf4j-simple:2.0.13 | org.slf4j:slf4j-api:2.0.13 |

Порядок загрузки для ромба: D, B, C, A; для цикла порядок невозможен.
Для JUnit программа ставит Hamcrest раньше JUnit. Maven скачивал JAR в обратном
порядке: скачивание архива не требует готовности его зависимостей.
В граф входят обязательные compile/runtime-зависимости. Профили, диапазоны
версий, SNAPSHOT, relocation и разрешение конфликтов версий не реализованы.

Для повторения сравнения установи Maven. Во вспомогательном POM по умолчанию JUnit.
Для других пакетов передай `-Dsample.group=...`, `-Dsample.artifact=...` и `-Dsample.version=...`.
Для графа в DOT добавь `-DoutputType=dot` к `dependency:tree`.

```powershell
New-Item -ItemType Directory -Force generated | Out-Null
git show stage-5:examples/maven/pom.xml | Set-Content -Encoding utf8 generated/compare.xml
mvn -B -f generated/compare.xml dependency:tree -Dscope=runtime
mvn -B -f generated/compare.xml '-Dmaven.repo.local=generated/maven-cache' `
  '-Dmaven.artifact.threads=1' dependency:resolve
```

## Этапы

Переключение: `git switch --detach stage-4`. Возврат: `git switch main`.
На метках используются файлы из `examples/`.

| Метка | Пример для `run.bat` | Что проверять |
| --- | --- | --- |
| `stage-1` | `examples/junit.csv` | Вывод настроек. Ошибки семи параметров проверяют тесты |
| `stage-2` | `examples/junit.csv` | Прямые зависимости и области действия |
| `stage-3` | `examples/diamond.csv`, `cycle.csv`, `chain.csv`, `leaf.csv` | BFS, цикл, глубина и лист |
| `stage-4` | `examples/diamond.csv`, `cycle.csv`, `chain.csv`, `leaf.csv` | Порядок и ошибка для цикла |
| `stage-5` | Три Maven CSV из `examples/` | PlantUML, PNG и ASCII-дерево |
