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
   приложениями (KiCad, FreeCAD, ngspice, FEMM): открывает, закрывает,
   перезапускает — без ручного вмешательства пользователя.
3. **Кроссплатформенность.** Linux и Windows как минимально
   поддерживаемые платформы.

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
Намоточные ────── PyOpenMagnetics + FEMM + MVB
изделия           (трансформаторы, дроссели)
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
| Верификация магнитных полей | FEMM + pyFEMM | 0 |
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
| **Bootstrap (Linux + Windows)** | **Наша разработка** | **~500 строк bash+ps1** |

**Собственный код: ~5200 строк. Всё остальное — интеграция готовых
open-source решений.**

## Быстрый старт

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

**Что дальше — Фаза 1a (MVP-ядро):** bootstrap-скрипты Linux/Windows,
KiCad↔SPICE bridge, SPICE-модели ламп, базовые анализы OP/tran/AC,
логирование сессий. Задачи декомпозированы в `BACKLOG.md` (T002–T010,
T050 и далее по фазам).

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
