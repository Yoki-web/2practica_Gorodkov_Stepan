# Maven Dependency Visualizer

Практика № 2, вариант 6. Граф зависимостей Maven-пакетов по POM или тестовому файлу.

## Запуск

Python 3.10+, Java и [PlantUML JAR](https://plantuml.com/download). Сборка не нужна.

```powershell
$env:PLANTUML_JAR = 'C:\Tools\plantuml.jar'
.\run.bat config.csv
python -B -m unittest -v
```

Укажи путь к своему JAR. Без `run.bat` — `python -B -m src.main config.csv`.
При необходимости задай путь к Python через `PYTHON`, к Java — через `JAVA_HOME`.
PNG и PlantUML сохраняются в `generated/`.

## Настройки

`package` — имя пакета, `version` — версия, `repository` — URL или путь к TXT.
`test_mode=true` выбирает TXT с пакетами A–Z, `false` — Maven и имя `groupId:artifactId`.
`output` — путь к PNG, `ascii_tree` — вывод в терминал, `max_depth` — глубина от 0.
Относительные пути считаются от `config.csv`.

## Функции

- [config.py](src/config.py) и [main.py](src/main.py) проверяют CSV и запускают анализ.
- [maven.py](src/maven.py) загружает POM и раскрывает свойства, наследование и управляемые версии.
- [graph.py](src/graph.py) читает TXT, строит граф BFS без рекурсии и считает порядок загрузки.
- [visualizer.py](src/visualizer.py) печатает дерево через стек и сохраняет PlantUML и PNG.

## Примеры

Тестовый `config.csv` запускает ромб от A. Корень E показывает цикл, H — цепочку, L — лист.
Для Maven задай `test_mode,false` и `repository,https://repo.maven.apache.org/maven2`.
Для каждой строки ниже подставь имя и версию в `package` и `version` и запусти ту же команду.

| Пакет | Версия | Зависимость из `dependency:tree -Dscope=runtime` |
| --- | --- | --- |
| `junit:junit` | `4.13.2` | `org.hamcrest:hamcrest-core:1.3` |
| `org.apache.commons:commons-text` | `1.10.0` | `org.apache.commons:commons-lang3:3.12.0` |
| `org.slf4j:slf4j-simple` | `2.0.13` | `org.slf4j:slf4j-api:2.0.13` |

Графы совпали с Maven для этих примеров. Граф включает обязательные compile/runtime-зависимости.
Профили, диапазоны, SNAPSHOT, relocation и разрешение конфликтов версий не реализованы.

Этапы сохранены в `stage-1`–`stage-5`. На метках конфигурации лежат в `examples/`.
На этапе 4 ромб даёт D, B, C, A. Для JUnit Hamcrest стоит раньше JUnit по зависимостям,
хотя Maven первым начал скачивать JUnit. Скачивание JAR может идти до готовности его зависимостей.
Команды сравнения и POM находятся в [этапе 5](https://github.com/Yoki-web/2practica_Gorodkov_Stepan/tree/stage-5).
