# Spec: Agent Knowledge Base — persistent KB для runtime-агента efactory

**Статус:** Analyzed
**Дата создания:** 2026-05-26
**Clarify прошёл:** 2026-05-26 (11 вопросов, все «по рекомендации»)
**Analyze прошёл:** 2026-05-26 (issues отражены в FR/Assumptions)
**Связанные документы:**
- `BACKLOG.md → T134` (источник — Phase E T131, расширен 2026-05-21
  control examples из T131 / T132 / T133).
- `DECISIONS.md 2026-05-24` «Tool surface = Bash + efactory CLI +
  filesystem, не MCP» — KB живёт на filesystem, не MCP-server.
- `T016` — SessionStart hook + `additionalContext` injection
  (используется для bootstrap KB index при старте сессии агента).
- `T140` — `docs/container-boundary.md` (KB persistence через host
  bind-mount, как `.claude` state).
- `T014` — pattern bootstrap'а из репо в host state
  (`docker/runtime-agent-commands/` → `$HOME/efactory-state/claude/
  commands/`). KB использует тот же механизм.
- `T154` — follow-up T134, заведена 2026-05-26 в BACKLOG: «Full
  migration dev-process knowledge (DECISIONS.md / CHANGELOG.md /
  auto-memory Гвидо / mem0) в agent KB» — отдельная curation-задача
  с поэтапным review per entry (Q-F → c).

---

## 1. Overview

Persistent knowledge base для runtime-агента efactory (Claude Code в
`efactory:linux` контейнере). Решает проблему: агент **не имеет
доступа** к auto-memory разработчика (вне репо, приватная), mem0
(приватная Vladimir+Гвидо), и работает в свежей сессии каждый раз —
без аккумулированного опыта прошлых проектов.

KB закрывает три класса знаний, которые иначе теряются между
сессиями:
1. **«Готовый ответ на типичный запрос»** — какую slash-команду
   использовать для какого user-request'а. Защита от изобретения
   велосипеда (написать свой ngspice-wrapper вместо `/sim-run`) и от
   ухода в исходники efactory ради поиска «что у нас есть».
2. **Hard-won technical lessons** — pitfall'ы и workaround'ы из
   развития efactory (XSPICE gyrator-cap для saturable, R_dc_leak для
   floating secondary, 2D-planar inherent gap к ZHANG, и т.п.).
   Сейчас они в `DECISIONS.md` / `CHANGELOG.md` / `feedback_*` auto-
   memory Гвидо — не primary канал для агента.
3. **Project-specific decisions** — что user уже решил в текущем
   проекте (выбранная топология, target specs, ranged-out альтернативы).
   Сейчас в `DECISIONS.md` проекта, но без structured retrieval.

## 2. Сценарии использования

> «User» = конечный проектировщик (физик / инженер РЭА), не
> разработчик efactory. «Agent» = runtime-агент Claude Code в
> `efactory:linux`.

- **Сценарий A (typical request → command mapping).**
  User: «построй график АЧХ». Agent: видит в KB topic
  `scenarios-quick-mapping`, выбирает `/plot-ac`, выполняет, не
  пишет свой matplotlib-wrapper и не лезет в исходники efactory.

- **Сценарий B (technical lesson lookup, реактивный).**
  Agent проектирует saturable transformer model. До mutation netlist'а
  проверяет KB на topic `saturable-spice` — находит правило «XSPICE
  gyrator-cap, не PWL» — применяет правильный path сразу, без
  numerical blow-up.

- **Сценарий C (technical lesson lookup, проактивный).**
  Agent готовит Fourier analysis на OPT с floating secondary. Перед
  запуском просматривает KB topic `spice-numerical-traps` — находит
  правило «inject R_dc_leak перед .four» — auto-инжектирует, получает
  релевантный THD сразу.

- **Сценарий D (write — агент пополняет KB в проде).**
  Agent в работе с user'ом нашёл новый pitfall (например, конкретная
  silicon-FET требует особый convergence helper). Записывает entry в
  KB через `/kb-add <topic> <markdown body>` — следующая сессия
  (и другой проект) этот lesson видит.

- **Сценарий E (curation — dev цикл).**
  Vladimir в dev-цикле efactory находит новый lesson при работе с
  Гвидо. Кладёт его в `docker/runtime-agent-knowledge-base/
  <topic>.md` (built-in seed). Следующий `docker build` запекает в
  образ. Существующие host-mutated entries сохраняются (host wins
  policy).

- **Сценарий F (developer migrate знания из dev-process артефактов).**
  Однократный bootstrap: ключевые lesson'ы из `DECISIONS.md`,
  `CHANGELOG.md`, `feedback_*` auto-memory Гвидо переносятся в
  initial seed `docker/runtime-agent-knowledge-base/*.md`. Это
  one-shot задача (не входит в T134 core, см. §7).

## 3. Functional Requirements

- **ДОЛЖНА** хранить KB как набор markdown-файлов с frontmatter
  (унифицировано со slash-командами — те же conventions). Один файл
  = один topic.
- **ДОЛЖНА** иметь два источника entries:
  - **Built-in seed** в репо (`docker/runtime-agent-knowledge-base/
    *.md`), запекается в образ через Dockerfile.
  - **Host-mutated** (`$HOME/efactory-state/knowledge-base/*.md`)
    — persistence между `docker rm`, как `.claude` state в T140.
- **ДОЛЖНА** при `efactory-up --agent` bootstrap'ить built-in seed
  в host state (паттерн T014 commands bootstrap): host wins при
  conflict; новый аргумент `--reset-claude-state` (T014) расширяется
  на KB директорию.
- **ДОЛЖНА** через расширение SessionStart hook (T016) инжектировать
  в `additionalContext` **KB index** (TOC: список topics + 1-line
  description каждого), не full content. Полный content агент
  читает через `Read` по необходимости.
- **ДОЛЖНА** предоставить slash-команду **`/kb-add <topic>`** для
  агента: append new entry в host-mutated KB (с frontmatter
  валидацией).
- **ДОЛЖНА** предоставить slash-команду **`/kb-search <query>`** для
  агента: grep-style поиск по KB body + frontmatter.
- **ДОЛЖНА** валидировать KB entries через integration test (как
  `test_runtime_agent_commands.py` для slash-команд): frontmatter
  schema, unique topic names, syntax check.
- **ДОЛЖНА** включать в initial seed **минимум 10 control examples**
  (9 existing из T131+T132+T133 + новый «typical scenarios mapping»).
- **МОЖЕТ** иметь CLI `efactory kb {list,show,add,search}` для
  validation вне runtime контейнера (dev-time check).
- **НЕ ДОЛЖНА** использовать vector DB / embeddings / RAG (premature
  для нашего scale; markdown + grep + Claude Code native Read
  достаточны на годы вперёд).
- **НЕ ДОЛЖНА** дублировать `DECISIONS.md` / `CHANGELOG.md` (они
  остаются для dev-process), а selectively extract'ить только то, что
  агенту нужно во время runtime.
- **НЕ ДОЛЖНА** включать MCP-server (ADR 2026-05-24).
- **НЕ ДОЛЖНА** автоматически migrate'ить весь существующий dev-
  process контент (DECISIONS / CHANGELOG / auto-memory) — это
  отдельная задача после T134 skeleton готов.

## 4. Success Criteria

- **10 control-example regression test** (9 existing из T131/T132/
  T133 BACKLOG + новый «typical scenarios»). Каждый example задан как:
  - User-style query (free text).
  - Ожидаемый KB topic, который должен быть выбран в ответ.
  - Ожидаемая core directive в body (key term для assert).
- Тест проходит через программный retrieval (`/kb-search` или CLI
  equivalent), не через LLM-judge — deterministic.
- Все 5 pre-push gates зелёные; coverage ≥ 80% на новом коде.
- `efactory-up --agent` после `docker build` + `--reset-claude-state`
  показывает в SessionStart context секцию `## Knowledge Base
  (N topics available)` с TOC.
- Manual smoke: agent в TUI на «построй график АЧХ» — выбирает
  `/plot-ac` через KB hit, не пытается писать свой ngspice-wrapper /
  Grep'ать исходники efactory.
- `/kb-add` создаёт корректный markdown с frontmatter; conflict
  (existing topic) — fail с подсказкой `--force` (или другой
  override, см. Clarify).

## 5. Key Entities

- **`KbEntry`** (domain VO) — `topic: str` (slug, unique),
  `description: str` (1-line summary для TOC), `tags: tuple[str,
  ...]`, `body: str` (markdown), `source: Literal['built-in',
  'host-mutated']`, `added_at: datetime`.
- **`KbIndex`** — `tuple[KbEntry, ...]` (sorted by topic), помогает
  SessionStart hook'у строить TOC.
- **`KbStore`** (outbound port) — `list() -> tuple[KbEntry, ...]`,
  `get(topic) -> KbEntry | None`, `add(entry) -> None`,
  `search(query) -> tuple[KbEntry, ...]` (substring / token match).
- **`FileSystemKbStore`** (adapter) — реализация над
  `/efactory/knowledge-base/` (built-in seed) + `/efactory/.claude/
  knowledge-base/` (host-mutated). Merge с host-wins policy.
- **Frontmatter schema** (yaml):
  ```yaml
  ---
  topic: saturable-spice           # slug, unique
  description: Saturable магнетика в SPICE — XSPICE gyrator-cap
  tags: [spice, magnetics, ngspice, gyrator-cap]
  source: built-in | host-mutated  # auto-set, не trusted от user
  ---
  # Saturable магнетика — XSPICE gyrator-capacitor

  Markdown body с правилом, обоснованием, anti-pattern'ом.
  ```

## 6. Assumptions & Constraints

- **Claude Code retrieval = Read tool**: агент явно читает KB-файлы
  через стандартный `Read` (никаких MCP). SessionStart hook
  показывает TOC для guidance.
- **Размер KB** на горизонте Phase 2-3 — десятки topics × ~1 KB =
  ~50-100 KB. Polnyy load в context не оправдан (соревнуется с user
  project content), TOC + selective Read — правильный paradigm.
- **Grep retrieval достаточен**: на сотнях topics и тысячах body-
  строк plain grep работает быстро. Vector DB — premature
  optimization.
- **Initial seed migration** (DECISIONS.md / CHANGELOG.md / auto-
  memory) — НЕ автоматическая; ручной перенос Vladimir + Гвидо
  curated, что попадёт в built-in KB. T134 даёт infrastructure +
  10 control examples; full migration — follow-up T-NEW.
- **`/kb-add` от агента — без user-confirmation**. Идея: автономный
  агент должен накапливать знания, иначе ценность падает. Защита от
  spam — validation (unique topic, syntax check); reset через
  `--reset-claude-state` доступен.
- **Знания специфичные для конкретного проекта** идут в
  `<PROJECT>/.efactory/decisions/` (расширение существующей T103
  Decision Aggregate), не в global KB. KB — cross-project.
- **Filename layout** (Analyze A1): flat `docker/runtime-agent-
  knowledge-base/<slug>.md`, где `<slug>` — full namespaced string
  с точками (`spice.saturable.md`). Subdirectory layout (`spice/
  saturable.md`) — потенциальный refactor при >30 entries.
- **Token-AND search complexity** (Analyze A2): O(N·M) acceptable
  до ~100 entries; inverted index — follow-up при превышении.
- **Bind-mount layout** (Analyze A3): новая host-side директория
  `$HOME/efactory-state/knowledge-base/` → `/efactory/knowledge-
  base/host-mutated/`. Built-in seed запекается в образ под
  `/efactory/knowledge-base/built-in/`. `--reset-claude-state`
  (T014) расширяется на KB директорию.

## 7. Out of Scope

- **Полная миграция dev-process знаний** в KB (DECISIONS.md /
  CHANGELOG.md / auto-memory / mem0). T134 даёт infrastructure +
  ≥10 seeded entries; migration массива знаний из репо — отдельная
  curation-задача.
- **Vector DB / embeddings / RAG** — premature scale. Markdown +
  grep + Read достаточны.
- **Multi-agent KB** (несколько runtime-агентов делят одну KB,
  consistency, locking). Сейчас один агент на сессию.
- **Voice / GUI для KB** — CLI / slash-команды достаточны.
- **Версионирование KB entries** (history per entry). Если нужно —
  git tracking host-mutated файлов; out of T134 core.
- **Project-specific knowledge** (живёт в `<PROJECT>/.efactory/
  decisions/`, T103).
- **MCP-server для KB** (ADR 2026-05-24 — tool surface = filesystem).

## 8. Phase plan (implementation)

Каждая фаза = одна сессия, отдельный commit (squash в один при merge).

- **Phase A — domain VOs + frontmatter parser.** `KbEntry`
  (Pydantic frozen, `extra='forbid'`), `KbNamespace` helper, parser
  для yaml-frontmatter + body split. Unit-тесты — full coverage,
  no external deps.
- **Phase B — `KbStore` port + `FileSystemKbStore` adapter.**
  Outbound port (Protocol): `list`, `get`, `add`, `search`. Adapter:
  read из built-in + host-mutated, merge с host-wins; `add` пишет
  только в host-mutated; `KbConflictError`. Integration тесты с
  `tmp_path` для обеих директорий.
- **Phase C — SessionStart hook расширение + `efactory-up`
  bind-mount.** `scripts/session_start_hook.py` extended: грузит
  built-in + host-mutated, рендерит TOC grouped by namespace,
  appends к existing project-context block. `efactory-up`: новый
  bind-mount `$HOME/efactory-state/knowledge-base/` → `/efactory/
  knowledge-base/host-mutated/`; `--reset-claude-state` расширен на
  KB директорию (backup в `*.bak-YYYY-MM-DD/`). Integration test —
  hook subprocess с tmp HOME, проверка TOC structure.
- **Phase D — CLI `efactory kb {list,show,add,search}` + 2 slash-
  команды.** Typer sub-app в `app.py` (после `bridge`); тонкий
  wrapper над `KbStore`. Slash-команды `/kb-search <query>` и
  `/kb-add <topic>` в `docker/runtime-agent-commands/`. `build_app`
  signature расширен `kb_store: KbStore`; composition root
  пробрасывает `FileSystemKbStore`. E2e тесты.
- **Phase E — 10 initial seed entries + 10 control-example
  regression test + CHANGELOG/README.** Содержимое seed
  (`docker/runtime-agent-knowledge-base/*.md`): 9 lessons из T131
  (spice.saturable-gyrator, spice.floating-secondary-leak,
  spice.saturation-contribution-metric), T132 (magnetics.pyom-
  leakage-broken, magnetics.interleaving-n-squared, magnetics.pyom-
  bobbin-patch), T133 (fem.2d-planar-zhang-gap, fem.elmer-3d-mumps-
  ceiling, fem.elmer-stranded-coil-loop) + agent.command-routing.
  Regression test (`tests/integration/agent_kb/test_control_
  examples.py`) — 10 testfunctions с (query, expected_topic,
  expected_directive_term) tuples; deterministic через
  `kb_store.search()`.

---

## Clarify (заполняется Гвидо)

### Resolved (с ответами)

Все 11 вопросов разрешены 2026-05-26 ответом Vladimir-а «по
рекомендации» — выбран мой предварительный голос по каждому.

| ID | Решение | Влияние |
|----|---------|---------|
| **Q-A** | (a) Seed `docker/runtime-agent-knowledge-base/`. | Bootstrap pattern T014; KB — runtime-agent config, не shipping data. |
| **Q-B** | (b) Namespaced slug `<namespace>.<name>` (`spice.saturable`, `agent.command-routing`). | TOC groups по namespace (Q-C); prefix-поиск естественный. |
| **Q-C** | (c) Grouped headings (по namespace) + bullets в SessionStart `additionalContext`. | Hook (T016) extension. |
| **Q-D** | (b) Token-AND (whitespace split, все tokens must match). | Predictable, тестируемое без LLM-judge. |
| **Q-E** | (a) Host wins; `--reset-claude-state` (T014) расширяется на KB. | Protects user-contribution от docker upgrade. |
| **Q-F** | (c) Ровно 10 control examples + отдельная **T154** для massive migration. | T134 = infrastructure + acceptance; full curation массивных знаний — отдельная задача. |
| **Q-G** | (a) CLI `efactory kb {list,show,add,search}` обязателен. | Dev-time validation; тонкий Typer wrapper. |
| **Q-H** | (a)+(c) hybrid: agent → host-mutated без confirm; built-in promotion manual через PR. | Autonomous accumulation + quality gate на built-in seed. |
| **Q-I** | (b) Topic `agent.command-routing` (мой пример). | Точнее описывает routing. |
| **Q-J** | (a) Strict Pydantic (`KbEntry` frozen, `extra='forbid'`). | Consistency с slash-команд validation; CI ловит broken entries. |
| **Q-K** | (b) Directory `tests/integration/agent_kb/` (bootstrap/search/add/control_examples). | ~500 LOC — split логичен. |

**Сторонний эффект** — заведена **T154** в BACKLOG (Q-F → c).

---

## Analyze (заполняется Гвидо)

Analyze pass 2026-05-26: 8 issues, **0 Critical**; 3 Warning отражены
в FR/Assumptions; 5 Note — implementation guidance.

### 🔴 Critical — нет

### 🟡 Warning — отражены в spec'е

- **A1. Namespace в slug vs filename.** Q-B даёт slug
  `spice.saturable`, точка в filename'е валидна на Linux/macOS/Windows
  (`spice.saturable.md` — два dot'а ок). Subdirectory layout
  (`spice/saturable.md`) чище для >30 entries, но требует recursive
  scan. **Решение:** flat layout `<slug>.md` сейчас; migration в
  subdirectories — follow-up при >30 entries.
- **A2. `KbStore.search()` token-AND на large bodies — O(N·M).**
  N=entries, M=tokens. На ~50 entries × 2-3 tokens = ~150 substring
  checks per query — приемлемо. **Решение:** acceptable до 100
  entries; при превышении — T-NEW для inverted index.
- **A3. Host-mutated bind-mount требует расширения `efactory-up`.**
  Существующий `$HOME/efactory-state/claude/` → `/efactory/.claude/`;
  параллельно нужен `$HOME/efactory-state/knowledge-base/` →
  `/efactory/knowledge-base/host-mutated/`. Зафиксировано в §6 +
  Phase C scope.

### 🟢 Note — implementation guidance

- **A4. SessionStart hook (T016) backward-compat.** KB-секция
  appended после existing project-context; пустая KB — skip section.
- **A5. `KbStore.add()` writes only host-mutated.** Built-in seed
  read-only runtime; conflict при existing topic → `KbConflictError`
  с `--force` overwrite option.
- **A6. CLI `efactory kb add` + slash-команда `/kb-add`** — обе
  пишут в host-mutated. Built-in mutate'ится только через PR в репо.
- **A7. Frontmatter `source` field auto-set adapter'ом** при read,
  не пользователем. Pydantic `KbEntry.source` — `Literal['built-in',
  'host-mutated']`, но в file отсутствует.
- **A8. Phase plan (5 фаз)** — каждая ≈ 1 сессия = 1 commit на
  ветке, squash в один при merge. См. §8 ниже.
