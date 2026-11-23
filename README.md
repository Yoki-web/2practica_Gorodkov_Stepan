# Maven Dependency Visualizer

Практика № 2, вариант 6. Граф зависимостей Maven.

## Запуск

Python 3.10+, Java и PlantUML. Сборка не требуется. Пути к инструментам локальные.

```powershell
$demoPyRoot = 'C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1119-907-0_26.1119.907.0_x64__3k8sg7r9htsxt'
$env:PYTHON = Join-Path $demoPyRoot 'dependencies\python\python.exe'
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21.0.12.1'
$env:PLANTUML_JAR = 'C:\Users\stepa\Documents\Codex\2026-11-17\x20\work\tools\plantuml.jar'
$env:PYTHONUTF8 = '1'
.\run.bat config.csv
```

Результаты — PNG и `.puml` в `generated/`. Тесты — `& $env:PYTHON -B -m unittest -q`.

## Тестовые графы

| Строки в `config.csv` | Результат |
| --- | --- |
| `package,A`, `max_depth,10` | Ромб. D — общая зависимость (`[shared]`). |
| `package,A`, `max_depth,1` | A, B и C. D за пределами глубины. |
| `package,E`, `max_depth,10` | Цикл E → F → G → E (`[cycle]`). |

## JUnit

```csv
package,junit:junit
repository,https://repo.maven.apache.org/maven2
test_mode,false
version,4.13.2
output,generated/junit.png
```

`package`, `version` — пакет и версия. `repository` — TXT или URL. `test_mode` — выбор источника.
`output` — путь PNG, `ascii_tree` — вывод дерева, `max_depth` — предел глубины.
BFS — построение графа. DFS — вывод дерева. PlantUML — рендеринг PNG.
Порядок загрузки — [stage-4](../../tree/stage-4). Три примера и сравнение с Maven — [stage-5](../../tree/stage-5).
