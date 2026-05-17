## Spec: T099 — Decision aggregate (журнал проектных решений)

**Статус:** Analyzed
**Дата создания:** 2026-05-17
**Связанные документы:**
- `DECISIONS.md` → ADR 2026-05-17 «Domain expansion direction: D»
  (T099 = фаза D, последняя в направлении).
- `CONCEPT.md` §4.3 (поле `decisions:` в YAML), §4.4 (markdown
  шаблон DDR — Design Decision Record).
- `BACKLOG.md` → запись T099 (исходный набросок).
- `specs/T097-phase-vo/spec.md` (фаза B — Phase VO).
- `specs/T098-manifest-primary/spec.md` (фаза C — manifest primary;
  atomic dual write паттерн переиспользуется).

---

### 1. Overview

Каждое значимое проектное решение (выбор схемы, изменение номинала,
архитектурный выбор) фиксируется как:
- **Markdown файл** `<project>/decisions/D###_<slug>.md` — детали
  (контекст, варианты, решение, подтверждение). Источник истины
  для деталей.
- **Краткая запись** в `project.yaml → decisions:` — id, date,
  summary, rationale, evidence, session. Источник истины для
  индекса.

T099 вводит **`Decision` aggregate** в domain, outbound port
`DecisionRepository`, filesystem markdown adapter, application
use cases (`AddDecision`, `ListDecisions`, `GetDecision`) и CLI
`efactory decision add / list / show`. Без edit и delete в v1.

Markdown — truth: при desync (manifest reference есть, markdown
файла нет — или наоборот) выигрывает markdown. `efactory project
reindex` (расширенный из T098) синхронизирует manifest decisions
с фактическими файлами в `decisions/`.

### 2. User Stories

- **Зафиксировать решение.** Как разработчик, я выбрал между двумя
  топологиями (SE vs PP); хочу `efactory decision add --project
  myamp --title "Выбор SE-топологии" --status accepted --summary
  "..." --rationale "..."` — получить готовый `D001_*.md` с
  заполненной шапкой, плюс reference в manifest.
- **Посмотреть журнал.** Как разработчик, через год я возвращаюсь
  к проекту и хочу `efactory decision list --project myamp` —
  таблица решений (id, date, status, summary).
- **Посмотреть детали.** `efactory decision show --project myamp
  --id D002` → полный markdown файл в stdout.
- **Восстановить контекст.** Каталог `decisions/` переехал на новую
  машину вместе с проектом (T098 portability). После `reindex`
  manifest decisions подтягивается из markdown файлов автоматически.

### 3. Functional Requirements

#### Domain

- ДОЛЖНА: появиться сущность `Decision` (frozen Pydantic VO):
  ```python
  class DecisionId(str):  # Annotated[str, AfterValidator(_validate_id)]
      pass  # формат D### (D + 3+ цифры)

  class DecisionStatus(StrEnum):
      PROPOSED = 'proposed'
      ACCEPTED = 'accepted'
      REJECTED = 'rejected'

  class Decision(BaseModel):
      model_config = ConfigDict(frozen=True, extra='ignore')
      id: DecisionId
      title: ProjectName  # переиспользуем path-safe валидатор
      date: date  # datetime.date, не datetime
      status: DecisionStatus
      summary: str   # 1-2 строки; min_length=1
      rationale: str  # min_length=1
      evidence: Path | None = None  # путь относительно project_path
      session: Path | None = None
  ```
- ДОЛЖНА: появиться сущность `DecisionRef` (frozen Pydantic VO) —
  компактная запись для manifest YAML:
  ```python
  class DecisionRef(BaseModel):
      model_config = ConfigDict(frozen=True, extra='ignore')
      id: DecisionId
      date: date
      summary: str
      rationale: str
      evidence: Path | None = None
      session: Path | None = None
  ```
  (Title и status не вшиваются в reference — title есть в имени
  файла, status — в markdown шапке. Это минимизирует
  избыточность.)
- ДОЛЖНА: `Project.decisions: tuple[DecisionRef, ...] = ()` —
  новое поле, default empty. Pydantic v2 model_config уже
  `extra='ignore'` — старые manifest'ы без `decisions:` валидны.

#### Outbound port

- ДОЛЖНА: `DecisionRepository` (Protocol) в
  `src/ports/outbound/decision_repository.py`:
  ```python
  async def save(self, project_path: Path, decision: Decision) -> Path: ...
  async def load(self, project_path: Path, decision_id: str) -> Decision: ...
  async def list_all(self, project_path: Path) -> list[Decision]: ...
  async def next_id(self, project_path: Path) -> DecisionId: ...
  ```
  - `save` записывает markdown файл `decisions/D###_<slug>.md`
    атомарно, возвращает путь к нему. Каталог `decisions/`
    создаётся при отсутствии.
  - `load` парсит markdown по id; бросает
    `DecisionNotFoundError` если файла нет.
  - `list_all` сканирует `decisions/*.md`, парсит, возвращает
    sorted by id.
  - `next_id` возвращает `D<max+1:03d>` (или `D001` для пустого
    каталога).
- ДОЛЖНЫ: контрактные исключения в том же модуле порта:
  `DecisionNotFoundError`, `DecisionInvalidError`.

#### Adapter

- ДОЛЖНА: `FilesystemDecisionRepository` в
  `src/adapters/outbound/decision_markdown/`. Шаблон markdown
  (фиксированный, ASCII anchors для парсинга):
  ```markdown
  # {id}: {title}

  **Дата:** {date_iso}
  **Статус:** {status}
  {?session: "**Сессия:** {session}\n"}

  ## Summary
  {summary}

  ## Rationale
  {rationale}

  {?evidence: "## Evidence\n{evidence}\n"}
  ```
  - Атомарная запись (tmp + `os.replace`, как T098 manifest).
  - Слаг — `_slugify(title)`: lowercase ASCII, кириллица через
    `unicodedata.normalize('NFKD')` + ASCII drop, не-[a-z0-9]
    → dash, collapse multiple dashes, strip leading/trailing
    dashes, max 50 chars; fallback `untitled` для пустой
    строки.
  - `load` парсит обратно по anchor-секциям (`# `, `## Summary`,
    `## Rationale`, `## Evidence`, и `**Дата:**`, `**Статус:**`,
    `**Сессия:**` — строгий формат).

#### Application

- ДОЛЖНА: `AddDecision` use case (`src/application/add_decision.py`):
  ```python
  async def add_decision(
      *, project_name: str, title: str, date: date, status: DecisionStatus,
      summary: str, rationale: str,
      evidence: Path | None = None, session: Path | None = None,
      repo: MetadataRepository,
      manifest_repo: ProjectManifestRepository,
      decision_repo: DecisionRepository,
  ) -> Decision:
  ```
  Pattern (по аналогии с T098 manifest-first):
  1. `get_project` (через SQL.path → manifest.load) — даёт actual
     `Project` aggregate.
  2. `decision_repo.next_id(project.path)` → новый id.
  3. Создаём `Decision` (Pydantic валидация title, summary etc.).
  4. `decision_repo.save(project.path, decision)` → markdown
     записан.
  5. Project mutate: `project.decisions = (*existing, ref)`.
     `updated_at = now()`.
  6. `manifest_repo.save(project)` — обновлённый manifest.
  7. `metadata_repo.update(project)` (для consistency,
     SqlAlchemyError → IndexPersistenceError).

  Partial-failure: markdown записан, manifest save упал →
  `DecisionPersistenceError` (новый, аналог
  `IndexPersistenceError`). Recovery: `reindex` подтянет
  markdown в manifest.

- ДОЛЖНА: `ListDecisions` use case:
  ```python
  async def list_decisions(*, project_name, repo, manifest_repo,
                            decision_repo) -> list[Decision]
  ```
  Источник истины — markdown файлы (`decision_repo.list_all`),
  не manifest reference (markdown = truth).

- ДОЛЖНА: `GetDecision` use case:
  ```python
  async def get_decision(*, project_name, decision_id, repo,
                          manifest_repo, decision_repo) -> Decision
  ```
  → `decision_repo.load`; `DecisionNotFoundError` если файла нет.

#### Расширение `ReindexProjects` (T098)

- ДОЛЖНО: при загрузке manifest'а в primary mode — обновить поле
  `decisions` в Project из реального содержимого `decisions/`
  на диске (markdown = truth). То есть после reindex'а manifest
  не может содержать reference на удалённый markdown — он будет
  выкинут; markdown без reference — появится.
- Реализация: после `manifest_repo.load(path)` зовём
  `decision_repo.list_all(path)` → собираем `DecisionRef` для
  каждого → `project = project.model_copy(update={'decisions':
  tuple(refs)})` → `manifest_repo.save(project)` → SQL upsert.
- Это меняет contract `reindex`: теперь он не просто SQL→manifest
  upsert, а ещё «manifest sync с markdown files». Тесты T098
  reindex остаются валидными — без `decisions/` папки поведение
  не меняется.

#### CLI

- ДОЛЖНЫ: новые Typer subcommand'ы в новом subapp
  `efactory decision`:
  ```
  efactory decision add --project <name> --title <t> --status <s>
                        --summary <text> --rationale <text>
                        [--date YYYY-MM-DD] [--evidence PATH]
                        [--session PATH]
  efactory decision list --project <name>     # таблица
  efactory decision show --project <name> --id D001    # markdown
  ```
  - `--date` default = today (UTC).
  - `--status` default = `accepted`.
  - Error handling: `ProjectNotFoundError` → exit 1;
    `ProjectManifestMissingError` / `DecisionPersistenceError`
    / `IndexPersistenceError` → exit 2; `DecisionNotFoundError`
    → exit 1 (`show`); `ValidationError` → exit 2.

### 4. Success Criteria

- TDD outside-in: e2e `decision add → list → show` → unit
  с fake-портами → adapter integration с `tmp_path` (markdown
  round-trip).
- `uv run pytest` зелёный, coverage ≥ 80% на `src/`.
- 4 проверки гейта + `lint-imports` — 0 ошибок.
- **markdown шаблон совпадает с CONCEPT §4.4** (по существенным
  полям; точные секции «Контекст/Варианты/Подтверждение» — TODO
  для LLM-driven decisions, в v1 рендерим только обязательные).
- **Round-trip:** `save → load` восстанавливает Decision побайтово
  по всем полям (date, status, evidence, session).
- **Reindex sync:** ручное добавление `D004_*.md` в
  `decisions/` → `efactory project reindex` → `decision list`
  показывает D004; manifest содержит ref.
- **Acceptance test on growth:** добавить 50 decisions через
  CLI без падения list-performance. Целевая планка: `decision
  list` для 50 решений < 200ms.
- **Partial-failure:** markdown записан, manifest save fails →
  `DecisionPersistenceError`, markdown на диске, reindex
  восстанавливает.

### 5. Key Entities

- **`Decision`** — frozen aggregate, поля выше.
- **`DecisionRef`** — компактная запись для manifest decisions list.
- **`DecisionId`** — Annotated[str, validator] = `D###` format.
- **`DecisionStatus`** — StrEnum (proposed | accepted | rejected).
- **`DecisionRepository`** — Protocol port (save / load / list_all
  / next_id).
- **`FilesystemDecisionRepository`** — markdown filesystem adapter.
- **`DecisionNotFoundError`** / **`DecisionInvalidError`** —
  контрактные исключения порта.
- **`DecisionPersistenceError`** — application error (markdown ok,
  manifest save fails). Wraps original. Сообщение —
  «Decision <id> saved to markdown; failed to sync manifest:
  <reason>. Run `efactory project reindex` to recover.»
- **`AddDecision` / `ListDecisions` / `GetDecision`** — use cases.
- **`Project.decisions: tuple[DecisionRef, ...]`** — новое domain
  поле, default empty.

### 6. Assumptions & Constraints

- Single-user CLI; конкурентного создания decisions нет →
  ID auto-increment по `max(file ids) + 1` безопасен без lock'а.
- POSIX storage_root (как T098).
- `decisions/` каталог создаётся lazy на первый `add`.
- Markdown шаблон фиксирован; кастомизация — out of scope (если
  понадобится — отдельная задача с Jinja).
- Manifest schema_version остаётся = 1; `decisions:` добавлено
  как optional field — старые manifest'ы без `decisions:`
  валидируются (default ()).
- `Decision.title` использует тот же валидатор, что
  `ProjectName` (T092): защита от path-traversal в slug.
- `evidence` / `session` — `Path` относительный (валидируем что
  не absolute); на load проверяем относительность.

### 7. Out of Scope

- **Edit / Delete decision.** Decisions исторический журнал;
  v1 — append only. Edit — отдельная задача (потребует
  consistency policy).
- **Кастомные секции markdown («Контекст / Варианты /
  Подтверждение»).** LLM-driven в Phase 1a — приедет с реальным
  bridge'ем (например, при `bridge_edit_and_resim` LLM может
  записать решение через MCP tool с богатым контекстом). В v1
  пользователь добавляет через CLI (короткие поля) или
  редактирует markdown вручную после `add`.
- **Decision per board** в multi-board проектах. Boards в YAML —
  отдельный концепт; в v1 decisions flat per project.
- **Session как сущность** (CONCEPT §4.5). Phase 1b в roadmap.
  `session: Path` в Decision — просто строка-путь, без
  валидации существования.
- **ID format >D999.** Реализация естественно расширится до
  D1000+; жёстко 3 цифр не требуем (format `D{n:03d}` для
  n < 1000, иначе `D{n}`).
- **Markdown с YAML front-matter.** Не используем — структура
  читается из markdown шапок. Если позже понадобится — мигрируем
  с bump schema_version.
- **CLI флаги богатого редактирования** (`--variant`,
  `--context`, `--confirmation`). v1 — минимум; расширение
  с LLM-driven фичами.

---

### Clarify (resolved)

Все вопросы решены дефолтами при первом анализе (single-author
spec, scope узкий, паттерны переиспользуются из T098).

1. **`title` vs `summary` различение** — оба обязательные. title —
   человеческий заголовок (в markdown header и slug); summary —
   одна-две строки для journal-view. Это разные роли.
2. **`status` дефолт** — `accepted` (по CONCEPT шаблону, где
   статус «Принято» — основной кейс).
3. **`date` тип** — `datetime.date`. CONCEPT YAML использует ISO
   date без времени; для журнала решений секунды не значимы.
4. **`evidence` / `session` пути** — **относительные** к project_path.
   Валидируется `AfterValidator` (`assert not p.is_absolute()`).
   Хранятся как переданы; разрешение в абсолют — задача потребителя.
5. **Manifest schema_version** — остаётся 1. `decisions:` —
   forward-compatible optional поле (default `()`). Bump до 2 не
   нужен.
6. **Slug стратегия** — кратко: NFKD normalize → drop non-ASCII →
   `re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:50]` →
   fallback `untitled`. Регулярка простая, тестируем edge-cases
   (кириллица «Выбор SE-топологии» → `vybor-se-topologii`; пустой
   slug → `untitled`).
7. **ID >999** — `D{n}` без zero-pad для n ≥ 1000. Сортировка по
   числовой части. Тестируем.
8. **Markdown шаблон v1** — обязательные секции: Headline (id +
   title), Дата, Статус, Summary, Rationale. Опциональные:
   Сессия (если задана), Evidence (если задан). Секции
   «Контекст / Варианты / Решение / Подтверждение» из CONCEPT
   §4.4 — добавятся в Phase 1a с LLM-driven decisions. Это OK:
   шаблон CONCEPT — иллюстративный для богатых случаев.
9. **Partial-failure** — markdown = truth. `DecisionPersistenceError`
   с подсказкой `reindex`. Recovery: `reindex` подтягивает
   decisions из `decisions/*.md` в manifest.
10. **Concurrent add** — single-user → не защищаемся. При появлении
    daemon/web — пересмотрим в отдельной задаче (file-lock или
    транзакции). Документируется.

---

### Analyze

#### 🔴 Critical

##### C1. Markdown round-trip строгий формат

Adapter парсит markdown по anchor-секциям. Если пользователь
вручную добавит секцию в середину (например, `## Context`) —
парсер должен либо (а) её проигнорировать, либо (б) упасть.

**Резолюция:** **(а) игнорировать unknown секции** — markdown
для человека, лишние секции (Context / Варианты / Подтверждение,
заметки) не должны ломать parse. Сохраняем строгость для
обязательных секций: отсутствие `## Summary` или
`## Rationale` → `DecisionInvalidError`. Тест на «markdown
с дополнительной секцией Context — load успешен, секция
не теряется в plain-чтении через `show`».

##### C2. Sync `decisions` поля Project в reindex

`ReindexProjects` теперь не «manifest → SQL», а ещё «manifest
decisions sync с markdown files на диске». Это расширение
семантики reindex (T098 spec § 3 — там reindex только SQL).
Документируем в docstring reindex.

**Резолюция:** реализуем расширение, сохраняем backward compat:
без `decisions/` каталога — поведение reindex'а идентично T098.
Тесты T098 продолжают работать.

##### C3. ID generation race на параллельных `add`

Если два процесса одновременно зовут `decision add`, оба могут
получить D003 → один overwrites другой markdown.

**Резолюция:** single-user CLI (Assumption); защита не реализуется.
Документируем в коде. При появлении daemon — отдельная задача
(file-lock через `fcntl` либо UUID-based id вместо инкремента).

#### 🟡 Warning

##### W1. `evidence` / `session` относительный путь — что если пользователь укажет absolute?

**Резолюция:** `AfterValidator(_validate_relative_path)` бросает
ValueError если absolute. CLI ловит ValidationError → exit 2 +
понятное сообщение «evidence path must be relative to project».

##### W2. Кириллица в `title` и slug

Cyrillic via `unicodedata.normalize('NFKD')` пытается
декомпозировать, но кириллица не имеет ASCII-эквивалентов в NFKD
(в отличие от диакритики). В результате drop non-ASCII →
пустой slug → fallback `untitled`.

**Резолюция:** v1 — это OK, fallback `untitled` приемлем. Slug
не критичен (id всё равно уникален). Тест документирует
поведение для cyrillic. Для будущего — можно добавить
transliteration (например, `transliterate` лёжит на PyPI),
но это нагрузка на dep и v1 не блокирует.

##### W3. Дублирование slug при одинаковых title

`D001_my-decision.md`, `D002_my-decision.md` — slug одинаков, id
разный → разные имена файлов (id префикс), коллизий нет.

**Резолюция:** не проблема, документируем.

#### 🟢 Note

##### N1. `date` импорт vs `datetime` коллизия имён

`from datetime import date` vs `Decision.date` поле. Конфликт
скрывается scope'ом, но читабельно: использовать full path
`datetime.date` в annotations либо alias `from datetime import
date as date_t`. Решение по месту.

##### N2. ID parsing для list_all

`list_all` сортирует by id. id — строка `D001` / `D002` /
`D1000`. Lexicographic sort: D1, D10, D2 (D10 < D2 lex). Нужно
extract numeric: `key=lambda d: int(d.id[1:])`. Тест на сортировку
с D9, D10, D100 в одном проекте.

##### N3. Manifest write при `add` — atomic dual write нюанс

Use case делает manifest.save после decision_repo.save. Если
manifest.save упал — markdown уже на диске. CLI ловит
`DecisionPersistenceError` (новый). Сообщение должно подсказать
`reindex` — после reindex'а manifest пополнится.

##### N4. CLI table формат

`decision list` — TSV (как `project list`): id<tab>date<tab>
status<tab>summary. Без rich table — минимальная dep, parseable.

##### N5. Тестируем «old manifest без decisions» backward compat

E2E: проект, созданный «до T099» (manifest без `decisions:`) →
`decision add` корректно работает (Project.decisions default
== ()), manifest после save содержит `decisions:`.

##### N6. CONCEPT §4.4 формулировка про автогенерацию

«Решения создаются автоматически, когда LLM фиксирует изменение
номинала или топологии с обоснованием» — это про Phase 1a
LLM-driven. В T099 — фундамент: ручной CLI add. Тесты на
LLM-flow не требуются.

##### N7. `Project.model_dump` для manifest YAML с `decisions`

После добавления поля `decisions: tuple[DecisionRef, ...]`,
`model_dump(mode='json')` сериализует кортеж как список dict'ов
(каждый DecisionRef). YAML принимает. Manifest schema v1 + новое
поле — forward compat через `extra='ignore'`.

##### N8. Phasing

Реализация в 2 фазы (паттерн меньше T098):
- **Phase 1:** Domain (Decision, DecisionRef, DecisionId,
  DecisionStatus + Project.decisions) + DecisionRepository port
  + filesystem markdown adapter + расширение ReindexProjects.
- **Phase 2:** Application use cases (Add/List/Get) + CLI commands
  + e2e + close BOARD.
