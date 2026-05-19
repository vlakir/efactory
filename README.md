# efactory

Система сквозного проектирования РЭА (радиоэлектронной аппаратуры) на
базе ИИ — от идеи до полного пакета производственной документации.
Охватывает аналоговую, цифровую и смешанную схемотехнику: разработка
и оптимизация схемы → SPICE-моделирование → проектирование PCB →
проектирование намоточных изделий → проектирование корпуса →
формирование производственной документации.

Построена на MCP-серверах и универсальном чат-клиенте с поддержкой
нескольких LLM-бэкендов (Claude Code Max без API, Anthropic API,
OpenAI-совместимые API, Ollama). Полное видение проекта зафиксировано
в `CONCEPT.md` (immutable). Текущее состояние ведётся здесь и в
`CHANGELOG.md`.

## Принципы

1. **Максимальное использование готовых решений, минимум собственного
   кода.** Система — тонкий оркестрационный слой над готовыми
   MCP-серверами и Python-библиотеками. Архитектурное обоснование —
   в `DECISIONS.md`.
2. **Максимальная автоматизация.** Система сама управляет внешними
   приложениями (KiCad, FreeCAD, ngspice, FEM-solver): открывает,
   закрывает, перезапускает — без ручного вмешательства пользователя.
3. **Distribution через Linux Docker image.** Весь стек (KiCad,
   ngspice, FreeCAD, FEM-solver, Python, Claude Code, MCP-серверы)
   упакован в один воспроизводимый образ; пользователь запускает
   единым `efactory-up`. Кроссплатформенность (Mac/Windows) —
   отдельная Phase Cross-platform после стабилизации Linux-only
   workflow. ADR — `DECISIONS.md` (2026-05-19, Distribution: Linux
   Docker image).

## Сквозной пайплайн

```text
Идея / ТЗ на устройство
    ↓
Схемотехника ──── KiCad + mcp-kicad-sch-api
    ↓
Моделирование ─── ngspice + SPICEBridge
    ↓  ↺ итеративная оптимизация
Валидация ─────── ERC/DRC/DFM + kicad-mcp-pro
    ↓
PCB-дизайн ────── kicad-mcp-pro + FreeRouting
    ↓
Намоточные ────── PyOpenMagnetics + FEM-solver + MVB
изделия           (трансформаторы, дроссели; FEM-solver — Elmer
                  primary, см. DECISIONS.md 2026-05-19)
    ↓
Корпус ────────── FreeCAD + freecad-mcp
    ↓
Документация ──── полный пакет для производства
    │
    ├── Схема (PDF/SVG)
    ├── BOM (CSV/XLSX)
    ├── Gerber + drill
    ├── Pick-and-place
    ├── Спецификации намоточных изделий
    ├── Развёртки корпуса (DXF)
    ├── 3D-модель сборки (STEP)
    ├── Отчёт о моделировании
    └── Сборочный чертёж
```

## Соотношение готового и своего

Сводка из CONCEPT.md §18 — что берём готовое, что пишем сами.

| Компонент | Источник | Объём своего кода |
|-----------|----------|-------------------|
| Создание схем | kicad-sch-api + MCP-сервер (PyPI) | 0 |
| Проект / PCB / валидация / экспорт | kicad-mcp-pro (PyPI) | 0 |
| Моделирование | SPICEBridge (GitHub) | 0 |
| Python↔ngspice | PySpice (PyPI) | 0 |
| Экспорт нетлистов / SVG | kicad-cli (KiCad) | 0 |
| Модели ламп | Koren / Ayumi / Duncan | ~50 строк (конвертация) |
| Curve-fitting | Gleb Zaslavsky tool (GitHub) | 0 |
| Автотрассировка | FreeRouting (встроен в kicad-mcp-pro) | 0 |
| pcbnew API | KiCad built-in | 0 |
| Проектирование корпусов | FreeCAD + freecad-mcp (GitHub) | 0 |
| Расчёт намоточных изделий | PyOpenMagnetics + transformer_designer | 0 |
| 3D-модели магнитных компонентов | MVB (OpenMagnetics → FreeCAD) | 0 |
| Верификация магнитных полей | Elmer FEM / GetDP (Linux-native, выбор по T113) | ~50–100 строк (MAS → solver input) |
| **Оркестрация схем (bridge)** | **Наша разработка** | **~500 строк Python** |
| **Оркестрация PCB (pcb bridge)** | **Наша разработка** | **~300 строк Python** |
| **Навесной монтаж (P2P bridge)** | **Наша разработка** | **~250 строк Python** |
| **Помехозащита / безопасность** | **Наша разработка** | **~200 строк Python** |
| **Wizard БП** | **Наша разработка** | **~200 строк Python** |
| **Оркестрация намоточных изделий** | **Наша разработка** | **~300 строк Python** |
| **Оркестрация корпусов** | **Наша разработка** | **~200 строк Python** |
| **Управление проектами (project.yaml, DDR, sessions)** | **Наша разработка** | **~400 строк Python** |
| **Производственная документация + sourcing** | **Наша разработка** | **~400 строк Python** |
| **Импорт измерений** | **Наша разработка** | **~150 строк Python** |
| **Менеджер приложений + платформа** | **Наша разработка** | **~300 строк Python** |
| **Чат-клиент (UI + MCP-клиент + бэкенды)** | **Наша разработка** | **~1500 строк Python** |
| **Containerization (Linux Docker image)** | **Наша разработка** | **~150–200 строк Dockerfile + shell wrapper** |

**Собственный код: ~4800 строк (после ухода от bootstrap-скриптов).
Всё остальное — интеграция готовых open-source решений в одном
Docker-образе.**

## Быстрый старт

### Для пользователя (target state, реализация — Phase 0.9)

Distribution через Linux Docker image (см. ADR от 2026-05-19).
Целевой workflow:

```bash
# Один раз — pull образа с pinned версиями всего стека
docker pull ghcr.io/vlakir/efactory:linux-latest

# Запуск рабочей станции efactory (GUI окна KiCad/FreeCAD
# выкидываются через X11/Wayland passthrough хосту)
./efactory-up
```

`efactory-up` — wrapper-скрипт в корне репо (T114): pre-flight,
xhost setup, libraries bootstrap (T121), mount проектов и
persistent state, locale pass-through, опциональный GPU passthrough.
Платформа: **Linux only в текущей фазе**; Mac/Windows — Phase
Cross-platform.

### Запуск KiCad GUI из контейнера (current state, T114+T121)

Один раз — собрать оба образа:

```bash
docker build -t efactory:linux .                          # ~2.5 GB
docker build -f Dockerfile.libs -t efactory-libs:linux-dev .  # ~450 MB
# Опционально — 3D-модели для PCB-preview (~4 GB):
# docker build -f Dockerfile.libs --build-arg INCLUDE_3DMODELS=1 \
#     -t efactory-libs:linux-dev-3d .
```

Дальше — `efactory-up` сам делает остальное:

```bash
./efactory-up                       # стартует KiCad GUI; первый
                                    # запуск bootstrap'ит libraries
                                    # из efactory-libs image в
                                    # $HOME/efactory-libs/
./efactory-up --update-libs         # пересоздать libraries
./efactory-up --update-libs --with-3dmodels   # подтянуть 3D-модели
./efactory-up --headless            # запустить pytest в контейнере
./efactory-up --demo                # открыть SE-amp 6П14П demo
./efactory-up --version             # показать EFACTORY_VERSION
./efactory-up -- --pcb              # форвардинг KiCad-аргументов
```

Smoke-проверка X11 passthrough (без интерактивного окна KiCad):

```bash
./scripts/smoke-gui.sh
```

Demo-проект для ручного прогона Simulator (SE-amp 6П14П, та же
топология что в интеграционном acceptance-тесте):

```bash
# Сгенерировать demo-dir в $HOME/efactory-projects/se-amp-demo/
# (efactory-up --demo делает это автоматически, если фикстуры нет)
uv run python scripts/gen-se-amp-demo.py
./efactory-up --demo
```

В GUI: Tools → Simulator → Run, чтобы прогнать `.tran 10u 80m 10m
uic` и увидеть на plate-net AC-амплификацию 5–7× от 10mV input.

**Что mount'ит efactory-up:**

| Host | Container | Назначение |
|---|---|---|
| `$HOME/efactory-projects/` | `/workspace/` | Проекты пользователя |
| `$HOME/efactory-libs/{symbols,footprints,template,3dmodels}/` | `/usr/share/kicad/{symbols,footprints,template,3dmodels}/` | KiCad system libraries (T121, ro) |
| `$HOME/efactory-state/{config,cache,local}/` | `/opt/efactory/.{config,cache,local}/` | Persistent KiCad state (setup wizard, settings) |
| `/tmp/.X11-unix/` | `/tmp/.X11-unix/` | X11 socket |
| `$XAUTHORITY` | `/efactory/.Xauthority` | X11 auth cookie (ro) |

Wayland-сессии (Ubuntu 24.04 GNOME по умолчанию) работают через
XWayland-bridge без изменений. Native Wayland-passthrough
(`-v /run/user/$UID/wayland-0:/run/user/$UID/wayland-0`) пока не
добавлен — пилим, когда появится Wayland-only сценарий.

### Для разработчика efactory (текущий режим разработки)

Менеджер зависимостей и окружения: **`uv`** (выбран при
`dreamteam init`).

```bash
uv sync                                       # поставить зависимости
uv run efactory project create --name myprj   # создать новый проект
uv run efactory project list                  # все проекты
uv run efactory project show --name myprj     # подробности
uv run efactory project update myprj --phase schematic --status in_progress
uv run efactory project delete --name myprj
```

По умолчанию данные кладутся в `$XDG_DATA_HOME/efactory/`
(или `$HOME/.local/share/efactory/`, если переменная не задана):
каталоги проектов — `projects/<name>/`, SQLite-индекс —
`efactory.db`. Переопределить пути можно через env-переменные
`EFACTORY_PROJECTS_ROOT` / `EFACTORY_DATABASE_URL` либо через файл
`.secrets` в директории запуска (уже в `.gitignore`).

### Manifest как источник истины (T098)

В каталоге каждого проекта лежит `project.yaml` — это **источник
истины**: имя, фазы, временные метки. SQLite — быстрый индекс для
`list`; всё остальное (`show`, `update`) читает manifest напрямую.

Практические следствия:

- **Портативность.** Папку проекта (`<storage_root>/<name>/`) можно
  целиком архивировать, переносить на другую машину, распаковывать,
  запускать `efactory project reindex` — индекс восстановится.
- **Ручная правка.** `project.yaml` можно редактировать руками
  (например, пометить фазу как `done`); `show` сразу покажет
  изменения, `list` подтянет их после `reindex`.

```bash
uv run efactory project reindex                    # пересобрать SQL индекс
uv run efactory project reindex --remove-orphans   # + удалить SQL-only записи
```

`reindex` идемпотентен и работает в обе стороны: manifest → SQL
(основной режим) и SQL → manifest (bootstrap для проектов,
созданных до T098).

### Журнал проектных решений (T099, CONCEPT §4.4)

Каждое значимое решение фиксируется как markdown файл
`<project>/decisions/D###_<slug>.md`. Краткая запись попадает
в `project.yaml → decisions:` (индекс), детали — в markdown
(`# Headline`, `Дата`, `Статус`, `Summary`, `Rationale`,
опционально `Evidence` и `Сессия`).

```bash
uv run efactory decision add --project myprj \
    --title "Choose SE topology" \
    --summary "SE для наушников" \
    --rationale "Меньше искажений, достаточная мощность"
uv run efactory decision list --project myprj
uv run efactory decision show --project myprj --id D001
```

ID присваивается автоматически (D001, D002, …). Можно
дополнять файлы руками — `reindex` подтянет изменения в
manifest; неизвестные секции (например, `## Context`) не ломают
парсер.

## Состояние проекта (0.3.0)

После релиза **0.3.0** ядро domain-модели готово к Фазе 1a
дорожной карты (CONCEPT §13):

- Полный CRUD по `Project` через CLI.
- 6 канонических фаз (schematic / simulation / pcb / magnetics /
  enclosure / documentation) + derived `Project.status`.
- Manifest YAML как источник истины (портативность,
  ручное редактирование, `reindex`).
- Журнал проектных решений (markdown DDR + индекс в manifest).
- Hexagonal-фундамент (5 use cases + ReindexProjects + Decision
  CRUD) без правок ADR.

**Что дальше — Phase 0.9 Containerization** (новая фаза, добавлена
2026-05-19 архитектурным решением о Docker distribution).
Базовый Dockerfile с полным стеком (KiCad из official-репов,
ngspice, FreeCAD, Linux-native FEM-solver, Python, Claude Code,
MCP-серверы), GUI passthrough, `efactory-up` wrapper, CI-сборка
образа. После этого — продолжение Phase 1a (KiCad↔SPICE bridge,
SPICE-модели ламп, базовые анализы) и Phase 1b (LLM chat-client
внутри контейнера). Задачи — `BACKLOG.md`, T110–T115 (Containerization)
и далее по фазам.

**T002 (bootstrap.sh Linux)** заменён на T110 (Dockerfile);
**T003 (bootstrap.ps1 Windows)** парковано в Tech Debt до Phase
Cross-platform.

## Зависимости

```bash
uv add <pkg>                  # runtime
uv add --dev <pkg>            # dev
```

## Проверки перед push

Гейт из 5 проверок (все должны проходить с 0 ошибок):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest
```

Гейт автоматизирован через [pre-commit](https://pre-commit.com) на
stage `pre-push`. После клонирования достаточно:

```bash
uv sync
```

Hook ставится автоматически — `uv sync` дёргает hatchling custom
build hook (`hatch_build.py`), который запускает `pre-commit install
--hook-type pre-push` в проектном `.venv/`. ADR — `DECISIONS.md`
(T095). Существующий `.git/hooks/pre-push` (защита `main` от прямого
push) сохраняется в `pre-push.legacy` и запускается первым.

Если автоустановка по какой-то причине не сработала (например, `.git/`
отсутствует или `uv` не на PATH в момент build'а) — ручной запуск
работает как fallback:

```bash
uv run pre-commit install --hook-type pre-push
```

После этого `git push` сам прогонит все 5 проверок и заблокирует
push, если что-то не зелёное.

Запустить проверки без push:

```bash
uv run pre-commit run --all-files --hook-stage pre-push
```

Если нужно скипнуть конкретный hook (только если знаешь зачем):

```bash
SKIP=pytest git push
git push --no-verify   # пропускает все pre-push hooks
```

Обходные манёвры (`# noqa`, `# type: ignore`, расширение
`ignore`-секции) — только по согласованию.

## Структура проекта

- `src/` — корень исходников.
- `CONCEPT.md` — изначальное видение проекта (immutable).
- `DECISIONS.md` — архитектурные решения с обоснованиями (ADR-Lite).
- `BOARD.md` — рабочая Kanban-доска (To Do / Doing / Done).
- `BACKLOG.md` — парковка идей и побочных находок; на этапе
  bootstrap также содержит roadmap-задачи декомпозиции концепта.
- `CHANGELOG.md` — журнал заметных изменений.
- `specs/` — спецификации крупных фич.
- `CLAUDE.md` — проектные правила для Claude (Claude Code).

## Методика работы

Проект создан из шаблона
[vlakir/dreamteam](https://github.com/vlakir/dreamteam). Подробное
описание методики (scope discipline, ритуал spec/clarify/analyze для
крупных фич, pre-push контроль) — см. репозиторий шаблона.

<!-- Ниже добавляются проект-специфичные разделы: API, развёртывание,
     схемы БД, документация модулей, контакты и т.п. -->
