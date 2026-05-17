# Changelog

История заметных изменений. Формат — упрощённый
[Keep a Changelog](https://keepachangelog.com/).

Записи группируются по версиям или датам релизов. Для проектов без
формального версионирования допустимо использовать дату как заголовок.

Категории:
- **Added** — новая функциональность.
- **Changed** — изменения в существующей функциональности.
- **Fixed** — исправления багов.
- **Removed** — удалённая функциональность.
- **Deprecated** — то, что помечено к удалению, но пока работает.
- **Security** — изменения, важные с точки зрения безопасности.

Если изменение связано с задачей из `BOARD.md` / `BACKLOG.md`,
запись **обязательно** содержит T-ID в скобках, например:
`Added: Превью постов в Telegram (T<NNN>).` Это сохраняет уникальность
T-ID между релизами — `CHANGELOG.md` единственное persistent-
хранилище номеров завершённых задач (см. правило нумерации
в `README.md`).

---

## [Unreleased]

### Added
- `composition/settings.py`: XDG-style default'ы для `projects_root`
  и `database_url` через `Field(default_factory=...)` —
  `$XDG_DATA_HOME/efactory/{projects,efactory.db}` или
  `$HOME/.local/share/efactory/...` если переменная не задана.
  Walking Skeleton CLI работает из чистого окружения без обязательного
  `.secrets` или env (`Settings()` больше не падает с
  `ValidationError`). Явное переопределение через
  `EFACTORY_PROJECTS_ROOT` / `EFACTORY_DATABASE_URL` или
  `.secrets`-файл остаётся возможным и имеет приоритет над default'ами. (T087)
- `composition/main.py`: хелпер `_ensure_storage_dirs` — composition
  root до запуска Alembic-миграций создаёт `projects_root` и
  родительский каталог SQLite-файла (URL парсится через
  `sqlalchemy.engine.make_url`, не-SQLite драйверы пропускаются). (T087)
- Тесты: `tests/unit/composition/test_settings.py` (3 теста —
  XDG-default, XDG_DATA_HOME override, env override) и
  `tests/integration/composition/test_main.py` (1 тест — `build_cli_app`
  без env создаёт storage-каталоги и сквозной use case работает). (T087)
- В `BACKLOG.md` новый раздел «Архитектурные follow-up'ы Walking
  Skeleton» с задачей **T087** — дать `Settings` разумные default'ы
  для `projects_root` / `database_url`, чтобы Walking Skeleton CLI
  работал из коробки. Выявлено при работе над T086. (T086, закрыт в T087)

### Changed
- README «Быстрый старт» упрощён до двух строчек —
  `uv sync && uv run efactory project create --name myprj`. Блок
  создания `.secrets` (введённый в T086) убран после появления
  default'ов `Settings`. `.secrets`/env описаны справочно как
  способ переопределить пути по умолчанию. (T087)
- README «Быстрый старт» (предыдущая итерация в T086): устаревшая
  команда `uv run python src/main.py` заменена на Walking Skeleton
  CLI `uv run efactory project create --name <name>` + блок создания
  `.secrets` (на тот момент `Settings()` падал с `ValidationError` без
  явных env). Промежуточное состояние, схлопнутое в T087. (T086)

### Fixed
- Уточнение к Retrospective `[0.1.0]`: пункт «снять
  "провизорный" статус с ADR про Kùzu в `DECISIONS.md`»
  был ошибочным — статус снят финальным squash-коммитом T085
  (см. `DECISIONS.md` ADR «Kùzu как embedded граф-БД для
  топологий», раздел Последствия → Статус). Попал в ретро
  по неточной session-memory: запись «сделаем при следующей
  правке DECISIONS» не была сверена с актуальным состоянием
  ADR. Сам блок Retrospective как часть milestone-snapshot
  `[0.1.0]` не редактируется. (T086)

---

## [0.1.0] — 2026-05-17

Первый осмысленный milestone проекта: концепт проекта зафиксирован в
живой документации, дорожная карта разложена по фазам в backlog,
заложен архитектурный фундамент (hexagonal, TDD, async) и проверен
Walking Skeleton сквозного use case.

### Added
- Разложение `CONCEPT.md` v5.1 (immutable) по живой проектной
  документации: цель / принципы / диаграмма пайплайна / таблица
  «готовое vs своё» в `README.md`; 7 ADR в `DECISIONS.md`
  (архитектурный принцип MCP-обвязки, выбор kicad-sch-api,
  kicad-mcp-pro, SPICEBridge, PyOpenMagnetics+FEMM,
  FreeCAD+freecad-mcp, стратегия версионирования через
  `compatibility.toml`); 49 задач (`T002`–`T050`) по фазам
  1a/1b/2/3/4 дорожной карты в `BACKLOG.md`. (T001)
- Декомпозиция фаз 5 (намоточные изделия), 6 (корпус),
  7 (производственная документация), 8 (будущее) дорожной
  карты CONCEPT.md §13 в `BACKLOG.md`: 34 задачи
  (`T051`–`T084`). (T050)
- Архитектурный фундамент проекта:
  - **Фаза 0 (дизайн).** Спецификация
    `specs/T085-architecture-foundation/spec.md` (Analyzed) и
    9 ADR в `DECISIONS.md` — Hexagonal Architecture, TDD-first,
    async-first, Pydantic v2 domain + отдельные persistence-
    модели, ручная DI-композиция, SQLAlchemy 2.0 + aiosqlite +
    Alembic для метаданных, Kùzu для графа топологий
    (провизорно), pydantic-settings для конфига, import-linter
    для автоматической изоляции слоёв.
  - **Фаза 1 (скелет).** Структура `src/` по hexagonal-слоям
    (`domain/`, `application/`, `ports/{inbound,outbound}/`,
    `adapters/{inbound,outbound}/`, `composition/`) с README в
    каждой папке слоя. Runtime-зависимости (`pydantic`,
    `pydantic-settings`, `sqlalchemy[asyncio]`, `aiosqlite`,
    `alembic`, `kuzu`, `typer`) и dev-зависимость `import-linter`
    в `pyproject.toml`. Editable-install 5 верхнеуровневых
    слоёв через `[build-system]` (hatchling-`packages`). Alembic
    инициализирован с async-шаблоном (`migrations/` внутри
    SQL-адаптера, исключены из ruff/mypy/coverage), стартовая
    пустая миграция-плейсхолдер. Kùzu Critical #1 закрыт: wheel
    под Python 3.14 работает, sync API обёрнут в
    `asyncio.to_thread` — подтверждено integration-smoke-тестом
    `tests/integration/adapters/graph_store/test_kuzu_smoke.py`.
    `import-linter` сконфигурирован: layers contract
    (composition → adapters → application → ports → domain)
    + forbidden contract для `domain` (запрет
    sqlalchemy/aiosqlite/alembic/kuzu/mcp/anthropic/typer).
    Все 5 проверок качества (ruff / format / mypy / pytest /
    lint-imports) зелёные.
  - **Фаза 2 (Walking Skeleton).** Сквозной use case
    `CreateProject` (`efactory project create --name <name>`) через
    все слои end-to-end по TDD outside-in:
    - `domain.Project` — Pydantic v2 aggregate (id UUID, name с
      инвариантом non-empty, path, created_at TZ-aware, статус
      ProjectStatus enum).
    - `application.create_project` — тонкий use case, оркестрирует
      два outbound-порта.
    - `ports.outbound.MetadataRepository` и `ProjectFileRepository` —
      Protocol-интерфейсы.
    - `adapters.outbound.persistence_sql` — модели SQLAlchemy 2.0
      typed declarative, явный mapping `domain ↔ persistence`,
      реализация `MetadataRepository`, утилита запуска Alembic-
      миграций (`migrations_runner`), revision
      `create_projects_table` через autogenerate.
    - `adapters.outbound.file_store.FilesystemProjectFileRepository`
      — создание директории проекта через `asyncio.to_thread`.
    - `adapters.inbound.cli` — Typer-app с командой
      `project create --name`, зависимости пробрасываются через
      фабрику `build_app(...)`.
    - `composition.settings.Settings` — pydantic-settings (env
      prefix `EFACTORY_`, optional `.secrets` file).
    - `composition.main.build_cli_app` / `run` — composition root:
      Settings → миграции → engine + session_factory → repositories
      → CLI-app. Entry point `efactory = "composition.main:run"`.
    - Третий import-linter контракт: `independence` между
      адаптерами (`adapters.inbound.cli`,
      `adapters.outbound.persistence_sql`, `…file_store`).
    - Тестовый стек: e2e walking skeleton, unit-тесты domain/
      application с fake-портами (без `unittest.mock`), integration
      адаптеров с реальными SQLite и FS в `tmp_path`. Coverage
      ≥ 80% (≈98% после исключения Protocol-портов и
      TYPE_CHECKING-блоков). Все 5 проверок качества зелёные.
    - Штатные настройки плагинов (без подавлений): `pydantic.mypy`
      в mypy, `runtime-evaluated-base-classes` в
      `flake8-type-checking` (для Pydantic/SQLA typed declarative),
      `--import-mode=importlib` в pytest. (T085)

### Retrospective

**Что зашло:**

- Outside-in TDD на T085 дал чистый Walking Skeleton без mock-ов:
  domain/application — fake-порты, адаптеры — integration с реальными
  SQLite/FS в `tmp_path`. Coverage ≈98% при честном (не «mock-fest»)
  тестовом стеке.
- Ритуал **Spec → Clarify → Analyze** на T085 поймал риск Kùzu под
  Python 3.14 на этапе дизайна (Critical #1). В фазе 1 риск закрыли
  smoke-тестом — wheel ставится, sync API работает через
  `asyncio.to_thread`. До блокера дело не дошло.
- Editable install через `hatchling`-`packages` вместо `PYTHONPATH`-
  хака — import-linter нашёл слои «из коробки».
- BACKLOG как буфер: при разложении CONCEPT.md (T001) и
  декомпозиции фаз 5–8 (T050) идеи парковались отдельными T-задачами,
  scope текущей задачи оставался чистым.

**Что не зашло:**

- Парные chore-PR на закрытие BOARD (T001 → PR #2, T050 → PR #4) —
  лишний overhead на ревью и сторонние боты, на каждую задачу ×2 PR
  без самостоятельной ценности. Породило правило (см. ниже).
- CodeRabbit упирался в rate limit на T050 (~40 мин) и на T085
  (58 мин); оба раза мерджили через self-review fallback. Бесплатные
  ревью-боты в критическом пути — ненадёжны.
- `README.md` «Быстрый старт» остался в template-варианте
  (`uv run python src/main.py`) и устарел сразу после T085 — Walking
  Skeleton предоставляет CLI `efactory project create --name <name>`.
  Tech-debt, в следующий milestone.
- `DECISIONS.md` ADR про Kùzu всё ещё помечен «провизорный»; фаза 1
  закрыла этот риск, статус надо снять. Tech-debt, в следующий
  milestone.

**Правки методики (внесены по ходу):**

- **Closing-правка BOARD (Doing → Done) делается прямо в задачном
  PR**, без парного chore-PR. Зафиксировано в проектном и глобальном
  `CLAUDE.md`, в auto-memory проекта
  (`feedback_closing_board_in_task_pr.md`) и в mem0. T085 уже
  закрылся по новому правилу.
- **Укрупняем PR.** Границы PR определяет логическая связность
  задачи, а не желание «PR покороче». Парный chore — допустим только
  как fallback (забыли в задачном PR — поправили после merge).
- **TDD строго во всём efactory** (Red → Green → Refactor) — outside-in
  для hexagonal, domain без mock-ов, адаптеры — integration с
  реальными зависимостями. Зафиксировано в auto-memory
  (`feedback_tdd.md`) и в mem0.
