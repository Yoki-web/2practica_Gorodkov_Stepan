# Maven Dependency Visualizer

Практическая работа № 2, вариант 6. Граф зависимостей Maven-пакетов.

## Запуск

Python 3.10+, Java и PlantUML JAR. Сборка и пакеты pip не нужны.
Путь к JAR задается через `PLANTUML_JAR`, Java берется из PATH или `JAVA_HOME`.

```powershell
$env:PLANTUML_JAR = 'C:\Tools\plantuml.jar'
.\run.bat data\test.csv
python -B -m unittest discover -s tests -v
```

Без bat: `python -B -m src.main data/test.csv`.
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

- `config.py`: чтение CSV и проверка всех настроек.
- `maven.py`: загрузка POM, свойства, parent и dependencyManagement/BOM.
- `graph.py`: BFS без рекурсии, глубина, циклы и порядок загрузки по Кану.
- `visualizer.py`: PlantUML, локальный PNG и ASCII-дерево.
- `main.py`: запуск и вывод ошибок. Тесты находятся в `tests/test_main.py`.

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

Этапы: `stage-1`–`stage-5` со своими README. Просмотр: `git switch --detach stage-4`; возврат: `git switch main`.
