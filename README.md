# Maven Dependency Visualizer

Практика № 2, вариант 6. Граф зависимостей Maven.

## Запуск

Python 3.10+, Java и PlantUML. Сборка не нужна. Пути ниже для моего ПК.

```powershell
$demoPyRoot = 'C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1119-907-0_26.1119.907.0_x64__3k8sg7r9htsxt'
$env:PYTHON = Join-Path $demoPyRoot 'dependencies\python\python.exe'
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21.0.12.1'
$env:PLANTUML_JAR = 'C:\Users\stepa\Documents\Codex\2026-11-17\x20\work\tools\plantuml.jar'
$env:PYTHONUTF8 = '1'
.\run.bat config.csv
```

PNG и `.puml` лежат в `generated/`. Тесты — `& $env:PYTHON -B -m unittest -q`.

## Проверка

Меняю строки в `config.csv`, сохраняю и снова запускаю `run.bat`.

| Что поставить в `config.csv` | Что показать преподавателю |
| --- | --- |
| `package,A`, `max_depth,10` | Ромб с двумя стрелками к D. В дереве второй D помечен `[shared]`. |
| `package,A`, `max_depth,1` | Остаются A, B и C. D за пределами глубины. |
| `package,E`, `max_depth,10` | Цикл E → F → G → E. Есть `[cycle]`, обход завершился. |

Для проверки JUnit меняю эти строки:

```csv
package,junit:junit
repository,https://repo.maven.apache.org/maven2
test_mode,false
version,4.13.2
output,generated/junit.png
```

`package` и `version` задают пакет. `test_mode` выбирает TXT или URL из `repository`.
`output` задаёт PNG, `ascii_tree` включает дерево, `max_depth` ограничивает глубину.
Граф строится BFS из TXT или POM. DFS выводит дерево, PlantUML рисует PNG.
Порядок загрузки — [stage-4](../../tree/stage-4). Три примера и сравнение с Maven — [stage-5](../../tree/stage-5).
