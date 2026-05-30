# Spec: `bridge edit-and-resim` с автосравнением метрик (до/после)

**Статус:** Analyzed
**Дата создания:** 2026-05-30
**Clarified / Analyzed:** 2026-05-30
**Связанные документы:**
- `specs/T023-measurements/spec.md` (Analyzed, merged) — domain VO
  `GainMeasurement` / `BandwidthMeasurement` / `ThdMeasurement` и use
  cases `measure_{gain,bandwidth,thd}`, которые T021 переиспользует.
- `specs/T022-bridge-sweep/spec.md` (Analyzed, merged) — образец
  use case-агрегатора с metric dispatch и DI измерений.
- `src/application/edit_and_resim.py` — существующий Python use case
  (T004b), который T021 либо расширяет, либо параллельно строит
  второй use case с baseline+after; решение — в Clarify.
- `src/adapters/inbound/cli/app.py` L1681–L1756 (`bridge edit`) —
  pattern атомарного batch edit'а через `SchematicSnapshot`.

---

## 1. Overview

Сегодня цикл «изменил → пересимулировал → понял, стало лучше или
хуже» требует четырёх ручных шагов (`bridge measure` → `bridge edit`
→ `bridge measure` → diff в голове). T021 сворачивает его в одну
команду `bridge edit-and-resim`: agent / разработчик описывает
batch edits и набор метрик, efactory автоматически снимает
baseline до правок, применяет edits, снимает повторное измерение, и
печатает таблицу «до / после / Δ / Δ%». Это финальный шаг
analysis-first ordering Фазы 2 — после T023 (метрики) и T022
(sweep), оба переиспользуются.

## 2. User Stories

efactory — не «обычный» end-user продукт, поэтому формат User Stories
работает через две роли: runtime-агент в `efactory:linux` (primary,
через slash-команды и CLI) и разработчик (secondary, через CLI).

- **Как runtime-агент**, проверяющий гипотезу «увеличить Rk катода
  до 1.5k вместо 1k снизит THD на 6 kHz без потери gain», я хочу
  одним вызовом узнать численную разницу — чтобы не строить вручную
  pipeline из measure→edit→measure→diff и не путаться в before/after
  файлах.
- **Как разработчик-аудиофил**, проектирующий SE-усилитель, я хочу
  быстро прогнать «what-if» эксперимент (например, заменить connect
  трансформатор `OPT_SE_5K_8` на `OPT_SE_3K5_8`) и увидеть, как
  это сказалось на bandwidth и THD@1W — чтобы решить, стоит ли
  углубляться в этом направлении.
- **Как Vladimir, ведущий efactory**, я хочу, чтобы команда давала
  «тёплое» (без шумной телеметрии sweep'а) сравнение для типичного
  one-off изменения — фундамент под будущий interactive design loop
  с LLM (Фаза 3+).

## 3. Functional Requirements

### 3.1. CLI команда

- **ДОЛЖНА:** существовать команда `efactory bridge edit-and-resim
  <project> --schematic <path> --set REF=VALUE [...] --measure
  <metric> [...]`, где `--measure` принимает one-or-many из
  `{gain, bandwidth, thd}`.
- **ДОЛЖНА:** принимать те же edit-flags, что и `bridge edit`
  (`--set REF=VALUE` повторяемый), и переиспользовать существующий
  `application.edit_component_value` + `SchematicSnapshot` для
  атомарного batch.
- **ДОЛЖНА:** для каждой `--measure` принимать те же доп. флаги,
  что и одноимённая `bridge measure` команда (frequency, v_in_peak,
  f_low/f_high, mode, input/output signal, input-source) — единый
  набор флагов работает для всех выбранных метрик (если метрика не
  использует флаг — игнорирует его, без warning'а).
- **МОЖЕТ:** поддерживать `--output text|json` (как в `bridge measure`
  / `bridge_sweep`).
- **НЕ ДОЛЖНА:** делать собственные SPICE-измерения; всё через DI
  существующих use cases `measure_{gain,bandwidth,thd}` (T023).
- **НЕ ДОЛЖНА:** поддерживать sweep по параметру — это T022.

### 3.2. Use case-агрегатор

- **ДОЛЖНА:** существовать функция `edit_and_resim_with_delta(...)`
  (или аналогичное имя — финализируется в Phase A) в
  `src/application/`, dispatch'ащая измерения и собирающая дельту.
  Decision «extend `edit_and_resim` vs new use case» — в Clarify.
- **ДОЛЖНА:** последовательность: (1) baseline measure × N (по
  выбранным метрикам), (2) `SchematicSnapshot` + batch edits,
  (3) re-measure × N, (4) собрать `MeasurementDelta` × N.
- **ДОЛЖНА:** failure baseline measure → exit без edits (нечего
  откатывать); failure edit → SchematicSnapshot rollback,
  пропущенные `after`-измерения помечаются как `failed`; failure
  after measure → schematic уже изменён (rollback не делается),
  user видит `before` + сообщение об ошибке. Детали — в Clarify.

### 3.3. Domain VO

- **ДОЛЖНА:** появиться domain VO `MeasurementDelta` (или набор
  per-metric VO) с полями `before`, `after`, `delta_absolute`,
  `delta_relative_percent`, плюс metric-specific контекст (какое
  именно поле сравнивалось — `gain_db`, `bandwidth_hz`,
  `thd_percent`).
- **МОЖЕТ:** хранить опциональное `failed_reason: str | None` для
  случаев, когда after measure упало.

### 3.4. Renderer

- **ДОЛЖНА:** в режиме `--output text` показывать таблицу со
  столбцами: metric / before / after / Δ / Δ% — выровненную
  plain-text (стиль T022 sweep table renderer).
- **ДОЛЖНА:** в `--output json` отдавать машинно-читаемый dump
  для programmatic consumers (фундамент будущего T032 vision-
  валидации).
- **МОЖЕТ:** показывать направление (`↑` / `↓` / `=`) — UX-косметика.

### 3.5. Slash-команда

- **ДОЛЖНА:** появиться slash-команда `/edit-and-resim` (имя
  финализируется в Clarify) в `docker/runtime-agent-commands/` —
  hyphenated flat per T014 A1.
- **ДОЛЖНА:** покрыться KB sync Уровни 1+2:
  - mapping `agent.command-routing` — фразы вида «измени R5 и
    проверь, как изменилась полоса» → `/edit-and-resim`.
  - deterministic regression test в
    `tests/integration/agent_kb/test_control_examples.py`.

## 4. Success Criteria

1. **Acceptance из BACKLOG L810 выполнен:** после изменения схемы
   выводится дельта по ключевым метрикам (gain, bandwidth, THD).
2. **End-to-end demo на `se-amp-demo`:** последовательность
   ```
   /sim-run op
   /edit-and-resim --set R5=2k --measure gain --measure thd \
                   --frequency 1k --v-in-peak 0.1
   ```
   возвращает таблицу «до / после / Δ / Δ%» по обеим метрикам
   без ручного редактирования файлов.
3. **Хирургически чистый pre-push:** `ruff check`, `ruff format
   --check`, `mypy src`, `pytest` все зелёные; coverage не упал
   ниже текущего baseline (~84.7%).
4. **Use case покрыт тестами TDD-стилем:** domain VO (frozen,
   validators), use case-агрегатор (mock simulator + real
   NetlistEditor), CLI (Typer-runner), e2e (real ngspice
   на voltage divider или mini-схеме).
5. **KB sync Уровни 1+2 done:** `agent.command-routing` обновлён,
   regression test зелёный.
6. **Один PR — один коммит** с self-review checklist'ом
   (scope/архитектура/код/линтеры/документация/соглашения/
   безопасность).

## 5. Key Entities

- **`MeasurementDelta`** (domain VO, frozen Pydantic) — обёртка над
  парой `(before, after)` для одной метрики; источник «дельты»
  правды. Per-metric или union — решается в Clarify.
- **`EditAndResimReport`** (domain VO или application DTO,
  финализируется в Phase A) — агрегат: edits applied, список
  `MeasurementDelta`, схема-файл, project name. То, что serializer
  превращает в JSON и renderer — в таблицу.
- **`SchematicSnapshot`** (уже существует) — context-manager,
  гарантирует атомарность batch edits; T021 переиспользует без
  изменений.
- **`measure_{gain,bandwidth,thd}`** (T023) — каждый dispatch'ится
  по `--measure <kind>` через тот же шаблон, что в `bridge_sweep`
  metric dispatch (T022).

## 6. Assumptions & Constraints

- **Pre-reqs готовы:** T023 (measure) + T022 (sweep) merged;
  `edit_component_value` + `SchematicSnapshot` стабильны (T004b).
- **Один project root** на запуск; project resolve через
  `ProjectManifestRepository` (как и `bridge edit`).
- **Один schematic-файл** на запуск (no multi-sheet). Это
  ограничение унаследовано от `bridge edit` / `bridge measure` —
  снимется отдельной задачей.
- **`design_to_sim` идемпотентен** в рамках одной команды: одна
  схема → одна симуляция; baseline и after — независимые subprocess
  ngspice run'ы (как в T022).
- **Сравнение в numeric space:** delta = after − before (absolute) и
  (after − before)/before × 100% (relative). Edge case `before == 0`
  для relative — в Clarify (NaN / `inf` / suppress).
- **Async-стек** — use case `async def`, как и все остальные в
  efactory.
- **Detection терминала** не делаем — output либо `text`, либо
  `json` (как в `bridge measure` / `bridge_sweep`).

## 7. Out of Scope

- **Sweep по параметру / Cartesian product** — это T022. Здесь
  только one-shot edit (1 set of edits → 1 after-measure).
- **Phase margin** — T153 (ждёт feedback-фикстуру), не входит в
  стандартный набор метрик T021.
- **Multi-sheet / hierarchical schematic** — ограничение из
  `bridge edit`.
- **Визуализация дельты графиком** — может пригодиться позже, но
  здесь только tabular output. ASCII-плот dispatch'ить не
  стоит — T024 (plot) рисует AC/TRAN traces, а не bar charts метрик.
- **Persistence истории сравнений** — `SimResult` writer уже
  кладёт `metrics` per measure (T016 pattern); делать ли запись
  про дельту отдельно — решим в Clarify (по умолчанию: нет,
  consumer всегда может вычислить дельту из двух последовательных
  `SimResult`).
- **Schematic input → design-to-measure pipeline** (только `.cir`
  / pre-rendered netlist) — это ограничение T023 mexico,
  унаследовано.
- **Calibration loop для THD target power** — T131 (ADR), не
  входит в стандартный workflow T021.
- **Automatic rollback при «дельта в плохую сторону»** — exit-код
  отражает технический успех pipeline, не направление дельты.
  Agent / user сам решает, считается ли результат успехом.

---

## Clarify (заполняется Claude)

### Resolved (с ответами Vladimir-а 2026-05-30)

10 вопросов сформулированы Claude, 9 закрыты «по рекомендации»,
1 (Q-J) — явное override Vladimir-ом (smoke внутри контейнера
включить в этот PR).

- **Q-A → b. Новый use case `edit_and_resim_with_delta` рядом со
  старым `edit_and_resim`.** Сигнатуры расходятся (новый принимает
  list of metric specs, не `AnalysisSpec`); DI-список отличается
  (нужен `NetlistEditor` для `ensure_ac_modifier`). Старый
  T004b-use-case не трогаем — оставляем для callers, которые
  использует `bridge sim-run`-сценарии и `design_to_sim` pipeline.
- **Q-B → a. CLI команда `bridge edit-and-resim`, повторяемый
  `--measure`.** 1-к-1 соответствие с use case'ом; hyphenated flat
  per T014 A1.
- **Q-C → a. Единый плоский набор флагов на все метрики.** Паттерн
  T022 sweep dispatch'а. Метрики берут что нужно; required-validation
  делегируется самим `measure_*` use cases (там уже всё проверено).
- **Q-D → a. `delta_relative_percent: float | None`; при `before
  == 0` → `None`; renderer показывает `—`.** Optional поле
  безопаснее `inf`/`nan` в JSON.
- **Q-E → a. Edit'ы commit'нуты, after-measure failure помечается
  `failed_reason: str | None`; exit-код = 1.** Edit'ы — часть
  явно запрошенного результата; failure — отдельный сигнал в
  output. CI-friendly exit.
- **Q-F → a. Три per-metric VO: `GainDelta`, `BandwidthDelta`,
  `ThdDelta`.** Phase-coherent с T023 (3 independent VO без union).
- **Q-G → a. Slash-команда `/edit-and-resim`.** 1-к-1 mapping с CLI;
  hyphenated flat.
- **Q-H → b. JSON output содержит full before / after measurements
  + delta + edits + project metadata.** Для programmatic consumers
  и будущего T032.
- **Q-I → a. Только обычные `SimResult` writer от before/after
  measure (как у `bridge measure`).** Никакого нового sim-result
  kind для дельты — consumer вычисляет дельту из двух последовательных
  `SimResult` если нужно. Cheapest и совместимо с T157 (filesystem
  SSOT).
- **Q-J → b (override Vladimir-а). KB Уровни 1+2 + Уровень 3 full
  smoke в контейнере — всё в этом PR.** Перед merge — `docker build`
  и headless `claude -p` smoke с T021 scenario. Уровни 1+2 — fast
  гейты pre-push.

---

## Analyze (заполняется Claude)

Claude перечитывает Clarified spec и ищет противоречия, пробелы,
технические невозможности. Помечает 🔴 Critical / 🟡 Warning / 🟢 Note.

### 🔴 Critical (фиксим до начала реализации)

**A1. `measure_*` use cases требуют разных подходов к ngspice run-у;
batch вызов «3 metrics × 2 (before/after) = 6 ngspice'ов» —
доказуемо неоптимально, но это accepted cost.**

Каждая `measure_{gain,bandwidth,thd}` поднимает свой ngspice
subprocess (AC sweep для gain-small, TRAN для gain-large/thd, AC
sweep для bandwidth). В worst case T021 с `--measure
gain,bandwidth,thd` запустит 6 ngspice run'ов (3 × before/after).
Это inherently slow (5-30 секунд per run на типичной схеме).
**Resolution in-spec:** не оптимизировать (no fusion, no caching);
T022 sweep ровно с тем же ограничением merged. Опциональный
параметр `--parallel` оставим backlog'у. Документировать в
docstring use case'а и `--help` команды.

**A2. `edit_and_resim` (T004b) + новый use case оба используют
`edit_component_value`, но `SchematicSnapshot` сейчас живёт только
в CLI слое (`bridge edit` command), не в use case'е.**

Проверил: `src/application/edit_and_resim.py` НЕ использует
`SchematicSnapshot` — он просто циклит `edit_component_value`
без rollback'а (docstring явно говорит «failure в середине edits
оставляет schematic в частично-изменённом состоянии»). T021 use
case ДОЛЖЕН использовать `SchematicSnapshot` (это в Q-E резолюции
неявно). **Resolution in-spec:** новый `edit_and_resim_with_delta`
оборачивает edit-loop в `SchematicSnapshot`, как делает `bridge
edit` command. После Phase A pull-up `SchematicSnapshot` в
application layer (если он там ещё не лежит) — детали в Phase A.
Параллельный pull-up для старого `edit_and_resim` — out of scope
(может быть отдельной задачей).

### 🟡 Warning (обсуждаем, возможно фиксим)

**W1. `measure_gain` в режиме `small` требует `ensure_ac_modifier`
на schematic V-source — это side effect на netlist'е, не на
schematic-файле.**

`ensure_ac_modifier` (T023 NetlistEditor extension) работает на
сгенерированном `.cir`, не на `.kicad_sch`. После `design_to_sim`
получаем netlist, его modify'им, ngspice ест. Для T021 это значит:
для baseline gain-small → design_to_netlist → ensure_ac_modifier →
ngspice (это уже делает `measure_gain`); for after — то же самое
с пересгенерированным netlist'ом. Никаких stale modifier'ов, потому
что каждый design_to_netlist regen'ит. **Resolution:** no fix —
текущая семантика `measure_gain` correct'ная. Просто внимательно
не закешировать netlist между before/after (каждый раз свежий
design_to_netlist).

**W2. JSON output `H → b` (полные measurement объекты) — Pydantic
serialization unicode-флагов / Decimal'а / NaN.**

`GainMeasurement` / `BandwidthMeasurement` / `ThdMeasurement` —
pure float fields, `Literal` enums. Pydantic v2 `.model_dump_json()`
их сериализует чисто. Проблема — только `delta_relative_percent:
float | None`; `None` → JSON `null`, ok. **Resolution:** explicit
`.model_dump_json(indent=2)` для pretty JSON; tests на serializable
round-trip.

**W3. CLI command name `bridge edit-and-resim` — slug content
«edit-and-resim», но в Python-модуле use case называется
`edit_and_resim_with_delta` (длинный).**

Не нужно strict matching CLI ↔ use case имени. Расхождение есть
и в T022 (`bridge sweep` ↔ `bridge_sweep` use case) — это ok.
**Resolution:** оставляем как есть. CLI имя — для UX, Python имя —
для разработчика.

**W4. Edit batch и измерение не атомарны — если after-measure
завершится failure, schematic уже изменён (Q-E → a).**

Резолюция Q-E явно говорит «не откатываем». Risk: user не понимает
почему schematic изменён, но дельты нет. **Resolution:** text
renderer явно говорит `Edit'ы applied, после-измерения упали:
<reason>. Schematic в состоянии после edit'ов; rollback не
выполнен.` Это явное предупреждение, не silent failure.

**W5. Hard cap для одной команды (no max-edits limit) vs T022's
MAX_COMBINATIONS=100.**

T022 имеет soft warn 20 / hard cap 100 на N combinations. T021 —
one-shot, N edits не explodes (typical 1-5 edits), но agent может
накопить 20+ — это нарушает «small batch» дух команды. **Resolution:**
soft warn после 10 edits в stderr (`>10 edits in single command —
consider splitting; complex what-if often easier to debug step by
step`). No hard cap (overkill для one-shot).

### 🟢 Note (к сведению)

**N1. Phase margin (T153) не входит в standard set.** Если у agent'а
гипотеза о feedback loop'е — `bridge edit` + `bridge measure
phase-margin` отдельно после T153 merge. Документировать в
`--help`.

**N2. `--output text` taborlu output — без `tabulate` зависимости
(per T022 A5 decision).** Plain-text alignment через `f-string`
+ str-width.

**N3. Acceptance test data — voltage divider (1:2) + simple RC
filter** (минимум для покрытия gain/bandwidth/thd одновременно).
e2e тесты в `tests/integration/cli/` следуют паттерну T023 e2e.

**N4. KB control example — фраза вида «измени R5 на 2k и проверь,
как изменился gain» → expected_topic
`agent.command-routing`, expected_directive_keyword
`/edit-and-resim`.** Будет в `test_control_examples.py` параметризованным
case'ом.

**N5. CHANGELOG entry — verbose на стиль T022/T023.** Включает:
DTO, use case, CLI, slash, KB sync, tests breakdown, coverage,
out of scope (T153, sweep, multi-sheet).

**N6. Если after-measure упало и при этом был не один failure а
несколько (например, AC sweep упал → bandwidth & gain-small оба
failed) — каждая metric получает свой `failed_reason`.** Renderer
печатает per-row.

**N7. Phase D (Уровень 3 smoke в контейнере) добавляет ~30 минут
overhead к закрытию задачи; это явно принято Vladimir-ом
(override Q-J).**

### Резюме Analyze

- 0 Critical после in-spec resolution (A1 — accepted, A2 — fix
  путём `SchematicSnapshot` в use case).
- 5 Warning, все с in-spec resolution (W1-W5).
- 7 Note для guidance в imp фазах.

Spec готова к implementation. Фазы реализации — A/B/C/D/E,
см. отдельное сообщение Vladimir-у.
