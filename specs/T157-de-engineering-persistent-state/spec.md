# Spec: De-engineering persistent state — filesystem as single source of truth

**Статус:** Analyzed
**Дата создания:** 2026-05-27
**Clarify прошёл:** 2026-05-27 (10 вопросов, все «по рекомендации»)
**Analyze прошёл:** 2026-05-27 (12 issues: 2 Critical разрешены
in-spec, 5 Warning с predeclared resolutions, 5 Note)
**Связанные документы:**
- `BACKLOG.md → ### Фаза 2 → T157` — короткая запись.
- `DECISIONS.md` — ADR 2026-05-19 «Tool surface = Bash + efactory CLI
  + filesystem, не MCP» (этот спек оперирует следствием).
- `src/adapters/outbound/persistence_sql/` — legacy DB-слой (SQLAlchemy
  + aiosqlite + Alembic).
- `src/adapters/outbound/graph_store/` (упомянут в README, отсутствует
  физически) + `tests/integration/adapters/graph_store/test_kuzu_smoke.py`
  — Kùzu stub.
- `src/ports/outbound/metadata_repository.py` — outbound port для
  projects/phases.
- `data/templates/se-amp/template.yaml` + `project.yaml` (T014) —
  existing manifest format (расширим для phases).
- T097 / T098 / T099 — phase'ы которые ввели и затем модифицировали
  projects+phases tables в БД.

---

## 1. Overview

Архитектурный refactor: убрать legacy persistent-state-слой (SQLite
+ SQLAlchemy ORM + aiosqlite + Alembic migrations + Kùzu graph-stub),
filesystem становится единственным источником истины для project
metadata. `MetadataRepository` outbound port заменяется на
`FileSystemProjectRepository`. Phases переезжают в `project.yaml`
manifest. Все 4 dependencies (`sqlalchemy`, `aiosqlite`, `alembic`,
`kuzu`) удаляются — снижение venv ~30-40 MB + Docker image baseline.

ADR в `DECISIONS.md` фиксирует strategy: **filesystem source of
truth; БД вводится только под конкретный future use case при scale**
(triggers: T030 model_import_url @ >1000 моделей, sim-results archive
cross-project trend analysis, KB > 100 entries с semantic search,
real BOM/inventory).

## 2. Сценарии использования

> Проект без явных «ролей» — efactory работает с агентом и
> Разработчиком через CLI / chat-обёртку.

- **Сценарий A (CLI — create project).** Пользователь зовёт
  `efactory project create --name foo --template se-amp`. Текущий
  behaviour: создаётся директория + запись в SQLite + INSERT INTO
  projects. **Post-T157**: создаётся директория + `project.yaml` с
  manifest (`{name, created_at, updated_at, phases: [], ...}`). Без
  БД. UUID можно generate randomly и хранить в manifest, либо derive
  from directory hash.

- **Сценарий B (CLI — list projects).** `efactory project list`.
  **Post-T157**: `os.scandir(EFACTORY_PROJECTS_ROOT)` + parse
  `project.yaml` per directory. Latency для десятков проектов —
  единицы ms. Сортировка по `created_at` из manifest.

- **Сценарий C (CLI — get project by name).** **Post-T157**: linear
  scan + match (или direct lookup `<root>/<name>/project.yaml` если
  filesystem case-sensitive). Sub-ms.

- **Сценарий D (CLI — update project / phase status).**
  `efactory project update <name> --phase X --status done`.
  **Post-T157**: read `project.yaml` → patch phases entry → write back
  atomically (`*.tmp` + `Path.replace`).

- **Сценарий E (CLI — delete project).** **Post-T157**: `shutil.rmtree`
  директории. Никакой DB-стороны.

- **Сценарий F (CLI — validate_manifests, бывший `reindex_projects`).**
  Use case `reindex_projects` exists потому что DB могла разойтись
  с filesystem. **Post-T157** (Q-A → b): use case переименовывается
  в `validate_manifests` — проверяет presence + parseability +
  corruption всех `project.yaml` в `EFACTORY_PROJECTS_ROOT`,
  отчёт об orphaned/corrupt directories. Old semantic (DB↔FS sync)
  отброшен. CLI rename: `efactory project reindex` → `efactory
  project validate`.

- **Сценарий G (migration — existing projects).** У Vladimir-а в
  `$HOME/efactory-projects/` уже есть `se-amp-demo`, `se_amp`,
  `sheetmetal-bracket-demo`. Каждый имеет `db.sqlite` с phases-data.
  **Migration script** читает db.sqlite per project → пишет phases
  в `project.yaml`. Once-off operation, runs as part of `efactory
  migrate-to-filesystem` или auto-on-first-cli-call.

- **Сценарий H (agent context — SessionStart hook T016).**
  SessionStart hook читает project context для агента. **Post-T157**:
  hook читает `project.yaml` напрямую вместо запроса в БД.
  Simplifies cold-start ~30-50 ms (no SQLite open).

## 3. Functional Requirements

- **ДОЛЖНА** заменить `MetadataRepository` outbound port на
  `FileSystemProjectRepository` adapter в `src/adapters/outbound/
  metadata_filesystem/`. Same Protocol interface — все existing
  use cases работают без модификации сигнатур.

- **ДОЛЖНА** расширить `project.yaml` schema:
  ```yaml
  schema_version: 1  # для future migrations format'а
  name: foo
  created_at: 2026-05-27T15:00:00Z
  updated_at: 2026-05-27T15:00:00Z
  template: se-amp  # if known
  phases:
    - name: design
      status: done
      started_at: ...
      completed_at: ...
    - name: simulate
      status: in_progress
      started_at: ...
      completed_at: null
  ```

- **ДОЛЖНА** atomic write для `project.yaml` mutations — `*.tmp` +
  `Path.replace` (same pattern что T016 sim_results adapter).

- **ДОЛЖНА** иметь migration script `scripts/migrate-to-filesystem.py`
  (или `efactory project migrate --to filesystem` CLI команда):
  - Для каждой директории в `EFACTORY_PROJECTS_ROOT` где есть
    `db.sqlite` (legacy) — читает `projects` + `phases` tables,
    пишет `project.yaml`, удаляет `db.sqlite` после успешной записи.
  - Idempotent — повторный запуск без изменений (если manifest уже
    есть).
  - Backup `db.sqlite.bak-<DATE>` перед удалением.
  - Logs migrated/skipped count.

- **ДОЛЖНА** удалить из `pyproject.toml`:
  - `sqlalchemy>=2.x`
  - `aiosqlite>=0.22`
  - `alembic>=1.18`
  - `kuzu>=0.11.3`
  - И связанные test-зависимости если есть.

- **ДОЛЖНА** удалить:
  - `src/adapters/outbound/persistence_sql/` целиком (mapping/
    models/repository/migrations_runner/migrations/).
  - `tests/integration/adapters/graph_store/test_kuzu_smoke.py`.
  - References на Kùzu в `src/adapters/README.md`,
    `src/ports/README.md`, `src/application/README.md`,
    `src/composition/README.md`.
  - Environment variable `EFACTORY_DATABASE_URL` из docs +
    composition + container-boundary.md.

- **ДОЛЖНА** обновить `composition/main.py` — заменить SQLAlchemy
  session wiring на `FileSystemProjectRepository` injection.

- **ДОЛЖНА** обновить `docs/container-boundary.md` — убрать DB-related
  section, объяснить что projects state теперь pure filesystem.

- **ДОЛЖНА** заменить `reindex_projects` use case на `validate_
  manifests` (Q-A → b): scan `EFACTORY_PROJECTS_ROOT`, для каждой
  директории проверить presence `project.yaml` + Pydantic parse
  + report corrupt/orphaned. CLI rename: `efactory project reindex`
  → `efactory project validate` (с deprecation alias на 1 minor).

- **ДОЛЖНА** добавить ADR в `DECISIONS.md` под заголовком «Persistent
  state strategy: filesystem as single source of truth» с разделами:
  - Контекст (legacy DB-слой, ADR 2026-05-19 cross-ref).
  - Решение (что убираем + почему).
  - Альтернативы рассмотренные (per-project YAML, global SQLite,
    JSON-only).
  - Triggers для возвращения DB (с примерами из use cases T030 /
    sim-results / KB / BOM).

- **ДОЛЖНА** все 5 pre-push gates green после refactor; pytest без
  регрессий (existing testы create/get/list/update/delete/reindex
  должны проходить с FileSystemProjectRepository).

- **МОЖЕТ** иметь `project.yaml` validator (Pydantic) с
  `schema_version` field для будущих migrations format'а.

- **МОЖЕТ** в migration script добавить `--dry-run` flag для review
  перед deletion.

- **НЕ ДОЛЖНА** трогать sim-results infrastructure (T016) — она
  уже filesystem-based.

- **НЕ ДОЛЖНА** трогать KB infrastructure (T134) — markdown +
  filesystem, не DB.

- **НЕ ДОЛЖНА** изменять `MetadataRepository` Protocol interface —
  только swap adapter.

- **НЕ ДОЛЖНА** вводить новую DB-стек как часть refactor (это
  T-ID отдельно — when scale-trigger).

## 4. Success Criteria

- `efactory project {create,list,get,update,delete}` работают
  end-to-end на `FileSystemProjectRepository` без regression.
- Migration script успешно мигрирует Vladimir-овы 3 projects
  (`se-amp-demo`, `se_amp`, `sheetmetal-bracket-demo`) → `project.yaml`,
  удаляет `db.sqlite.bak-*`.
- venv size **reduction ≥ 25 MB** (sqlalchemy/aiosqlite/alembic +
  kuzu suite).
- Docker image baseline **reduction ≥ 25 MB** (после rebuild).
- Все 5 pre-push gates зелёные после refactor.
- Acceptance тесты: ≥ 1 happy-path на каждый CRUD + migration
  idempotency + unhappy (corrupt manifest → ValidationError).
- ADR в `DECISIONS.md` записан и cross-referenced из `pyproject.toml`
  comment, `composition/main.py` и `container-boundary.md`.
- SessionStart hook продолжает работать (T016 не сломан).

## 5. Key Entities

- **`ProjectManifest`** (Pydantic frozen, `schema_version=1`) —
  YAML model для `project.yaml`. Поля: `name`, `id` (UUID),
  `created_at`, `updated_at`, `template` (optional),
  `phases: list[PhaseEntry]`.

- **`PhaseEntry`** (Pydantic) — `name`, `status`, `started_at`,
  `completed_at`. Same shape что existing PhaseModel SQLAlchemy.

- **`FileSystemProjectRepository`** (adapter) — implements
  `MetadataRepository` Protocol. Internal state: `root_dir`
  (`EFACTORY_PROJECTS_ROOT`); per-call scans + reads `project.yaml`.

- **`MigrationScript`** (one-off script в `scripts/`) — reads
  `db.sqlite` (если есть), пишет `project.yaml`, backups & removes.

## 6. Assumptions & Constraints

- **EFACTORY_PROJECTS_ROOT** — single root; scale ожидается десятки
  директорий, не сотни / тысячи. Linear scan приемлем.

- **filesystem case-sensitive** (Linux+ext4 + Docker volume) —
  гарантирует уникальность project name через directory name.

- **No multi-user concurrent writes** — efactory single-user;
  no need для file locking сверх atomic-replace.

- **`statx.btime`** для real creation time (Linux 6+) через
  `os.stat().st_birthtime` (Python 3.13+); fallback на
  `created_at` field в manifest (записанный нами при create).

- **`project.yaml` уже существует** как concept (T014 templates)
  — расширяем same файл, не новый.

- **Existing tests на `MetadataRepository`** — protocol-based, должны
  pass с любым adapter implementing Protocol. Если есть SQLite-
  specific assertions (e.g. UNIQUE constraint error) — переписать
  под filesystem equivalent (FileExistsError).

- **UUID generation** — `uuid.uuid4()` при create, хранится в
  `project.yaml.id`. Used by existing code (e.g. `ProjectModel.id`).

- **Backward-compat** не нужен — это **breaking change для DB-state**.
  Migration script — once-off; новые projects сразу filesystem-based.

## 7. Out of Scope

- **Введение новой DB-стек** под конкретный use case (T030 / sim-
  results archive / KB semantic) — отдельные T-IDs.
- **Refactor sim-results T016** — уже filesystem-based.
- **Refactor KB T134** — уже filesystem-based.
- **Migration cross-host** — owners мигрируют locally; no cloud sync.
- **Backward-compat для legacy DB-state** — once-off migration,
  потом DB файлы удаляются.

---

## Clarify (заполняется Claude)

### Open questions

- **Q-A: Что делать с `reindex_projects` use case после T157?**
  - a) Удалить use case целиком (filesystem всегда truth, reindex
    логически нечего делать).
  - b) Превратить в `validate_manifests` — проверяет presence и
    корректность `project.yaml` во всех directories, отчёт об
    orphaned/corrupt.
  - **c) Keep use case с new semantics**: «refresh `updated_at`
    timestamps based on actual file mtime в директории» (useful
    после bulk-edit через external tools).
  - **Рекомендация: b** — validate-only имеет диагностическую
    ценность; old semantic (sync DB ↔ FS) больше нерелевантен.

- **Q-B: `project.yaml` schema — strict vs lenient?**
  - a) **Strict Pydantic** с `extra='forbid'` — любые extra fields
    → ValidationError.
  - b) Lenient — extra fields ignored (forward-compat для new fields
    от future versions).
  - c) `schema_version`-based — strict для current, lenient для older.
  - **Рекомендация: a** — strict, явный contract; форvard-compat
    через `schema_version` bump + migration.

- **Q-C: UUID generation — random vs deterministic?**
  - a) `uuid.uuid4()` — random, stored in manifest. Existing approach.
  - b) Deterministic — `uuid5(EFACTORY_NAMESPACE, name)` — same name
    always same UUID.
  - **Рекомендация: a** — same semantics что было; ID хранится в
    manifest, не recomputed.

- **Q-D: Migration script invocation — explicit vs auto-on-startup?**
  - a) **Explicit**: пользователь сам запускает `efactory project
    migrate --to filesystem` или `scripts/migrate-to-filesystem.py`.
    Idempotent.
  - b) Auto-on-startup: первый CLI call после T157 deploy замечает
    legacy db.sqlite и автоматически мигрирует. Riskier (silent
    destructive operation).
  - **Рекомендация: a** — explicit + idempotent. CLI command с
    `--dry-run`.

- **Q-E: Удалять `db.sqlite` after migration или backup-only?**
  - a) **Backup**: `db.sqlite` → `db.sqlite.bak-<DATE>`, не удалять.
    Юзер сам удаляет когда уверен.
  - b) Delete сразу — clean state.
  - c) `--keep` / `--delete` flag для script.
  - **Рекомендация: a** — backup default, не destructive; конечный
    delete — manually позже.

- **Q-F: Phases data — top-level в manifest или отдельный файл?**
  - a) **Embedded в `project.yaml`** (single file, easier ops).
  - b) Separate `phases.yaml` — модульность.
  - **Рекомендация: a** — phases — small data (<10 entries per
    project обычно); 1 file проще.

- **Q-G: `EFACTORY_DATABASE_URL` env — silent delete или deprecation
  warning?**
  - a) **Silent delete** — env var больше не читается, не упоминается.
  - b) Deprecation warning при presence в env.
  - **Рекомендация: a** — clean delete (efactory single-user, у
    Vladimir env пересоберётся вместе с T157 deploy).

- **Q-H: Test'ы на existing use cases (create/get/list/update/delete/
  reindex) — переписать full или adapter-swap?**
  - a) Adapter-swap — same tests, swap fixture с
    `FakeMetadataRepository` ↔ `FileSystemProjectRepository`. Если
    tests Protocol-based — pass without code changes.
  - b) Rewrite full — separate FS-specific scenarios.
  - **Рекомендация: a** — Protocol-based tests должны быть
    portable. Phase A проверка: какие tests сломаются → fix
    minimally.

- **Q-I: Phase migration script — Python or shell?**
  - a) **Python** (`scripts/migrate-to-filesystem.py`) — async-aware,
    могу reuse `sqlite3` stdlib + yaml dump.
  - b) Shell + sqlite3 CLI + yq.
  - **Рекомендация: a** — Python даёт type-safety + better error
    reporting; same stack что rest of project.

- **Q-J: Удалить ли `EFACTORY_DATABASE_URL` ENV из image entry-
  point/efactory-up бутстрапа сразу?**
  - a) Удалить (no longer needed).
  - b) Keep как unused (минимизация diff в `efactory-up`).
  - **Рекомендация: a** — full cleanup; не оставляем mystery env vars.

### Resolved (с ответами)

Vladimir (2026-05-27): все 10 вопросов — «по рекомендации».

- **Q-A → b**: `reindex_projects` превращается в `validate_manifests`
  — проверяет presence + parseability + corruption detection.
  Old semantic (sync DB ↔ FS) отброшен. CLI command renaming:
  `efactory project reindex` → `efactory project validate`.
- **Q-B → a**: `project.yaml` schema — **strict Pydantic** с
  `extra='forbid'`. Forward-compat через `schema_version` bump +
  migration script для each version.
- **Q-C → a**: UUID — `uuid.uuid4()` при create, хранится в
  `manifest.id`. Existing semantics сохранены (existing ProjectModel
  UUID approach).
- **Q-D → a**: Migration script — explicit invocation, idempotent,
  с `--dry-run` flag. Без auto-on-startup (silent destructive
  operations недопустимы).
- **Q-E → a**: `db.sqlite` backed up как `db.sqlite.bak-<DATE>`,
  не удаляется автоматически. Owner удаляет manually позже.
- **Q-F → a**: Phases embedded в `project.yaml` (top-level
  `phases:` ключ). Не отдельный файл — phases small (<10 entries
  typical).
- **Q-G → a**: `EFACTORY_DATABASE_URL` env — silent delete; нигде
  не упоминается post-T157. Single-user efactory, env пересоберётся.
- **Q-H → a**: Existing tests — Protocol-swap fixture
  (`FileSystemProjectRepository` ↔ `FakeMetadataRepository`).
  Phase A: проверка которые тесты сломаются (SQLite-specific
  assertions если есть) — fix minimally.
- **Q-I → a**: Migration script — Python (`scripts/migrate-to-
  filesystem.py`). Reuse stdlib `sqlite3` + `yaml`; type-safe;
  better error reporting. Same stack что rest of project.
- **Q-J → a**: `EFACTORY_DATABASE_URL` удаляется из `efactory-up`
  + container-boundary.md + всех ENV references сразу. Full
  cleanup, не leftover mystery env vars.

---

## Analyze (заполняется Claude)

Проход 2026-05-27, 12 issues: **2 Critical** (фиксим до
implementation, оба разрешены in-spec), **5 Warning** (predeclared
resolutions), **5 Note** (реализационные guidance).

### 🔴 Critical (фиксим до implementation)

- **A1: T157 scope меньше чем казалось — `ProjectManifestRepository`
  уже существует.** Discovery в Analyze: `src/ports/outbound/
  project_manifest_repository.py` уже **Protocol** с
  `save/load/exists/discover_all` + adapter `src/adapters/outbound/
  manifest_yaml/project_manifest_repository.py` уже реализован.
  Docstring port: «Manifest `project.yaml` — **источник истины**;
  SQL индекс **пересобирается** из манифестов через `ReindexProjects`».
  То есть **filesystem-first архитектура УЖЕ зацементирована** в
  design, SQL — derived view (использовался для quick lookup).
  **Resolution:** T157 не пишет новый `FileSystemProjectRepository`
  с нуля; использует **existing** `ProjectManifestRepository` +
  `ProjectFileRepository` (адаптеры готовы). Phase A: inventory
  каких use cases используют MetadataRepository vs
  ProjectManifestRepository → unify на manifest path. Удалить
  MetadataRepository Protocol + persistence_sql adapter + SQL
  composition wiring + alembic migrations + dependencies. Scope
  **уменьшается с ~500 LOC до ~150-250 LOC delete** (mostly
  rewiring + удалить).

- **A2: `phases` data — где живёт post-T157?** В spec'е (FR + Q-F →
  a) я зафиксировал «embedded в `project.yaml`». Но `ProjectManifestRepository.load()` возвращает `Project` VO — нужно проверить
  включает ли `Project` domain VO поле `phases`. Если **нет** —
  manifest нужно расширить + Project domain VO нужно расширить
  + `ProjectManifestRepository.save/load` нужно подхватывать
  phases.
  **Resolution:** Phase A inventory: проверить
  `src/domain/project.py` и `src/domain/phase.py` (упомянут в grep
  earlier). Если Phase entity отдельная — добавить
  `Project.phases: list[Phase]` field, обновить
  `ProjectManifestRepository` adapter. Если уже есть — no-op.

### 🟡 Warning (predeclared resolutions)

- **A3: Migration script — сложность из-за per-project SQLite.**
  Vladimir-у в `$HOME/efactory-projects/{se-amp-demo, se_amp,
  sheetmetal-bracket-demo}` каждая директория может иметь свой
  `.efactory/db.sqlite` (per-project schema, T098 introduced).
  Migration читает каждую, dumps phases, mergeit в manifest.
  **Predeclared resolution:** scripts/migrate-to-filesystem.py
  использует stdlib `sqlite3` (sync), iterates over directories
  в `EFACTORY_PROJECTS_ROOT`, читает `projects` (1 row per dir,
  поскольку per-project DB) + `phases`, пишет в
  `project.yaml`. Backup как `.bak-<DATE>`. Idempotent (skip
  если уже migrated — manifest присутствует, db.sqlite уже backed up).

- **A4: `MetadataRepository` interface удаление — какие use cases
  фактически зависят от SQL-specific семантики?** Phase A inventory:
  - SQL UNIQUE constraint → FileExistsError при duplicate name.
  - SQL transaction → atomic create+save → individual file ops
    в filesystem layer.
  - SQL FK cascade (phases.project_id → projects.id) → embedded
    в manifest (no cascade нужен).
  **Predeclared resolution:** Phase A проверка какие tests на
  SQL-specifics: переписать на filesystem equivalent (FileExists,
  ValueError на missing). Если tests Protocol-based (через
  fake) — pass without changes.

- **A5: `Project.id` UUID — derived от directory hash или random?**
  Q-C → a сказал random (uuid4). Но если manifest хранит ID, при
  copy/rename директории ID меняется или нет? Phase A проверить
  что `Project.id` semantics не используется как stable cross-
  session reference. Если используется (e.g. в sim-results path
  как `<project_id>/<analysis>.json`) — поломка.
  **Predeclared resolution:** Phase A grep по `project.id` /
  `project_id` references; если ID часть filesystem paths/JSON
  keys → **stable** UUID нужен (hash directory name? UUID5 с
  namespace + name?). Если нигде не persist'ится — random ok.

- **A6: Backward-compat для existing SimResult files** — sim-results
  T016 пишет в `<PROJECT>/.efactory/sim-results/<TIMESTAMP>-<analysis>.json`.
  Если path использует `Project.id` → ID нужен stable. Phase A
  проверка.

- **A7: ADR formatting в `DECISIONS.md`** — спека требует ADR с
  contexts/decision/alternatives/triggers. Какой формат имеют
  existing ADRs в DECISIONS.md? Phase A посмотреть → match style.

### 🟢 Note (к сведению)

- **A8: 154 references на `MetadataRepository`/`EFACTORY_DATABASE_
  URL`** через src+tests (counted в Analyze). Это **переписать
  массово** через grep+sed может быть проще чем по одному. Phase D
  cleanup.

- **A9: Decision-port отдельный.** `DecisionRepository` (T099) —
  уже markdown-based, отдельный port. T157 его не касается.
  Out of scope явно.

- **A10: Тестовая инфраструктура.** Existing tests на
  `MetadataRepository` через fake; если они Protocol-portable —
  swap на `ProjectManifestRepository` fake. Phase A: assess.

- **A11: Pyproject deps — точное удаление.** `sqlalchemy`,
  `aiosqlite`, `alembic`, `kuzu` — четыре main dependencies.
  Также проверить indirect (psycopg, asyncpg — нет). uv.lock
  пересохранится.

- **A12: Docker image baseline reduction.** Estimate: 21 MB
  (kuzu) + 9 MB (sqlalchemy) + 1 MB (aiosqlite) + 5 MB (alembic +
  Mako) ≈ **35 MB** savings в venv layer. Image baseline ↓
  estimate 25-40 MB.

### Resolutions inline в spec

A1 — Phase plan переписан, A2 — добавлен «Phase A inventory» step,
A5/A6 — Phase A grep на `Project.id` references.

---

## Phase plan (Implementation — 4 фазы TDD outside-in)

### Phase A — Inventory + domain VO extension

1. **Inventory** (Critical A1/A2/A5/A6/A11):
   - Grep всех use cases / tests / композиции которые используют
     `MetadataRepository` vs `ProjectManifestRepository`. Build
     map: «какой use case → какой port».
   - Grep `project.id` / `Project.id` references — определить
     где ID персистится / используется как stable reference.
   - Inspect `Project` domain VO (`src/domain/project.py`) + `Phase`
     entity (`src/domain/phase.py`) — нужно ли расширить.
   - List все tests которые используют SQL-specific семантику
     (UNIQUE error, FK cascade).
2. **Domain extension** (если нужно — A2 resolution):
   - `Project.phases: list[Phase]` field в domain VO.
   - `ProjectManifest` Pydantic schema в `manifest_yaml` adapter
     (если ещё нет) с `schema_version: 1`, `phases: list[PhaseEntry]`.
3. **Acceptance tests on existing fake repository** — verify что
   they pass on the Manifest adapter с/без changes.

### Phase B — Use case rewiring + reindex → validate

1. **Rewire all 12 use cases** с `MetadataRepository` → through
   `ProjectManifestRepository` для read paths;
   `ProjectFileRepository` для write directory ops; manifest
   adapter save для write metadata.
2. **`reindex_projects` use case → `validate_manifests`** (Q-A → b):
   - Same use case, new semantic — scan directories, validate
     manifests, report orphaned/corrupt.
   - CLI command `efactory project reindex` → `efactory project
     validate` (deprecation alias на 1 minor).
3. **Unit tests** через FakeManifestRepository (Q-H → a).

### Phase C — Migration script + remove SQL adapter

1. **`scripts/migrate-to-filesystem.py`** (Q-D → a, Q-I → a):
   - Iterates `EFACTORY_PROJECTS_ROOT`, для each dir с
     `.efactory/db.sqlite` (legacy):
     - Read `projects` row + `phases` rows via stdlib `sqlite3`.
     - Compose `project.yaml` (extend если уже существует).
     - Backup `db.sqlite` → `db.sqlite.bak-<DATE>`.
     - Log migrated/skipped count.
   - Idempotent. `--dry-run` flag.
2. **Run migration на Vladimir's** 3 existing projects (manual smoke).
3. **Delete `src/adapters/outbound/persistence_sql/`** целиком
   (mapping/models/repository/migrations_runner/migrations dir).

### Phase D — Cleanup deps + Kùzu + composition + ADR

1. **`pyproject.toml`** — удалить `sqlalchemy`, `aiosqlite`,
   `alembic`, `kuzu` из dependencies. `uv sync` пересохранит lock.
2. **Kùzu cleanup**:
   - Delete `tests/integration/adapters/graph_store/test_kuzu_smoke.py`.
   - Remove `outbound/graph_store/` references в README'ях.
3. **Composition** (`composition/main.py`):
   - Replace SQLAlchemy session/engine wiring с manifest adapter
     injection.
   - Remove `EFACTORY_DATABASE_URL` settings field.
4. **Docs cleanup**:
   - `docs/container-boundary.md` — remove DB section.
   - `pyproject.toml` comment update.
   - `efactory-up` — remove `EFACTORY_DATABASE_URL` from env passthrough.
5. **ADR в `DECISIONS.md`** «Persistent state strategy: filesystem
   as single source of truth» (per FR + Q-J → a).
6. **CHANGELOG.md [Unreleased]** entry.
7. **BOARD.md Doing → Done** в задачном PR.
8. **Self-review** + pre-push gates + push + PR + closing commit.

### Out-of-task spin-offs (BACKLOG when triggered)

- **T-future-1**: SPICE-models library (T030 future trigger) — DB
  introduction под конкретный use case.
- **T-future-2**: sim-results cross-project archive — DB при scale
  > 1000 results.
- **T-future-3**: KB semantic search via sqlite-vec при > 100 entries.
