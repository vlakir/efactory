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

<!-- Здесь накапливаются изменения, которые войдут в следующую
     версию `[N.M.0]`. При закрытии milestone — переименовывается
     в очередную версию, ниже создаётся новая пустая `[Unreleased]`. -->

### Added
- Auto-install pre-commit pre-push hook через hatchling custom build
  hook. После `git clone && uv sync` хук установлен автоматически,
  отдельная команда `uv run pre-commit install --hook-type pre-push`
  больше не нужна (остаётся как fallback).
  - `hatch_build.py` в корне реализует `BuildHookInterface.initialize`,
    делегирует на `uv run --no-sync pre-commit install --hook-type
    pre-push`. Использует `shutil.which('uv')` для resolved path
    (избегаем `S607`), очищает `VIRTUAL_ENV` из build venv
    (иначе uv warning'ует и игнорирует проектный `.venv/`).
  - Регистрация через `[tool.hatch.build.hooks.custom]` в
    `pyproject.toml`.
  - Guard'ы: skip при отсутствии `.git/` (tarball/non-VCS checkout)
    и при отсутствии `uv` на PATH — exit 0, warning в stderr.
  - Идемпотентность бесплатно: без `--reinstall` uv кеширует
    editable wheel, hook не дёргается на повторных `uv sync`.
  - ADR — `DECISIONS.md` (`2026-05-17 — Auto-install pre-push hook
    через hatchling custom build hook`), spec —
    `specs/T095-auto-install-hook/spec.md`.
  - README → «Проверки перед push» обновлён: ручная команда
    помечена fallback. (T095)

### Changed
- `[tool.ruff.lint.ignore]` дополнен `S603` (subprocess call without
  shell=True и без user-input — известный false-positive). Введено
  по ходу T095 (`hatch_build.py` — первый subprocess в проекте);
  обоснование в самой ignore-секции `pyproject.toml`. (T095)
- Closing-правка `BOARD.md`: запись `Doing → Done` оформляется
- Closing-правка `BOARD.md`: запись `Doing → Done` оформляется
  отдельным commit'ом **после** `gh pr create`, чтобы пометка
  содержала реальный `[closed YYYY-MM-DD, PR #N]` вместо
  placeholder `PR current` (повторившегося ×6 в `[0.2.0]`:
  T086–T091). Зафиксировано подразделом «Closing-правка `BOARD:
  Doing → Done`» в `CLAUDE.md § Git workflow`. Глобальное правило
  «closing-правка в задачном PR, без парного chore-PR» сохраняется
  — здесь только проектное уточнение порядка шагов на ветке.
  (T093)

---

## [0.2.0] — 2026-05-17

Второй milestone: hexagonal-фундамент 0.1.0 обкатан полным CRUD-набором
для домена `Project` (Create/List/Show/Delete), автоматизирован 5-
проверочный гейт через pre-commit hook, закрыта первая security-
уязвимость (path-traversal в `Project.name`). Архитектура подтвердила
рабочий характер на 4 use case'ах без правок фундамента.

### Security
- Валидация `Project.name` против path-traversal в `domain/project.py`.
  До T092 имя вида `../../etc` проходило domain-валидацию (которая
  проверяла только non-empty/non-whitespace) и попадало в
  `projects_root / name`. Для `delete_project` T090 это означало
  `shutil.rmtree` за пределами `projects_root` — потенциальное
  разрушение хост-FS. Сейчас вход — только локальный CLI (низкая
  реальная эксплуатируемость), но защита проактивная: при появлении
  MCP / HTTP-API имя может прийти из недоверенного источника.
  - `_validate_name` дополнен правилами: запрет имён `.` и `..`,
    запрет символов `/` и `\`.
  - CLI `efactory project create` ловит `pydantic.ValidationError`
    и выводит «Invalid project name: ...» в stderr с
    `exit_code=2` (вместо безобразного Rich-traceback с pydantic
    internals).
  - 14 параметризованных unit-тестов на отказ опасных имён (`..`,
    `.`, `../etc`, `..\\etc`, `/absolute`, `a/b`, `a\\b`,
    `trailing/`, `\\leading`, `./rel` и т.д.) + 7 на человеческие
    имена (включая юникод `тёплый-усилитель`) + 1 e2e на UX при
    bad name. 59 passed, coverage 99.20%. (T092)

### Added
- Pre-commit hook на 5-проверочный гейт через
  [pre-commit](https://pre-commit.com) framework на stage `pre-push`.
  - `.pre-commit-config.yaml` с пятью local hooks (`ruff check` /
    `ruff format --check` / `mypy src` / `lint-imports` / `pytest`).
    Local-стиль (без mirror-репозиториев) — версии инструментов
    те же, что фиксированы в `uv.lock`, без отдельного pinning.
  - `pre-commit` добавлен в dev-deps (`pyproject.toml` / `uv.lock`).
  - Однократная установка после клонирования —
    `uv run pre-commit install --hook-type pre-push`. Документировано
    в README → «Проверки перед push».
  - Существующий `.git/hooks/pre-push` (защита `main` от прямого push)
    сохраняется как `.git/hooks/pre-push.legacy` и запускается первым
    в migration mode pre-commit.
  - `git push` теперь автоматически прогоняет гейт; способы скипа
    (`SKIP=pytest git push`, `git push --no-verify`) документированы. (T091)
- Четвёртый use case `DeleteProject` — завершает базовый набор
  CRUD (Create, Read-Many, Read-One, Delete) для домена `Project`.
  - `ports/outbound/metadata_repository.py`: + `delete_by_name(name) -> None`.
  - `ports/outbound/project_file_repository.py`: +
    `remove_project_directory(path) -> None`.
  - `application/delete_project.py`: новый use case (порядок:
    `get_by_name` → `delete_by_name` → `remove_project_directory`)
    и re-export `ProjectNotFoundError` из `application.get_project`
    (общее исключение для read-and-act use cases).
  - `adapters/outbound/persistence_sql/repository.py`: реализация
    `delete_by_name` через `delete(...).where(name == ...)`. Noop
    при отсутствии строки (идемпотентно).
  - `adapters/outbound/file_store/project_file_repository.py`:
    реализация `remove_project_directory` через `shutil.rmtree`
    в `asyncio.to_thread`. Idempotent: если каталога нет — тихо
    возвращается (orphan-row страшнее orphan-папки, поэтому FS-
    операция последняя и не блокирует общий success).
  - `adapters/inbound/cli/app.py`: команда
    `efactory project delete --name <name>` — выводит
    «Deleted project <name>» при успехе; при отсутствии печатает
    `Project '<name>' not found` в stderr + `exit_code=1`.
  - Тесты (TDD outside-in): 2 e2e (happy path + unknown name; happy
    проверяет, что `show` после delete → exit 1, `list` пуст),
    2 unit с fake-портами (happy + raises; косвенно подтверждает
    порядок `get → delete`), 2 integration SQL (`delete_by_name`
    удаляет / noop на отсутствующее имя), 2 integration FS
    (`remove_project_directory` удаляет дерево / idempotent на
    отсутствующий путь). 37 passed, coverage 99.14% (+8 новых
    тестов). (T090)
- В `BACKLOG.md` новая задача **T091** (раздел «Архитектурные
  follow-up'ы Walking Skeleton») — pre-commit hook на 5-проверочный
  гейт (`pre-commit` framework + `.pre-commit-config.yaml`). Сейчас
  гейт прогоняется вручную; автоматизировать через `pre-commit`. (T090)
- В `BACKLOG.md` новая задача **T092** (там же) — валидация
  `Project.name` против path-traversal. Выявлено при self-review T090:
  имя «../../etc» проходит текущую domain-валидацию и попадает
  в `projects_root / name` (критично для `delete_project` →
  `shutil.rmtree`). Текущий вход — только локальный CLI, поэтому не
  CVE-уровень; станет критично при появлении MCP / HTTP. (T090)
- Третий use case `GetProject` (по имени) — продолжение обкатки
  hexagonal-фундамента после T088.
  - `ports/outbound/metadata_repository.py`: `MetadataRepository`
    Protocol расширен методом `get_by_name(name) -> Project | None`.
  - `application/get_project.py`: use case + `ProjectNotFoundError`
    (явное application-исключение, чтобы CLI / API могли отличить
    «нет такого» от «БД упала»).
  - `adapters/outbound/persistence_sql/repository.py`: реализация
    `get_by_name` через `select(...).where(name == ...).limit(1)`.
  - `adapters/inbound/cli/app.py`: команда
    `efactory project show --name <name>` — построчный вывод
    метаданных проекта; при отсутствии печатает
    `Project '<name>' not found` в stderr и выходит с `exit_code=1`.
  - Тесты (TDD outside-in): 2 e2e (happy + unknown name),
    2 unit с fake-портом (found / raises), 2 integration
    (get returns row / get returns None). Coverage 99.02%
    (29 passed; +6 новых). (T089)
- Второй use case `ListProjects` — проверка hexagonal-фундамента на
  втором сквозном срезе (CLI → application → SQL-adapter → domain).
  - `ports/outbound/metadata_repository.py`: `MetadataRepository`
    Protocol расширен методом `list_all(self) -> list[Project]`.
  - `application/list_projects.py`: тонкий use case, делегирует
    выборку и сортировку adapter'у.
  - `adapters/outbound/persistence_sql/repository.py`: реализация
    `list_all` через `select(...).order_by(created_at DESC)`,
    `model_to_project` mapping.
  - `adapters/inbound/cli/app.py`: команда
    `efactory project list` — TSV-вывод
    `name<TAB>created_at_iso<TAB>path`, пустой список выводит
    «No projects found.».
  - Тесты (TDD outside-in): 2 e2e (newest-first + empty), 3 unit
    с fake-портом (empty / returns / delegates ordering), 2 integration
    (sort DESC + empty). Coverage 98.84% (23 passed; +7 новых тестов). (T088)
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

### Retrospective

**Что зашло:**

- **TDD outside-in лёг как шаблон.** Четыре use case'а CRUD
  (T085 Create, T088 List, T089 Show, T090 Delete) сделаны по
  одному образцу: e2e Red → unit Red с fake-портами → integration
  Red → Green. Время на use case стабильное (~40 мин), без
  «как же мне это протестировать»-пауз.
- **Архитектурный вопрос «правильный ли фундамент 0.1.0?»
  получил утвердительный ответ через 4 практики.** Ни один из
  4 use case'ов не потребовал правок Settings, composition root,
  layers contracts, миграционной системы. Hexagonal со старта
  работает.
- **Pre-commit hook (T091) окупился сразу.** Следующий же PR
  (T092) прошёл гейт без ручной `&&`-цепочки. Освобождение
  внимания заметно — perception «забыть гейт» сместилась с
  «вероятно» на «невозможно». Local-стиль hooks (вместо mirror-
  репозиториев) обеспечил единые версии инструментов с `uv.lock`.
- **Парковка побочных находок работает.** В ходе T086 всплыл
  Settings без default'ов → T087. В ходе T090 при self-review
  всплыл path-traversal → T092. Оба запаркованы в момент
  обнаружения, разобраны следующими PR — scope текущей задачи
  оставался чистым.
- **CodeRabbit реально проревьюил один раз (PR #10) — feedback
  оказался полезный.** Три замечания (PR ref + грамматика
  «об»/«о», строгий `exit_code == 1`, явные ассерты на поля)
  — все валидные, учли в fix-up commit. Не игнорировали.
- **Защита в domain, не в адаптерах** (T092 path-traversal) —
  правильное архитектурное решение: все use cases и адаптеры
  защищены автоматически, при появлении MCP/HTTP не нужно
  дублировать валидацию.

**Что не зашло:**

- **CodeRabbit упирался в rate-limit на 6+ PR из 9.** Free-tier
  не выдерживает интенсивной работы (rate-limit 42 минуты после
  пары PR). Status-check показывал SUCCESS, что вводило в
  заблуждение — реального ревью не было. Раз бот работает, его
  фидбек ценный, но полагаться на него нельзя.
- **Помарка `PR current` → `PR #N` повторилась 6 раз.** В записи
  T086, T087, T088, T089, T090, T091 — каждый раз правили в
  следующем PR. Корень: BOARD-запись закрытия делается **до**
  `gh pr create`, поэтому номер PR ещё не известен. Возможные
  решения для следующего milestone: (а) сделать closing-правку
  BOARD отдельным финальным commit'ом после `gh pr create`,
  (б) принять placeholder как ОК и систематически править в
  следующем PR (как делали).
- **Один раз я написал хрупкий unit-тест с monkey-patch + `# noqa:
  SLF001`** (T090, третий тест на порядок DB→FS) — нарушение
  методики «без noqa без обсуждения». Поймал по `pre-commit`,
  удалил тест как избыточный (паттерн уже виден из кода и
  косвенно подтверждается raises-тестом). Методически правильнее
  было сразу понять избыточность, не писать.
- **Qodo на паузе у этого аккаунта** — не использовался во
  всём 0.2.0 цикле (как и в 0.1.0). Если paid seat не появится —
  можно отключить, чтобы не шумел «paused»-комментариями на
  каждом PR.

**Правки методики (внесены по ходу):**

- **`pre-commit install --hook-type pre-push`** — добавлен в
  README → «Проверки перед push». Должен быть обязательным шагом
  после `uv sync` для всех новых разработчиков; обновится в
  template `dreamteam` отдельно.
- **Грамматика «об изменениях» (а не «о изменениях») перед
  гласной** — поправлено во всех BOARD-записях Done через
  `replace_all` в T086 fix-up. Унаследовано из template; в
  template `dreamteam` следующая правка попадёт отдельным PR
  (не сейчас, не в этой сессии).
- **Auto-memory `feedback_tdd.md`** (из ранней сессии) применился
  последовательно 5 раз без отступлений. Подтверждено.

**Технический долг и идеи для 0.3.0:**

- Помарка `PR current` — выбрать один из подходов выше и
  применять единообразно.
- Если CodeRabbit продолжит rate-limit — оценить paid plan
  или альтернативу (например, `/ultrareview` для критичных PR
  — Разработчик-триггерируемая).
- Возможно `uv sync` mог бы сам устанавливать pre-commit hook
  через post-install script (опционально).
- Domain расширение: следующий agregat (Component? Schematic?)
  или второй use case с записями (Update — когда появится
  реальное поле для обновления).

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
