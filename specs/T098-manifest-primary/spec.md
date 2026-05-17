# Spec: T098 — Manifest (project.yaml) as primary storage; SQL = index

**Статус:** Analyzed
**Дата создания:** 2026-05-17
**Связанные документы:**
- `DECISIONS.md` → ADR 2026-05-17 «Domain expansion direction: D»
  (T098 = фаза C этого направления).
- `CONCEPT.md` §4.1 (портативность как принцип), §4.2 (структура
  папки проекта), §4.3 (схема `project.yaml`), §4.6 (CLI команды
  управления проектом), §4.7 (события авто-обновления манифеста),
  §4.8 (портативность через `archive` / `import`).
- `BACKLOG.md` → запись T098 (исходный набросок, теперь в `BOARD.md`).
- `specs/T096-domain-expansion/spec.md` (discovery направления D).
- `specs/T097-phase-vo/spec.md` (фаза B — задействует те же сущности
  Phase / Project, что мы сериализуем здесь в YAML).

---

## 1. Overview

Сейчас единственным «правдивым» хранилищем проекта служит SQLite
через `MetadataRepository`: записи там создаются на `project create`,
читаются на `show / list`, мутируются на `update / delete`. Каталог
проекта на диске (`<storage_root>/<name>/`) пуст, кроме `.gitkeep` —
он создаётся только ради будущих артефактов.

Это противоречит CONCEPT §4.1: главное обещание efactory — что
проект самодостаточен и портативен. SQL-индекс — частная деталь
конкретной машины: tar.gz папки проекта без `index.db` не позволит
воссоздать состояние на новой машине.

T098 переворачивает зависимость: **манифест `project.yaml`
в корне папки проекта становится источником истины**, а SQLite —
быстрым read-only индексом для `list`. Все mutating операции
(`create / update / delete`) сначала меняют manifest, потом
переиндексируют SQL. Появляется отдельная CLI команда `efactory
project reindex`, чтобы пересобрать SQL индекс с нуля по
manifest'ам (нужна как штатный инструмент после переноса папки на
новую машину и как fallback при desync).

## 2. User Stories (Сценарии использования)

Пользовательский интерфейс — пока CLI `efactory`; LLM-чат и веб
появятся позже по дорожной карте.

- **Перенос проекта на другую машину.** Как разработчик, я хочу
  заархивировать `~/.local/share/efactory/SE-6P14P/`, перенести
  на новый ноутбук, распаковать и сразу видеть проект в
  `efactory project list` (после однократного `reindex`), без
  необходимости вручную восстанавливать SQL-индекс.
- **Внешнее редактирование.** Как разработчик, я хочу при необходимости
  отредактировать `project.yaml` руками (например, переименовать
  проект или вручную пометить фазу как `done`) и быть уверенным,
  что после `reindex` SQL-индекс подхватит правки.
- **Диагностика по файлу.** Как разработчик, я хочу открыть
  `project.yaml` глазами и сразу понять текущее состояние проекта
  (фазы, даты, имя) без обращения к CLI или БД.
- **Восстановление после потери индекса.** Как разработчик, я хочу,
  чтобы случайное удаление `~/.local/share/efactory/index.db`
  не приводило к потере проектов — `reindex` восстанавливает индекс
  из manifest'ов.
- **Существующие проекты не сломались.** Как пользователь, который
  создавал проекты до T098 (SQL-only, без manifest на диске), я хочу,
  чтобы после обновления `efactory` мои старые проекты автоматически
  получили manifest и продолжили работать без ручных действий.

## 3. Functional Requirements

### Domain

- НЕ ДОЛЖНА: появиться новая domain-сущность. T098 — чисто
  infrastructure задача; `Project` / `Phase` / enums из T097
  остаются как есть. (Возможные правки — только если выяснится,
  что какое-то поле manifest'а требует нового domain-атрибута;
  это вопрос Clarify #1 — состав полей.)

### Outbound port

- ДОЛЖНА: появиться новый Protocol `ProjectManifestRepository`
  в `src/ports/outbound/project_manifest_repository.py` со
  следующими методами:

  ```python
  async def save(self, project: Project) -> None: ...
  async def load(self, project_path: Path) -> Project: ...
  async def exists(self, project_path: Path) -> bool: ...
  async def discover_all(self, storage_root: Path) -> list[Path]: ...
  ```

  - `save` пишет `<project.path>/project.yaml` (атомарно — write
    tmp + `os.replace`). `path` **не сериализуется** в YAML
    (Analyze W1) — путь определяется расположением самого файла,
    что даёт портативность.
  - `load(project_path)` парсит YAML по `<project_path>/project.yaml`
    и возвращает `Project` с `path=project_path` (явно
    подставленный). Перед `model_validate` adapter `pop('status')`
    из dict (Analyze C/Resolved #5). Бросает `ManifestNotFoundError`
    если файла нет, `ManifestInvalidError` (wraps
    `pydantic.ValidationError`) при schema-ошибках.
  - `exists` — `True` если `<project_path>/project.yaml` есть.
  - `discover_all` сканирует `<storage_root>/*/project.yaml` и
    возвращает список каталогов с найденными manifest'ами. Нужен
    для `reindex`.

### Adapter

- ДОЛЖНА: появиться реализация
  `FilesystemProjectManifestRepository` в
  `src/adapters/outbound/manifest_yaml/` (новый sub-package).
  - YAML library — **PyYAML** (Resolved #2); `yaml.safe_load`
    (Analyze N1, защита от YAMLObject deserialize).
  - Schema validation через Pydantic (`Project.model_validate`).
  - `Project.model_config` получает `extra='ignore'` (Resolved #5).
  - `model_dump(exclude={'path'})` при save (W1); `status`
    включается в dump (computed_field автоматически).
  - Atomic write: tmp-файл в той же папке + `os.replace` (POSIX
    atomic; durability через `fsync` — не делаем, Analyze C3).
  - Кодировка UTF-8, `allow_unicode=True`, `sort_keys=False`
    (стабильный, человекочитаемый порядок ключей).
  - `discover_all` возвращает `sorted(storage_root.glob('*/
    project.yaml').map(parent))` (Analyze N2 — deterministic
    summary для тестов и UX).

### Application — переработка use case'ов

Write pattern: **manifest first, SQL after**. Если manifest write
прошёл, а SQL upsert упал — manifest = truth, SQL рассинхронизирован;
пользователь увидит ошибку и сможет восстановить индекс `reindex`.
(Альтернатива «one-way compensation» — обсуждается в Clarify #5.)

- ДОЛЖНА: `CreateProject` (existing) — стал:
  `validate_name → file_repo.create_dir → manifest_repo.save →
   metadata_repo.save (upsert)`. Возвращает `Project` как раньше.
- ДОЛЖНА: `UpdateProject` (T097) — стал:
  `load via SQL get_by_name → manifest_repo.load (truth!) →
   mutate (rename / transition_phase) → manifest_repo.save →
   metadata_repo.update`. Шаг «load via manifest, а не SQL» —
   важный поворот: если SQL и manifest рассинхронизированы,
   побеждает manifest.
- ДОЛЖНА: `GetProject` (T089) — стал: `metadata_repo.get_by_name
   (только для path lookup) → manifest_repo.load (truth!) →
   return`. SQL-данные (имя, фазы) **не используются** при
   формировании ответа — только path. Если manifest отсутствует
   при наличии SQL-строки — это desync, бросаем
   `ProjectManifestMissingError` с инструкцией «сделайте reindex
   или восстановите файл».
- ДОЛЖНА: `ListProjects` (T088) — без изменений: читает SQL,
  возвращает все строки. Это и есть единственная нагруженная-чтение
  операция, ради которой SQL остаётся.
- ДОЛЖНА: `DeleteProject` (T090) — стал:
  `metadata_repo.get_by_name → file_repo.remove_dir (manifest
   исчезает естественно) → metadata_repo.delete_by_name`. Порядок
  «FS → SQL» сохранён (как в T090): если SQL delete фейлится
  после FS remove, последующий `reindex` подхватит отсутствие.
- ДОЛЖНА: появиться новый use case `ReindexProjects` в
  `src/application/reindex_projects.py`:
  `manifest_repo.discover_all(storage_root) → for each path: load
   → metadata_repo.save (upsert) → собрать summary`. Поведение по
  ошибкам и orphan SQL-строкам — Clarify #6.

### Adapter (SQL): upsert семантика

- ДОЛЖНА: `MetadataRepository.save` (текущее имя — `save`)
  должен стать **idempotent upsert** (insert or update by `id`),
  потому что `reindex` будет звать `save` на уже существующих
  записях. Сейчас он `INSERT` — упадёт по PK conflict.
  Альтернатива — добавить отдельный `upsert` метод; см. Clarify #4
  про переименование/расширение порта.

### CLI

- ДОЛЖНА: появиться Typer subcommand `efactory project reindex
  [--storage-root PATH] [--remove-orphans]`:
  - без флагов: сканирует `storage_root` (из Settings), upsert'ит
    все найденные manifest'ы в SQL, на stdout — summary `Reindexed
    N projects` (+ детали по `--verbose`).
  - `--remove-orphans` (default `False`): удалить из SQL записи,
    для которых manifest не найден на диске. Без флага — orphan'ы
    остаются и помечаются в summary `K orphans found (use
    --remove-orphans to clean)`.
- ДОЛЖНА: backward-compat для существующих SQL-only проектов
  (без manifest на диске) — см. Clarify #3, варианты A/B/C.

### Backward compatibility (миграция SQL-only → manifest)

Подробный выбор подхода — Clarify #3. На уровне FR фиксирую только:
после применения миграции (каким бы способом мы её ни сделали)
существующие проекты должны:
- иметь `<path>/project.yaml` с корректным содержимым;
- продолжать работать с `show / update / delete / list` без
  ручных действий пользователя.

## 4. Success Criteria

- TDD outside-in для всех новых компонентов: e2e «create →
  edit YAML руками → reindex → show отражает правки» (Red) →
  unit (manifest_repo: round-trip Project ↔ YAML) → integration
  (manifest_repo с tmp_path) → application unit с fake-портами →
  CLI integration → e2e Green.
- `uv run pytest` зелёный, coverage ≥ 80% на `src/`
  (текущая планка — 99%+, рассчитываем удержать).
- `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src` — 0 ошибок.
- Alembic migration (если потребуется — см. Clarify #3 вариант A):
  отрабатывает на чистой БД и на БД с существующими SQL-only
  проектами без потери данных.
- **Portability acceptance test:**
  ```bash
  efactory project create demo --path /tmp/sandbox/demo
  efactory project update demo --phase schematic --status done
  tar czf /tmp/demo.tgz -C /tmp/sandbox demo
  rm -rf /tmp/sandbox/demo  ~/.local/share/efactory/index.db
  tar xzf /tmp/demo.tgz -C /tmp/sandbox
  efactory project reindex --storage-root /tmp/sandbox
  efactory project show demo   # → status: schematic, фаза done
  ```
  Этот сценарий покрывается e2e тестом, использующим `tmp_path`.
- `efactory project show demo` после ручного редактирования
  `project.yaml` (например, поменяли `phase.schematic.status` на
  `done`) отражает правку без вызовов `update` (т.к. manifest =
  truth, SQL подтянется на следующем `reindex` или авто-update —
  см. Clarify #8 про auto-reindex).
- `reindex` идемпотентен: повторный запуск без изменений на диске
  → summary `Reindexed N projects (no changes)`.
- `efactory project show demo` при отсутствующем `project.yaml`
  и наличии SQL-строки → exit code != 0, stderr — понятное
  сообщение с инструкцией: «Manifest not found at <path>. Run
  `efactory project reindex` or restore the file from backup.»
- **Partial failure scenario** (Analyze C2): manifest записан, SQL
  upsert упал (имитируется в тесте моком `metadata_repo.save` →
  `SQLAlchemyError`) → CLI exit_code = 2, stderr содержит
  подсказку `efactory project reindex`; на диске manifest
  присутствует и валиден; последующий `reindex` восстанавливает
  индекс.

## 5. Key Entities

- **`ProjectManifestRepository`** (Protocol) — новый outbound port.
  Методы: `save`, `load`, `exists`, `discover_all`. Не знает про
  SQL, не знает про domain-логику фаз — чистая
  serialization/deserialization.
- **`FilesystemProjectManifestRepository`** — реализация: YAML
  parser + Pydantic validation + атомарная запись.
- **`ManifestNotFoundError`** / **`ManifestInvalidError`** —
  доменные исключения сериализации, бросаются adapter'ом, ловятся
  application и CLI.
- **`ProjectManifestMissingError`** — application-level исключение,
  бросается `GetProject` / `UpdateProject` при наличии SQL-записи
  и отсутствии manifest на диске. (Имя — наследует паттерн
  `ProjectNotFoundError` из T089.)
- **`IndexPersistenceError`** — application-level исключение (Analyze
  C2), бросается use case'ами при partial failure («manifest
  записан, SQL upsert упал»). Wraps `SQLAlchemyError`. CLI
  ловит → exit_code = 2 + stderr подсказка `efactory project
  reindex` для восстановления.
- **`ReindexProjects`** — application use case. На входе —
  `storage_root: Path`; на выходе — `ReindexSummary`
  (см. Clarify #6 про точный shape).
- **`ReindexSummary`** — DTO результата: `{indexed: int, updated:
  int, orphans: list[str], failed: list[tuple[Path, str]]}` (точный
  состав — Clarify #6).
- **YAML schema manifest'а v1** — подмножество CONCEPT §4.3, ровно
  те поля, которые отражаются в текущем `Project` (см. Clarify #1).
  Версионирование схемы — Clarify #7.

## 6. Assumptions & Constraints

- Single-user CLI; конкурентного доступа к одному manifest'у
  нет, file-lock не нужен. (При появлении демона / web-сервиса
  пересмотрим в отдельной задаче.)
- POSIX-only storage_root в текущей фазе (`os.replace` гарантирует
  атомарность в пределах одной FS; Windows — поведение совместимое,
  но кросс-платформенно не тестируем здесь). CONCEPT §10.3
  обещает кросс-платформенность — закрепим тестами позже.
- Pydantic v2 уже стандарт проекта (T085); `Project.model_dump()`
  включает `@computed_field status` — это попадает в YAML.
  На `load` `status` должен быть **исключён из validation input**
  (computed, не stored). См. Clarify #5 — точная стратегия.
- YAML library — добавляется одной новой dependency. Pinned в
  `pyproject.toml`.
- Storage_root уже создаётся `composition.Settings` (T087, XDG-
  defaults + auto-create). Manifest пишется в существующий
  `<storage_root>/<name>/`, который создал `file_repo` (`create_
  project_directory`). Никакой новой логики bootstrap'а каталогов.
- Тестовые проекты в локальном `~/.local/share/efactory/` —
  не production data; после T098 они получат manifest (через
  выбранный в Clarify #3 механизм) либо могут быть пересозданы
  вручную, если что-то сломается. (Это efactory, не клиентский
  проект — мы переживём `rm -rf` storage_root.)

## 7. Out of Scope

- **CONCEPT §4.3 поля, которые НЕ соответствуют текущему domain.**
  `description`, `type`, `assembly`, `target_manufacturer`,
  `imports`, `specifications`, `boards`, `decisions`,
  `sessions` — это поля, появляющиеся вместе со своими
  фичами (T099 для decisions, Phase 1b для sessions, Phase 2
  для specifications, etc.). Manifest v1 содержит только те поля,
  которые сейчас есть в `Project` (id, name, created_at,
  updated_at, phases). См. Clarify #1.
- **CONCEPT §4.4 — журнал решений (`decisions/`).** T099.
- **CONCEPT §4.5 — sessions** (история чатов). Phase 1b.
- **CONCEPT §4.7 — автоматические триггеры обновления manifest'а**
  (git commit при изменении схемы, обновление `updated` поля и
  т.п.). Здесь только ручной CLI write/update. Авто-триггеры
  придут с реальными bridge'ами в Phase 1a+.
- **CONCEPT §4.8 — `archive` / `import` команды.** Отдельная
  задача после T098; manifest как формат — необходимое условие,
  но архивирование требует zip + проверку зависимостей, что
  отдельный объём.
- **Git init проекта при create.** T010 в BACKLOG (Фаза 1a).
- **Schema versioning manifest'а через автоматический migration.**
  В T098 — поле `schema_version: 1`, но без upgrade-логики
  (некуда мигрировать с одной версии). См. Clarify #7.
- **Multi-board проекты** (`boards:` в CONCEPT §4.3) — нет в
  domain'е, нет в manifest v1.
- **CLI флаги `--type`, `--assembly`, `--phases <subset>`
  при `create`** (CONCEPT §4.6). Они расширяют domain — отдельные
  задачи. Сейчас `--phases` нет даже намёка в коде (все 6 фаз
  всегда создаются по T097, см. T097 Clarify #2 (C)).
- **YAML pretty-printing с комментариями для human-editing.**
  Если выберем PyYAML — комментариев не будет, файл редактируется
  как есть. ruamel.yaml поддерживает round-trip с comments, но
  это нагрузка на сериализатор; см. Clarify #2.
- **Концепция `revision: "B"` (semver-like ревизия проекта)**
  из CONCEPT §4.3 — не вводим, требует домен-логики
  bump-revision и т.п.

---

## Clarify (заполняется Claude)

<!-- Открытые вопросы по слепым зонам. Ответы вшиваются обратно
     в § 1-7 или в Resolved. -->

### Open questions

#### 1. Состав полей manifest v1 — minimal или close-to-CONCEPT §4.3?

`Project` сейчас содержит: `id (UUID), name, path, created_at, phases`.
CONCEPT §4.3 содержит ещё `description, type, assembly, status
(derived), updated, author, revision, target_manufacturer, imports,
specifications, boards, decisions, sessions`.

**Варианты:**
- **(A) Minimal v1.** Manifest = ровно те поля, что в domain. Плюс
  `schema_version: 1` и `updated_at`. Никаких полей «на будущее».
  Каждое из CONCEPT §4.3 полей — приедет в свою задачу вместе с
  domain-расширением. **Безопаснее, проще тестировать, нечего
  валидировать.**
- **(B) Все поля CONCEPT §4.3, optional.** Manifest содержит все
  поля сразу, но необязательные. Парсер их хранит как
  pass-through-словари (не валидирует) — это позволяет
  пользователю заранее заполнить, например, `description`, и оно
  выживет следующий update. Сложнее: round-trip Project ↔ YAML
  теряет данные (Project их не содержит), значит manifest_repo
  должен «обогащать» Project pass-through-полями или хранить их
  отдельно.
- **(C) Гибрид: minimal в Project, но `extra: allow` в YAML
  parser.** YAML с дополнительными полями принимается, но эти
  поля игнорируются при load и **теряются при save**. То есть
  ручные правки `description:` будут затёрты следующим CLI update.
  Хуже всех — silent data loss.

**Предлагаемый дефолт:** **(A) Minimal v1**. YAGNI; на каждый из
не-domain полей будет своя задача (T099 для decisions, etc.), и
схема естественно расширится. Pass-through extra полей (B) выглядит
гибким, но архитектурно грязно: manifest перестаёт быть
сериализованным `Project` и становится «Project + extras». Тогда
все use case'ы должны таскать эти extras через себя.

`updated_at: datetime` — **новое поле в `Project`**, появляющееся
в T098 (отложено из T097 Clarify #10). Update use case проставляет
`updated_at = now()` перед save.

---

#### 2. YAML library — PyYAML или ruamel.yaml?

`PyYAML` — стандарт de-facto, минимальная dep, быстрый. Но: не
сохраняет порядок ключей при round-trip (без `sort_keys=False`),
не сохраняет комментарии, не сохраняет стиль (block vs flow).

`ruamel.yaml` — наследник PyYAML с поддержкой round-trip preserving
comments + style. Дороже (больше dep weight), API сложнее, но
human-editable файл реально сохраняется.

**Варианты:**
- **(A) PyYAML + `sort_keys=False`.** Достаточно для T098: пользователь
  может комментариев не писать (или знать, что они потеряются при
  следующем CLI write). Меньше зависимостей.
- **(B) ruamel.yaml.** Сразу под human-editing: комментарии и стиль
  сохраняются.

**Предлагаемый дефолт:** **(A) PyYAML**. Human-edit в T098 не главный
use case (см. user stories: главное — портативность). Если позже
комментарии станут важны (например, для аннотации фаз) — мигрируем.
Стоимость миграции PyYAML→ruamel.yaml невелика, обратное направление
тяжелее.

---

#### 3. Backward compatibility: SQL-only проекты → manifest

После apply T098 у пользователя в SQL уже могут быть проекты,
для которых нет `<path>/project.yaml`. Что делать?

**Варианты:**
- **(A) Alembic data migration.** Миграция читает все строки
  `projects` + `phases`, формирует `Project`, пишет manifest на диск.
  Плюс: автоматически, пользователь ничего не делает. Минус: Alembic
  лезет в filesystem из миграции (нетипично), миграция не reversible
  (rollback должен был бы удалить созданные manifests — сложно).
- **(B) One-shot CLI команда `efactory migrate-to-manifest`.**
  Пользователь сам зовёт после `uv sync`. Плюс: чистая, отделена
  от Alembic; легко тестируется. Минус: пользователь должен
  помнить и звать.
- **(C) Auto-on-first-read.** При `show` / `update` / `delete` —
  если manifest отсутствует, application генерирует его из SQL
  и сохраняет. Плюс: zero user action. Минус: первый `show`
  имеет side effect записи в FS — surprising; и при ручном
  удалении manifest'а пользователем (вдруг намеренно) — он
  «волшебно» восстановится.
- **(D) Combo: (A) для текущей одной миграции + auto-on-first-read
  как defence-in-depth.** Перебор.

**Предлагаемый дефолт:** **(B)** — `efactory project reindex` уже
есть в скоупе, и его естественно расширить. Добавим логику:
если для SQL-строки нет manifest на диске → создать его из SQL-данных
+ предупредить пользователя в summary («3 projects had no manifest;
generated from index»). То есть `reindex` работает в обе стороны:
- manifest → SQL (основной режим);
- SQL без manifest → создать manifest (one-shot bootstrap для
  пред-T098 проектов).

Это можно докуменировать как «one-time after T098 install: run
`efactory project reindex`». Без отдельной команды, минимум кода,
естественно вписывается.

---

#### 4. Имя `MetadataRepository` после T098 — переименование?

После T098 `MetadataRepository` де-факто становится `ProjectIndex`:
manifest — primary, SQL — индекс. Имя `Metadata` вводит в
заблуждение.

**Варианты:**
- **(A) Не переименовываем.** Имя есть имя; сам факт «manifest =
  truth» документирован в архитектурных ADR и READMEs. Меньше diff.
- **(B) Переименовываем в `ProjectIndexRepository`** (Protocol +
  адаптер + все импорты). Чище семантически, но **много правок**
  по кодовой базе (use cases в `application/`, composition,
  тесты).

**Предлагаемый дефолт:** **(A) Не переименовываем**. T098 уже
объёмный (новый порт + adapter + 4 переработки use case'ов +
1 новый use case + 1 новая CLI команда + миграция данных). Имя —
вопрос косметики, отдельная мини-задача (запарковать в BACKLOG —
рефакторинг T1xx «Rename MetadataRepository → ProjectIndex»).

---

#### 5. Что делать с `@computed_field status` при load из YAML

`Project.model_dump()` вернёт `status` (computed) — оно попадёт в
YAML. На `load` Pydantic будет пытаться валидировать `status` как
input — но `computed_field` read-only, на input оно не предусмотрено.

**Варианты:**
- **(A)** В adapter'е перед `Project.model_validate(...)` явно
  удалить `status` из dict. Простая защита; работает гарантированно.
- **(B)** Не дампить `status` в первую очередь —
  `model_dump(exclude={'status'})`. Симметрично, явно: yaml не
  содержит computed-полей. Но тогда в файле теряется удобный
  «человеку прочесть статус, не запуская CLI».
- **(C)** `Project.model_config = ConfigDict(populate_by_name=True,
  extra='ignore')` — Pydantic будет игнорировать unknown поля при
  load. Заодно решает risk будущих CONCEPT §4.3 полей.

**Предлагаемый дефолт:** **(A) + (C)** в комбинации. Дампим `status`
(удобно читать), на load — adapter explicitly pops `status`,
и Pydantic-side `extra='ignore'` страхует от любых других «лишних»
полей (например, если пользователь добавил `description`, оно
не валится).

`extra='ignore'` имеет побочный эффект — silent data loss для
extras при round-trip. Но `description` в manifest v1 не входит
(см. Clarify #1 вариант A), поэтому пользовательских ожиданий о
сохранении extras пока нет. Документируем явно: «v1 manifest schema
ignores fields outside the spec; they will be removed on next
write».

---

#### 6. `ReindexProjects` use case: точный shape результата и поведение ошибок

`reindex` сканирует storage_root, обрабатывает каждый manifest.
Что возвращать пользователю и что делать с ошибками?

**Возможные исходы для каждого найденного manifest'а:**
- Успешно прочитан и upsert'нут в SQL.
- Manifest парсится, но не валидируется (ValidationError). →
  ?
- Manifest повреждён (YAML syntax error). → ?
- I/O error при чтении (permissions). → ?

**Возможные исходы для каждой существующей SQL-строки без manifest'а:**
- Orphan: была в SQL, нет на диске. → ?

**Варианты обработки ошибок:**
- **(A) Fail-fast:** первая ошибка → abort всю операцию. Просто,
  но frustrating: один битый manifest блокирует индексацию остальных.
- **(B) Best-effort + summary:** обрабатываем всё, что можем,
  ошибки собираем в `failed`, в конце печатаем summary.
  `exit_code = 0 если failed == 0 else 1`.

**`--remove-orphans` policy:**
- Без флага — orphan'ы остаются в SQL, в summary помечены.
- С флагом — `DELETE FROM projects WHERE id IN orphans`.

**Предлагаемый дефолт:** **(B) best-effort** с `ReindexSummary`:

```python
@dataclass(frozen=True)
class ReindexSummary:
    indexed: int          # успешно upsert'нуто
    bootstrapped: int     # manifest сгенерирован из SQL (для
                          # pre-T098 проектов; см. Clarify #3 (B))
    orphans: list[str]    # SQL-имена без manifest (или удалены, если
                          # --remove-orphans)
    failed: list[tuple[Path, str]]  # (path, error_message)
```

CLI печатает читаемо:
```
Reindexed 5 projects.
Bootstrapped 2 manifests for pre-T098 projects.
Orphans (1): old-project — no manifest at <path>. (Use
  --remove-orphans to clean.)
Failed (0): —
```

---

#### 7. Schema versioning: `schema_version: 1` в YAML?

Если в будущем формат manifest'а изменится (T099 добавит
`decisions: [...]`, например), как читать старые manifest'ы?

**Варианты:**
- **(A) Пишем `schema_version: 1` сейчас.** Считываем — игнорируем
  (нечем мигрировать с одной версии). При появлении v2 — добавится
  migration логика; v1-only пользователи получат скрипт.
- **(B) Не пишем версию.** Полагаемся на `extra='ignore'` (Clarify
  #5 (C)) — добавление полей в v2 будет backward-compatible само
  по себе для v1-readers. Уход от формата (rename / breaking
  change) — никогда; либо отдельная команда `migrate-schema`.

**Предлагаемый дефолт:** **(A)** — даже если сейчас бесполезно,
заведомо лучше иметь поле, чем не иметь. Стоит 1 строки в YAML
и 0 кода (просто принимаем). При появлении v2 — естественная
точка ветвления.

---

#### 8. Auto-reindex при show после ручного редактирования YAML?

User story #2: «отредактировал YAML руками, ожидаю что увижу
изменения». Сейчас по предложенной архитектуре `show` читает
manifest напрямую → правки видны. SQL индекс — не видит, пока
не запустишь `reindex`. Это значит:

- `efactory project show demo` — корректно (отражает manifest).
- `efactory project list` — некорректно (показывает SQL = stale).

**Варианты:**
- **(A) Так и оставить.** Пользователь, отредактировавший YAML,
  знает что делает — пусть зовёт `reindex`. Документируем явно.
- **(B) Auto-reindex одной строки на каждом `show`.** При `show
  demo` — если mtime manifest > mtime SQL row → reindex эту одну
  строку. Скрытая магия, но удобная.
- **(C) Auto-reindex всего на каждом `list`.** Гарантирует
  актуальность list. Но `list` становится медленным при большом
  числе проектов (full scan).

**Предлагаемый дефолт:** **(A)** — явное лучше неявного. Пользователь,
редактирующий YAML руками, и так выходит за обычный workflow;
ему естественно подсказать `reindex` в документации (`efactory
project --help` и README). Auto-reindex (B/C) — отдельная задача,
если станет реальной проблемой.

---

#### 9. Storage_root в `discover_all`: глубина поиска и фильтры

`discover_all(storage_root)` — простое `storage_root.glob('*/project.
yaml')` (только одноуровневый scan) или рекурсивный `rglob`?

**Предлагаемый дефолт:** **glob('*/project.yaml')** — одноуровневый.
Каждый проект — папка непосредственно в `storage_root`. Вложенность
не предусмотрена. Рекурсивный поиск нашёл бы лишнее (например,
`storage_root/demo/sub-project/project.yaml` — что это?). Если позже
введём «sub-projects» — отдельная задача.

---

#### 10. `created_at` на bootstrap из SQL: что писать?

При генерации manifest из SQL для pre-T098 проекта (Clarify #3 (B)
поведение reindex) `created_at` берётся из SQL — там уже сохранено
с T085. Это нормально.

А `updated_at` (новое поле, см. Clarify #1) — что писать?
- (A) `updated_at = now()` — момент bootstrap'а. Семантически:
  «manifest создан сейчас». Логично, но искажает реальную
  историю.
- (B) `updated_at = created_at` — fallback. Чище: «обновлений после
  создания не было записано».

**Предлагаемый дефолт:** **(B)** — `updated_at = created_at`. Принцип
наименьшего сюрприза.

---

### Resolved (с ответами)

Разработчик подтвердил все 10 предложенных дефолтов + 3 доп. вопроса
(2026-05-17). Кратко:

1. **Состав полей manifest v1** — **(A) Minimal**: ровно поля
   `Project` (`id, name, created_at, updated_at, phases`) +
   `schema_version: 1` + derived `status` (для удобства чтения).
   Никаких CONCEPT §4.3 extras — каждое поле приедет со своей
   фичей (T099 для decisions, Phase 1b для sessions, etc.).
2. **YAML library — PyYAML** (`sort_keys=False`,
   `allow_unicode=True`). ruamel.yaml — позже, если потребуется
   round-trip с комментариями.
3. **Bootstrap pre-T098 проектов** — **расширяем `reindex`**:
   при отсутствии manifest для SQL-строки → сгенерировать manifest
   из SQL-данных. `reindex` работает в обе стороны (manifest→SQL
   primary mode + SQL→manifest bootstrap mode). Отдельной CLI
   команды `migrate-to-manifest` не вводим. Alembic data-migration
   — отвергнут (FS из миграции — антипаттерн).
4. **Имя `MetadataRepository`** — **не переименовываем сейчас**.
   Косметическая правка → паркуется в `BACKLOG.md` отдельной
   задачей T100+ «Rename MetadataRepository → ProjectIndex».
5. **`@computed_field status` round-trip** — комбо: дампим в YAML
   (читать удобно), на load adapter explicitly `pop('status')`
   из dict перед `Project.model_validate(...)`, + добавляем
   `ConfigDict(extra='ignore')` как страховку от любых extras.
6. **`ReindexProjects` поведение** — **best-effort + summary**.
   Возвращает `ReindexSummary {indexed, bootstrapped, orphans,
   failed}`. Одна битая запись не блокирует остальные. CLI
   `exit_code = 1 if failed != 0 else 0`.
   `--remove-orphans` (default `False`) — удалить из SQL записи
   без manifest на диске.
7. **`schema_version: 1` в YAML** — **пишем**. Стоит 0 кода,
   при v2 — естественная точка ветвления.
8. **Auto-reindex на `show` после ручной правки YAML** — **нет**.
   `show` читает manifest напрямую (правки видны); `list` после
   ручной правки показывает stale до `reindex`. Документируется
   явно (README + `efactory project --help` text).
9. **`discover_all` глубина** — одноуровневый
   `storage_root.glob('*/project.yaml')`.
10. **`updated_at` на bootstrap из SQL** — `updated_at = created_at`
    (принцип наименьшего сюрприза).

Дополнительно подтверждено:
- **(a)** `updated_at: datetime` добавляется в `Project` в этом PR
  (отложенный из T097 Clarify #10). Все mutating use case'ы
  (Create/Update/Delete; Reindex в bootstrap-mode) проставляют
  `updated_at` явно перед save.
- **(b)** Portability acceptance test (`tar czf → rm index.db →
  tar xzf → reindex → show`) реализуется как e2e на `tmp_path`,
  не на реальном `~/.local/share/efactory/`.
- **(c)** Implementation разбит на 3 фазы:
  - **Фаза 1** — Domain.updated_at + Manifest port + YAML adapter.
  - **Фаза 2** — Use cases переработка + ReindexProjects.
  - **Фаза 3** — CLI `reindex` + portability e2e + close BOARD.

---

## Analyze (заполняется Claude)

### 🔴 Critical (фиксим до начала implement)

#### C1. `MetadataRepository.save` → upsert: backward compatible или новый метод?

Текущий `save(project)` в SQL adapter делает `INSERT` (T085 контекст:
walking skeleton, проектов нет — `save` всегда новый). После T098
он будет дёргаться:

- из `CreateProject` — новый проект, INSERT;
- из `UpdateProject` — существующий, UPDATE (`update` уже есть из
  T097);
- из `ReindexProjects` — может быть и тем и другим (bootstrap или
  refresh).

**Опции:**
- **(A)** Превратить `save` в idempotent upsert (insert-or-update by
  `id`). Однозначно: один метод, одна точка истины. Все callers
  не задумываются. Семантика «save = persist current state».
- **(B)** Добавить отдельный `upsert(project)`; `save` оставить
  insert-only. Тогда `ReindexProjects` зовёт `upsert`, остальные —
  по факту. Чище SRP, но дороже в use case'ах (двойная диспетчеризация).

Резолюция: **(A)** — `save` становится upsert. Это согласуется с
семантикой Repository pattern (DDD «persist aggregate»). Все
тесты, проверяющие двойной `save` → ValueError, переписываются
(их и нет в текущем коде — `CreateProject` единственный caller,
двойной create предотвращается на уровне application-логики через
`get_by_name` precheck).

**Side effect:** `UpdateProject` (T097) сейчас зовёт `update`, не
`save`. После C1 можно бы заменить на `save` — но не делаем
ради scope discipline (это рефакторинг, не T098). Останется
`update` как явный «обновить существующее» и `save` как «persist
любое состояние».

#### C2. Порядок операций в write-path: что считаем «success» при partial failure?

Write pattern «manifest first, SQL after». При partial failure
(manifest записан, SQL upsert упал):
- из user perspective: **сценарий успеха** — manifest на диске
  = truth, SQL stale.
- но CLI вернёт exit_code != 0 (т.к. SQL upsert упал) — иначе
  пользователь не узнает, что indexed запорот.

Корректный порядок (для `CreateProject`):
1. `file_repo.create_project_directory(path)` — создать пустой
   каталог.
2. `manifest_repo.save(project)` — записать `<path>/project.yaml`.
3. `metadata_repo.save(project)` — upsert в SQL.

Если шаг 3 падает:
- состояние диска: manifest есть, корректный.
- состояние SQL: проекта нет (если CreateProject) или stale
  (если UpdateProject — но там сначала get_by_name → значит SQL
  не пустой; UPDATE упал → SQL stale).
- следующая команда `efactory project list` — проекта не покажет
  (или покажет stale).
- лечится `efactory project reindex` (подтянет manifest → SQL).

Сообщение в stderr должно явно подсказать `reindex`. Реализуется
как catch `SQLAlchemyError` в use case → wrap в
`IndexPersistenceError(project_name, original_exc)` → CLI печатает
«Manifest saved to <path>. Failed to update index: <reason>. Run
`efactory project reindex` to recover.» exit_code = 2 (отличить
от validation errors).

#### C3. Atomic write в YAML adapter: `os.replace` + `fsync` или just `os.replace`?

POSIX `os.replace` атомарен на уровне inode swap, но не гарантирует
durability — данные tmp-файла могут не быть на диске до момента
swap.

**Опции:**
- **(A) Просто `os.replace`.** Достаточно для нашего use case:
  тот же процесс сразу читает то, что записал; crash recovery
  для CLI-команды не критичен (пользователь повторит команду).
- **(B) `fsync` tmp-файла перед replace + `fsync` директории.**
  Полная durability guarantee. На CLI-уровне это
  preprocessor для возможных будущих daemon'ов / web-сервисов.

Резолюция: **(A) просто `os.replace`** — никаких durability
требований не озвучено, premature optimization. При появлении
сценариев типа kernel panic / power loss во время save —
вернёмся к (B) (1 строка кода).

### 🟡 Warning (обсуждаем при implement, не блокируем)

#### W1. `Project.path` — абсолютный или относительный в YAML?

`Project.path` — `Path` (abs path сейчас всегда). Если писать
абсолютный путь в `project.yaml` — manifest становится не
портативным: при переносе папки `path` в YAML указывает на старое
место.

**Опции:**
- **(A) Не писать `path` в YAML.** Path определяется
  расположением файла: `path = manifest_file.parent`. Тогда
  manifest_repo.load восстанавливает path из аргумента
  `project_path`. Это естественно: «где manifest лежит — там и
  проект».
- **(B) Писать `path`, но игнорировать при load.** Семантически
  путано: поле есть, но не работает.
- **(C) Писать relative path / просто `name`.** Дублирует name.

Резолюция: **(A) не писать path в YAML.** В `model_dump` →
`exclude={'path', 'status'}` (path исключён ради портативности,
status — read-only computed). На load: adapter передаёт
`path=project_path` явно.

Это технически breaking для Project schema, но `path` всегда был
infrastructural (где на диске лежит), не доменной семантикой.
Документируется в spec и в коде.

#### W2. Backfill phases для pre-T097 проектов в bootstrap mode

Bootstrap-mode reindex'а читает SQL → формирует Project → пишет
YAML. Но что если SQL `phases` table пустая для каких-то старых
строк (созданных до T097)?

После T097 миграция Alembic backfill'ит 6 pending rows для
существующих проектов (см. T097 § 3 / acceptance criteria). К моменту
T098 миграция уже отработала на dev-данных. То есть теоретически
вопрос неактуален.

**Но**: тесты T098 не должны полагаться на «миграция T097 уже
прошла» — корректнее, чтобы adapter SQL.list_all всегда возвращал
Project с заполненными phases (это и так так — repository
из T097 загружает phases).

→ Note, не Warning. Перевожу в N5 ниже.

#### W3. `ProjectName` валидация при load из YAML

`ProjectName` (T092) запрещает `/`, `\`, `..`, пустые имена.
Если пользователь ручкой отредактировал YAML и поставил
`name: ../etc/passwd` — `Project.model_validate` обязан упасть.

Это уже гарантировано `AfterValidator` (см.
`src/domain/project.py`). На load в manifest_repo — обычный
`model_validate`, валидатор сработает. Никаких extra проверок не
нужно. Документируем acceptance test'ом: «load malicious YAML →
ValidationError».

### 🟢 Note (к сведению)

#### N1. PyYAML safe_load обязателен

`yaml.safe_load` (не `yaml.load`), чтобы избежать
`yaml.YAMLObject` deserialize и связанных уязвимостей. Стандарт.
Прописываем в README и в коде adapter'а.

#### N2. `discover_all` сортировка результата

`glob` не гарантирует порядок. `ReindexProjects` идемпотентен,
но deterministic summary удобен для тестов и для пользователя:
`sorted(paths)` перед обходом.

#### N3. `ManifestInvalidError` ↔ `pydantic.ValidationError`

`pydantic.ValidationError` имеет богатое сообщение (поля, причины).
Не теряем его — `ManifestInvalidError` wraps original exception
с сообщением вида «Invalid manifest at <path>: <pydantic message>».
В тестах проверяем, что упомянуты name поля и причина.

#### N4. Поле `updated_at` — default factory

В `Project` `updated_at: datetime = Field(default_factory=lambda:
datetime.now(UTC))`. На fresh create — `updated_at == created_at`
(с точностью до микросекунды — два разных вызова `now`). Тест
толерантен (`abs(updated - created) < 1s`) либо `updated_at =
None | datetime` с явной семантикой «никогда не апдейтилось».

Резолюция: пишем `default_factory` (как у `created_at`), не вводим
None — `updated_at` всегда есть. На fresh create два разных
вызова `now()` дадут разницу в микросекунды; для теста не
проблема. Use case `UpdateProject` явно проставляет
`updated_at = now()` перед save (overrides default).

#### N5. Phases в bootstrap mode

См. перенесённый W2: после T097 миграции SQL.list_all возвращает
Project с заполненными phases. Bootstrap-mode reindex'а
полагается на этот контракт. Acceptance test для bootstrap mode
проверяет, что фазы прорастают в YAML корректно.

#### N6. Composition DI: новый порт + adapter

В `composition/main.py` появляется wiring:
```python
manifest_repo = FilesystemProjectManifestRepository()
create_project = CreateProject(file_repo, manifest_repo, metadata_repo)
update_project = UpdateProject(file_repo, manifest_repo, metadata_repo)
# ... аналогично для Get / Delete / Reindex
```

Settings (T087) не трогаем — `storage_root` уже есть, manifest_repo
не требует никакой конфигурации.

#### N7. Pre-push hook (T095) и pyyaml dependency

Добавление `pyyaml` через `uv add pyyaml` обновит `uv.lock`,
`pyproject.toml`. Hook повторно сработает (auto-install через
build hook — но добавление не-build-affecting deps не триггерит
re-install хука). Просто перепроверим вручную после `uv sync`.
