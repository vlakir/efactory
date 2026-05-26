# Spec: Agent Knowledge Base — persistent KB для runtime-агента efactory

**Статус:** Draft
**Дата создания:** 2026-05-26
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

---

## Clarify (заполняется Гвидо)

### Open questions

**Q-A. Built-in seed location в репо — `docker/runtime-agent-
knowledge-base/` или `data/knowledge-base/`?**

- (a) `docker/runtime-agent-knowledge-base/*.md` — родственно
  `docker/runtime-agent-commands/` (Slash-команды), bootstrap
  механизм тот же.
- (b) `data/knowledge-base/*.md` — родственно `data/templates/`,
  data-side-of-the-house.

Я голосую за **(a)** — KB концептуально часть runtime-agent
configuration (как slash-команды и system prompt), не shipping
data. Bootstrap pattern идентичный T014.

**Q-B. Slug формат для `topic` — kebab-case (`saturable-spice`) или
namespaced (`spice.saturable`)?**

- (a) Flat kebab-case (как slash-команды): `saturable-spice`,
  `floating-secondary-leak`.
- (b) Namespaced dotted: `spice.saturable`, `magnetics.leakage`,
  `scenarios.quick-mapping`.

Я голосую за **(b)** — namespacing помогает агенту orient'ироваться
по группам без external organisation. Поиск по prefix естественный.
Топиков будет >30 после miграции, плоский список становится
труднообозримым.

**Q-C. SessionStart hook injection format — table или bulleted
list?**

- (a) Markdown table (5-7 cols: topic / desc / tags).
- (b) Bulleted list (one line per topic: `- **topic** — desc
  [tags]`).
- (c) Grouped headings (по namespace, если Q-B → b).

Я голосую за **(c)** — group by namespace, headings + bulleted
items. Чище читается агентом, проще scan'ить по теме.

**Q-D. `/kb-search` matching algorithm — substring, token-AND, или
fuzzy?**

- (a) Plain substring (case-insensitive) по body + frontmatter
  description/tags.
- (b) Token-AND: query split'ится whitespace, все tokens должны
  встречаться (анти-fuzzy).
- (c) Lite-fuzzy через difflib или rapidfuzz.

Я голосую за **(b)** — predictable, deterministic, тестируемое.
Fuzzy усложняет regression tests без proven benefit на нашем scale.

**Q-E. Conflict resolution built-in seed vs host-mutated при
рестарте контейнера (новый image versions vs накопленный host
state) — host wins всегда?**

- (a) **Host wins** для существующих topic'ов; новые built-in
  topic'ы добавляются. (Mirror T014 settings.json policy.)
- (b) **Built-in wins** — каждый bootstrap затирает host. Простой,
  но теряет user-contribution'ы.
- (c) **Three-way merge** через git-style (`built-in original`,
  `host`, `built-in new`) — sophisticated, но overhead.

Я голосую за **(a)** — protect user contribution; clean reset
через `--reset-claude-state` (T014 механизм уже есть).

**Q-F. Initial seed contains ровно 10 control examples (T131/T132/
T133 + scenarios), или больше?**

- (a) Exactly 10 (acceptance minimum).
- (b) 10 + best-effort migration из DECISIONS.md / Гвидо auto-
  memory (за время T134 implementation; ~30-50 entries).
- (c) Только 10 + отдельный T-NEW для migration.

Я голосую за **(c)** — T134 core scope = infrastructure +
acceptance. Massive migration knowledge — separate concern (требует
curation discussion с Vladimir-ом по each entry, не auto-portable).

**Q-G. CLI `efactory kb {list,show,add,search}` — обязательный или
МОЖЕТ?**

- (a) Обязательный — для dev-time validation вне runtime контейнера
  (developer может проверить KB content без `docker run`).
- (b) Опциональный — slash-команды + filesystem-direct достаточны.

Я голосую за **(a)** — низкий overhead (тонкий Typer wrapper), но
очень полезен для dev-process (CI-validation, scripted bootstrap).

**Q-H. `/kb-add` от агента — без user-confirmation, или каждый раз
prompt?**

- (a) Без confirmation — autonomous agent сам решает.
- (b) Каждый раз prompt: «agent хочет добавить topic X — да/нет/
  edit».
- (c) Auto-add в quarantine namespace (`unverified.*`), Vladimir
  later promote'ит через CLI.

Я голосую за **(a)** + (c) hybrid: agent пишет напрямую в
`host-mutated` без promotion в built-in seed. Vladimir может затем
review через `efactory kb list --source host-mutated` и portировать
ценное в built-in seed через PR в репо (`docker/runtime-agent-
knowledge-base/`). Promotion — manual, не agent-decision.

**Q-I. Topic-namespace для «typical scenarios mapping» (мой
example) — `scenarios.quick-mapping` или другое?**

- (a) `scenarios.quick-mapping` (per Q-B namespace).
- (b) `agent.command-routing` — более descriptive.
- (c) Один большой topic `scenarios.*` (split на sub-topics: audio,
  power, fem).

Я голосую за **(b)** — `agent.command-routing` точнее отражает что
делает entry. Sub-topics по technical domain — будущие entries по
мере накопления.

**Q-J. Validation level frontmatter — strict (Pydantic) или
permissive (warn-only)?**

- (a) Strict: `KbEntry` Pydantic model с frozen, extra='forbid';
  парсинг fail'ит на bad frontmatter.
- (b) Permissive: warn в SessionStart hook, skip broken entries;
  не блокирует bootstrap.

Я голосую за **(a)** — consistency с slash-команд validation в
`test_runtime_agent_commands.py`. Plus integration test ловит
broken entries в CI до merge.

**Q-K. Где живут acceptance тесты T134 — `tests/integration/test_
agent_kb.py` или dedicated `tests/integration/agent_kb/`?**

- (a) Single file `test_agent_kb.py`.
- (b) Directory `tests/integration/agent_kb/` (по test category:
  bootstrap / search / add / control-examples).

Я голосую за **(b)** — 10 control examples + bootstrap + retrieval
+ writer достаточно для split. Single file будет ~500 LOC.

### Resolved (с ответами)

- ...

---

## Analyze (заполняется Гвидо)

<!-- После ответов на Clarify — pass на противоречия / упущения. -->

- ...
