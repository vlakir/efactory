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

<!-- При закрытии этой версии (переход к новой `## [N.M.0]`)
     добавляется секция:

### Retrospective

- **Что зашло:** ...
- **Что не зашло:** ...
- **Правки методики:** ...

Это короткий разбор результата milestone. Не обязательная длинная
форма — несколько строк по делу. -->


---

<!-- Пример (удалить при заполнении шаблона):

## [0.1.0] — 2026-05-13

### Added
- Базовая структура проекта по шаблону dreamteam.
- Веб-форма публикации с превью.

### Fixed
- Падение при пустом теле поста.

-->
