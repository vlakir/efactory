# Spec: `bridge measure phase-margin` — запас по фазе для feedback-схем

**Статус:** Clarified
**Дата создания:** 2026-05-31
**Clarify прошёл:** 2026-05-31 (13 вопросов; 9 «по рекомендации» +
4 расширения scope — Q2/Q3/Q11/Q12 — осознанные, ради
полнофункциональной реализации, не MVP).
**Spin-off от:** T023 Clarify (2026-05-26) — phase margin вынесен
отдельной задачей.
**Размер задачи:** **большая** — multi-week milestone. Включает два
new MAJOR subsystem'а (multi-injection abstraction + netlist graph
analyzer для feedback auto-detect) + T021 extension. Два ADR'а в
`DECISIONS.md` (injection-method strategy; netlist graph analyzer).
**Связанные документы:**
- `BOARD.md → Doing → T153` (BACKLOG-запись закрыта 2026-05-31,
  закомменчена с pointer на BOARD).
- `specs/T023-measurements/spec.md` — родительская инфраструктура
  `bridge measure {gain,bandwidth,thd}`; этот спек переиспользует тот же
  паттерн (use case + frozen VO + sub-Typer subcommand + slash + KB).
- `specs/T021-edit-and-resim-delta/spec.md` — недавний аналог как
  «полный ритуал» для bridge-задачи.
- `domain/simulation.py` — `AcAnalysis` / `AcSweep` готовы;
  `NgspiceNetlistEditor` — port для in-place правки netlist'а (T021).
- `data/templates/se-amp/` — единственная существующая фикстура; T153
  Phase A создаёт **новую** feedback-фикстуру (триггер из BACKLOG).

---

## 1. Overview

`efactory bridge measure phase-margin <NETLIST>` — полнофункциональный
«измеритель» **запаса по фазе** (phase margin, PM) и сопровождающей
точки **unity-gain crossover** для схем с замкнутой петлёй обратной
связи (NFB). Возвращает `PhaseMarginMeasurement` VO (margin_deg,
crossover_hz, optional gain_margin_db / phase_crossover_hz,
stability classification, full sweep dataset).

**Полнофункциональность** включает (отличия от изначального MVP-видения,
зафиксированные в Clarify 2026-05-31):

- **Четыре loop-injection methodologies** (Q2=c): Middlebrook voltage,
  Middlebrook current, Tian's method (1998), Rosenstark double-injection.
  Strategy pattern с per-method validation reference circuits.
- **Heuristic auto-detect feedback break node** (Q3=b) — netlist graph
  analyzer ищет cycle'ы в circuit graph, identification forward/feedback
  paths по element-type heuristics, confidence scoring + confirmation
  prompt. Explicit `--loop-break-node` остаётся как override.
- **T021 `edit_and_resim_with_delta` extension** (Q11=a):
  `--measure phase-margin` метрика с обязательным контекстным
  `--loop-break-node` (или auto-detect).
- **Level 3 smoke в `efactory:linux` obligatory** (Q12=b) — Phase E
  acceptance gate.

**Зачем отдельно от T023.** Phase margin принципиально отличается от
gain / bandwidth / THD: эти меряются как-есть на netlist'е без
вмешательства в топологию, а phase margin требует **разрыва loop'а** и
**инжекции тестового сигнала** в точку разрыва. Open-loop SE/PP
усилители (основной use case Фазы 2) phase margin не имеют —
концепция применима только к схемам с явным feedback path'ом. Поэтому:

1. Триггер задачи (BACKLOG, 2026-05-26): «появление первой feedback-
   схемы в `data/templates/`». Этот триггер закрывается **внутри**
   T153 Phase A (новая фикстура — часть scope).
2. Loop-cutting требует caller-side hint'а на break node + дисциплины
   inject/probe — отдельный CLI flag (`--loop-break-node`) и отдельная
   валидация, не вписываются в general measure-обвязку T023.
3. PM/GM — частая пара (gain margin как «бонус»); семантически связаны.

## 2. Сценарии использования

> Проект без явных «ролей» — efactory работает с агентом и
> Разработчиком через CLI / chat.

- **Сценарий A (Agent / NFB stability check).** Агент построил NFB
  tube amp (cathode feedback или global voltage feedback из вторички
  OPT в катод первого каскада). Хочет проверить stability запас.
  Вызывает `efactory bridge measure phase-margin <NETLIST>
  --loop-break-node <node>` → получает `(margin_deg, crossover_hz)`.
  Decisional output: «PM = 47° на 18 kHz — устойчиво с запасом» или
  «PM = 8° — на грани oscillation, увеличь Rfb или добавь
  compensation cap».

- **Сценарий B (Designer / op-amp filter).** Разработчик хочет
  проверить filter с активным op-amp'ом перед записью в schematic
  template. Тот же CLI, входной netlist — op-amp inverting + RC.

- **Сценарий C (T021/T022 prerequisite, programmatic).** Use case
  `edit_and_resim_with_delta` теоретически может включить
  phase-margin в свой набор метрик (Q11). T022 sweep — параметр vs
  PM по диапазону.

- **Сценарий D (Out-of-scope reminder).** Open-loop SE/PP amp без
  feedback path'а — caller получает явный exit с сообщением «schema
  contains no detectable feedback loop / break-node not found in
  netlist» и кодом 2.

## 3. Functional Requirements

### Базовые

- **ДОЛЖНА** предоставить use case `measure_phase_margin` в
  `application/` и CLI subcommand `bridge measure phase-margin` под
  существующим `bridge measure` sub-Typer (тот же путь, что T023
  gain/bandwidth/thd).
- **ДОЛЖНА** возвращать frozen Pydantic VO `PhaseMarginMeasurement` с
  полями `margin_deg: float`, `crossover_hz: float`,
  `measured_at_node: str`, `injection_method: Literal["middlebrook",
  ...]` (см. Q2). **МОЖЕТ** также возвращать `gain_margin_db:
  float | None` и `phase_crossover_hz: float | None` (Q1).
- **ДОЛЖНА** опираться на существующий `Simulator` port + ngspice
  AC analysis — никаких новых subprocess wrappers.
- **ДОЛЖНА** опционально писать `SimResult` через
  `SimResultsRepository` (тот же паттерн T023 Q9).
  `AnalysisType` расширяется `phase-margin`.

### Loop break — explicit или auto-detect

- **ДОЛЖНА** поддерживать **два способа** определить break node
  (Q3=b):
  - **Explicit override:** `--loop-break-node <node>` — имя SPICE-нета,
    в котором будет применена инжекция. Никаких heuristics, прямой
    приказ caller'у.
  - **Heuristic auto-detect (default):** при отсутствии флага tool
    строит граф netlist'а, ищет cycle'ы, классифицирует пути на
    forward / feedback по element-type heuristics, выбирает наиболее
    вероятный break node + рассчитывает confidence score.
- **ДОЛЖНА** при auto-detect выдавать **confirmation prompt** в text
  output:
  - В interactive TTY-режиме (`stdin.isatty()`) — печатать «detected
    break at node `xyz` (confidence X%). Continue? [Y/n]» и ждать
    ответа. На non-tty (CI, agent CLI) — auto-accept если
    confidence ≥ threshold (default 80%), иначе exit 2 + actionable
    error «auto-detect confidence below threshold, please pass
    --loop-break-node explicitly».
- **ДОЛЖНА** иметь флаг `--no-confirm` для skip confirmation в
  interactive TTY (полезно для batch scripts).
- **ДОЛЖНА** иметь флаг `--confidence-threshold <0..1>` для override
  default (Q3 → b implementation note).
- **ДОЛЖНА** обнаруживать missing node при explicit override: если
  `--loop-break-node` не найден среди нодов netlist'а → exit 2 +
  actionable error «node `xyz` not found; available nodes: <list>».
- **ДОЛЖНА** обнаруживать «no feedback loop found» при auto-detect:
  если circuit graph не содержит cycle'ов с активным элементом →
  exit 2 + message «no feedback loop detected in circuit; if loop
  exists, please pass --loop-break-node explicitly».

### Injection methodology (strategy pattern)

- **ДОЛЖНА** реализовать **четыре** injection methods (Q2=c) через
  strategy pattern (per-method `InjectionStrategy` ABC):
  1. **`middlebrook_voltage`** (default): один AC sweep с voltage
     source insertion. `Vinj N_inj N_break AC 1 0` + node split;
     `T(jω) = -V(reverse) / V(forward)`. Validation reference: simple
     op-amp inverting amp (analytical PM по GBW & feedback ratio).
  2. **`middlebrook_current`**: один AC sweep с current source
     insertion. `Iinj N_break N_inj AC 1 0`; `T(jω) = -I(reverse) /
     I(forward)`. Применяется для high-impedance break point'ов
     (current-mode loops). Validation reference: same op-amp setup
     для cross-check.
  3. **`tian`** (Michael Tian, IEEE TCAS 1998): два sweep'а —
     voltage injection даёт `T_v(jω)` и current injection даёт
     `T_i(jω)` в одной точке; combined `T(jω) = (T_v·T_i +
     T_v + T_i) / (T_v·T_i - 1) · 0.5` (точная formula — в
     Phase B Implementation Notes ADR'а). Самый точный для arbitrary
     impedance break point'ов. Validation reference: transimpedance
     amplifier setup с известным reference PM.
  4. **`double_rosenstark`** (Rosenstark 1974): два sweep'а с разными
     source positions через linear combination — robust к loading
     effects. Validation reference: cascaded feedback с loading.
- **ДОЛЖНА** иметь CLI flag `--injection-method
  {middlebrook-voltage,middlebrook-current,tian,double-rosenstark}`
  (default = `middlebrook-voltage`).
- **ДОЛЖНА** делать patching netlist'а **без мутации исходного
  файла** — патч живёт во временном `.cir` (T021 уже использует
  `NgspiceNetlistEditor` именно так). Strategy получает `netlist_text`,
  возвращает patched `netlist_text` + список probe-нодов.
- **ДОЛЖНА** в VO сохранять `injection_method: Literal[...]` для
  audit; json output включает full strategy parameters (probe nodes,
  source ratings).
- **ДОЛЖНА** strategy implementation выделить в **отдельный ADR**
  (`DECISIONS.md`) — обоснование выбора четырёх methods, math
  derivations, references.

### Crossover detection

- **ДОЛЖНА** запускать AC sweep `dec` по диапазону `[--f-low,
  --f-high]` с default'ами `(1.0, 1e6)` (audio + headroom) и
  `--points-per-decade <N>` (default 100, как в стандартном ngspice
  `.ac dec 100 ...`).
- **ДОЛЖНА** искать **gain crossover** (unity-gain точка, `|T| = 0
  dB`) интерполяцией между двумя соседними sample points: где
  `20*log10(|T_i|) ≥ 0 > 20*log10(|T_{i+1}|)` — линейная
  интерполяция по `log10(f)` и `dB`. Phase в точке crossover —
  линейная интерполяция unwrapped phase по `log10(f)`.
- **ДОЛЖНА** возвращать `margin_deg = 180.0 + phase_at_crossover_deg`
  (стандартная convention: positive = stable, ≤ 0 = unstable). См.
  Q4 про convention.
- **ДОЛЖНА** обрабатывать edge cases:
  - **No crossover (gain всегда < 1)**: exit 2 + сообщение «loop gain
    below unity over swept band; nothing to measure — feedback may
    already be heavily attenuated» (Q5 → a).
  - **Multiple crossovers**: брать **lowest-frequency crossover** где
    fall-через-0dB (gain goes from > 1 to < 1); это «main»
    crossover. В json output — full list (Q5 → b). Soft-warn в
    stderr.
  - **Gain всегда > 1 в свеппе**: расширить `--f-high` —  actionable
    error с подсказкой (Q5 → c).

### CLI

- **ДОЛЖНА** иметь stable интерфейс:
  ```
  bridge measure phase-margin <NETLIST>
      [--loop-break-node <node>]   # default: heuristic auto-detect
      [--confidence-threshold 0.8]
      [--no-confirm]
      [--injection-method {middlebrook-voltage,middlebrook-current,tian,double-rosenstark}]
      [--with-gain-margin]
      [--f-low <Hz>] [--f-high <Hz>] [--points-per-decade <N>]
      [--save-result] [--results-dir <path>]
      [--output {text,json}]
  ```
- **ДОЛЖНА** соблюдать общий `_resolve_netlist_path` helper из T161
  (defensive guard на empty/missing NETLIST).
- **ДОЛЖНА** иметь human-readable text renderer (aligned table:
  Metric / Value / Unit + stability classification tag) и json
  renderer (полный VO + sweep meta + auto-detect graph analysis
  details при default mode).

### T021 `edit_and_resim_with_delta` extension (Q11=a)

- **ДОЛЖНА** расширить T021 use case + CLI + slash, добавив
  `phase-margin` как четвёртую метрику в `--measure {gain,bandwidth,
  thd,phase-margin}`.
- **ДОЛЖНА** ввести новый frozen Pydantic VO `PhaseMarginDelta`
  (Phase-coherent с `GainDelta` / `BandwidthDelta` / `ThdDelta` из
  T021 без union'а): `before`, `after`, `delta_absolute`,
  `delta_relative_percent`, `failed_reason`. Validator
  `after==None ⇔ failed_reason set`.
- **ДОЛЖНА** при `--measure phase-margin` принимать опциональный
  `--loop-break-node` (default → auto-detect, same as standalone).
- **ДОЛЖНА** обновить `/edit-and-resim` slash docs + KB
  `agent.command-routing` table — phase-margin как доступный
  metric kind.
- **ДОЛЖНА** обновить text renderer T021 — table widening на
  PhaseMarginDelta (показывать margin_deg и crossover_hz).
- **ДОЛЖНА** обновить json renderer T021 — полное PhaseMarginDelta
  VO.

### Slash + KB

- **ДОЛЖНА** добавить `/measure-phase-margin` slash в
  `docker/runtime-agent-commands/` (hyphenated flat, T014 A1).
- **ДОЛЖНА** обновить KB Level 1 (`agent.command-routing` mapping
  table: «как proverить стабильность» / «запас по фазе» →
  `/measure-phase-margin`).
- **ДОЛЖНА** добавить KB Level 2 deterministic regression case в
  `tests/integration/agent_kb/test_control_examples.py`.
- **МОЖЕТ** Level 3 smoke в `efactory:linux` — рекомендован, но
  не gate (зависит от Clarify Q12).

### НЕ ДОЛЖНА

- НЕ должна делать **compensation suggestion** (это T029/T032 domain
  — beautifier / vision LLM advisor).
- НЕ должна делать **multi-loop decomposition** (inner-outer loops
  separation в multi-feedback circuit'е). Tool возвращает PM
  единого loop'а, выбранного explicit или auto-detect; разделение
  на independent loops — future task.
- НЕ должна делать **closed-loop transient stability check** (step
  response ringing) — отдельная задача, future.
- НЕ должна делать **schematic-side break point markup** (KiCad
  property hint типа `feedback_break=true` на wire) — out of scope,
  возможный follow-up.
- НЕ должна делать **ML-trained heuristics** для auto-detect (graph
  classification через trained model). Heuristics rule-based на
  element-type metadata.

## 4. Success Criteria

- **Functional accuracy** (per injection method):
  - Reference circuit для каждого из 4 methods даёт PM в пределах
    **±2°** от аналитической / cross-validated reference.
  - Crossover frequency — ±5%.
  - На Phase A feedback-фикстуре (NFB SE tube amp) все четыре
    methods дают cross-consistent PM (max разброс между methods
    ±3°). Reference — KiCad GUI run, Vladimir validates перед merge.
- **Auto-detect accuracy**:
  - На Phase A фикстуре + op-amp inverting fixture (если добавим
    как secondary) auto-detect находит break node с confidence
    ≥ 95% и совпадает с ручным выбором.
  - На open-loop SE-amp (`data/templates/se-amp`) — exit 2 + «no
    feedback loop detected».
  - Confusable cases (cathode bypass cap, decoupling cap) — не
    путаются с feedback path.
- **CLI defensive**:
  - Explicit `--loop-break-node` указывает на несуществующий node →
    exit 2 + actionable message.
  - Empty / nonexistent NETLIST → T161 helper срабатывает (exit 2).
  - Auto-detect confidence ниже threshold в non-TTY → exit 2 +
    actionable message.
- **T021 integration**:
  - `bridge edit-and-resim --measure phase-margin` работает на Phase
    A фикстуре, выдаёт PhaseMarginDelta до/после edit'а.
  - Existing T021 metrics (gain/bandwidth/thd) не сломаны (regression
    suite T021 проходит).
- **Quality gates** (4 обязательных перед push):
  - `uv run ruff check .` — 0 ошибок.
  - `uv run ruff format --check .` — clean.
  - `uv run mypy src tests` — 0 ошибок.
  - `uv run pytest` — 0 fails, coverage ≥ 80% на `src/`.
- **Test surface** (расширенная):
  - **Domain**: `PhaseMarginMeasurement` VO (frozen, validators,
    classmethods); `PhaseMarginDelta` VO (T021 family); `InjectionStrategy`
    ABC + 4 concrete impls; `FeedbackCycle` / `LoopGraphAnalyzer`
    domain types. ≈40-50 тестов.
  - **Use case unit**: `measure_phase_margin` happy path + edge
    cases × 4 injection methods × auto-detect/explicit branches.
    ≈40-60 тестов.
  - **Graph analyzer**: parsing → cycle detection → forward/feedback
    classification → confidence на изолированных фикстурах (RC, op-amp
    NFB, tube NFB, multi-loop). ≈20-30 тестов.
  - **CLI e2e** на реальном ngspice: 4 injection methods × happy
    paths + auto-detect TTY behavior + missing node + no crossover +
    json output. ≈20-30 тестов.
  - **T021 extension**: `edit_and_resim_with_delta` use case с
    phase-margin metric + delta computation + CLI integration.
    ≈15-20 тестов.
  - **Renderer**: text aligned (4 methods × stability tags) + json
    (full VO + sweep dataset). ≈10-15 тестов.
  - **Slash + KB**: 2 parametrized regression cases
    (`/measure-phase-margin` + `/edit-and-resim phase-margin`).
- **Level 3 smoke** (Q12=b, **obligatory**):
  - `efactory:linux` контейнер: 6+ scenarios (default auto-detect +
    explicit + 4 methods cross-validation + T021 integration +
    open-loop error case).
  - Acceptance: agent правильно выбирает команды через KB, не
    изобретает велосипеды.
- **DECISIONS.md ADR'ы**:
  - **ADR-T153a** (`injection-method strategy`): обоснование 4
    methods, math derivations, references (Middlebrook 1975, Tian
    1998, Rosenstark 1974).
  - **ADR-T153b** (`netlist graph analyzer`): rationale, algorithm
    (cycle detection + forward/feedback heuristics), confidence
    scoring, integration with `NgspiceNetlistEditor`.

## 5. Key Entities

### Domain VO

- **`PhaseMarginMeasurement`** (frozen Pydantic VO):
  - `margin_deg: float` — PM в градусах, `180° + phase_at_crossover`.
  - `crossover_hz: float` — частота unity-gain crossover.
  - `measured_at_node: str` — имя ноды, в которой применён injection.
  - `injection_method: Literal["middlebrook_voltage",
    "middlebrook_current", "tian", "double_rosenstark"]`.
  - `stability_class: Literal["high", "adequate", "marginal",
    "risky"]` (Q10=b): high > 60°, 45-60° adequate, 30-45° marginal,
    ≤ 30° risky.
  - `gain_margin_db: float | None` (Q1=c, опционально с
    `--with-gain-margin`).
  - `phase_crossover_hz: float | None`.
  - `extra_crossovers_hz: list[float]` (default `[]`) — multi-
    crossover informational list.
  - `sweep_dataset: AcSweep | None` (Q9=b — `--save-result` сохраняет
    full sweep; default `None` если save-result не запрошен; для VO
    сериализации json renderer выводит compact dataset).
  - `auto_detect_info: AutoDetectInfo | None` — если был auto-detect,
    зафиксировать confidence + alternative candidates.
  - Validators: `margin_deg ∈ [-180, 360]` (sanity); `crossover_hz >
    0`; NaN forbidden; `stability_class` derived consistent с
    `margin_deg`.

- **`PhaseMarginDelta`** (frozen Pydantic VO, T021 family):
  - `before: PhaseMarginMeasurement | None`,
    `after: PhaseMarginMeasurement | None`,
    `delta_absolute: float | None` (delta margin_deg),
    `delta_relative_percent: float | None`,
    `failed_reason: str | None`,
    `metric_field: Literal["phase_margin"]`.
  - Validator: `after==None ⇔ failed_reason set` (T021 паттерн).

- **`AutoDetectInfo`** (frozen Pydantic VO):
  - `chosen_node: str`,
  - `confidence: float ∈ [0, 1]`,
  - `alternatives: list[tuple[str, float]]` — top-N candidates с
    confidence,
  - `algorithm_notes: str` — short human-readable.

- **`FeedbackCycle`** (frozen, used internally by graph analyzer):
  - `nodes: list[str]`, `elements: list[str]`,
  - `forward_path_score: float`, `feedback_path_score: float`,
  - `suggested_break_node: str`, `confidence: float`.

### Injection strategies (ABC + 4 impls)

- **`InjectionStrategy`** (abstract base, `domain/phase_margin.py`):
  - `def patch(netlist: str, break_node: str) -> InjectionPatch:
    return list of source patches + probe-pair nodes`.
  - `def combine(sweep_v: AcSweep, sweep_i: AcSweep | None) ->
    LoopGain: T(jω) calculated по method-specific formula`.

- **`MiddlebrookVoltageStrategy`**: voltage source insertion +
  single sweep + `T = -V(rev)/V(fwd)`.
- **`MiddlebrookCurrentStrategy`**: current source insertion +
  single sweep + `T = -I(rev)/I(fwd)`.
- **`TianStrategy`**: voltage + current sweeps → Tian combine
  formula.
- **`DoubleRosenstarkStrategy`**: two voltage sweeps с разными
  source positions → linear combine.

### Use cases (`application/`)

- **`measure_phase_margin`**:
  - Args: `netlist_text`, optional `loop_break_node` (если None →
    auto-detect), `ac_sweep`, `simulator`, `netlist_editor`,
    `injection_strategy`, optional `repo`, `confirmation_callback`
    (для TTY confirmation injection — port для testability).
  - Returns: `PhaseMarginMeasurement`.
  - Errors (domain): `LoopBreakNodeNotFoundError`,
    `NoUnityGainCrossoverError`, `LoopGainAlwaysAboveUnityError`,
    `NoFeedbackLoopDetectedError`, `AutoDetectConfidenceTooLowError`.

- **`detect_feedback_break_node`**:
  - Args: `netlist_text`, `confidence_threshold`.
  - Returns: `AutoDetectInfo`.
  - Errors: `NoFeedbackLoopDetectedError`.

### Graph analyzer

- **`NetlistGraphAnalyzer`** (`domain/netlist_graph.py` или
  `application/`):
  - `parse(netlist: str) -> CircuitGraph` (узлы = nets, edges =
    elements с element-type metadata: R/C/L/V/I/diode/transistor/
    voltage-controlled-source/subckt).
  - `find_cycles(graph: CircuitGraph) -> list[FeedbackCycle]`.
  - `score_break_candidates(cycles: list[FeedbackCycle]) ->
    AutoDetectInfo`.
  - Heuristics:
    - Forward path: содержит **active element** (transistor /
      voltage-controlled-source / op-amp subckt).
    - Feedback path: **purely passive** (R / C / L combination, нет
      active elements).
    - Highest-impedance node в feedback path = preferred break point
      (минимизирует loading при injection).
  - Confidence scoring: монотонная функция от (active-element-only
    forward path), (purely passive feedback), (high impedance break),
    (single dominant cycle vs multiple cycles).

### CLI / Slash

- **`bridge measure phase-margin <NETLIST>`** subcommand под Typer
  sub-app (same as T023).
- **`/measure-phase-margin`** slash (T014 A1 flat hyphenated).
- **`/edit-and-resim`** slash расширение (Q11=a): новый `phase-margin`
  metric value.

### Phase A feedback fixtures

- **`data/templates/nfb-se-amp/`** (Q6=a) — NFB SE tube amp:
  - Двухкаскадный SE на 6Н1П + 6П14П (или single-stage с feedback,
    решим в Phase A).
  - Global voltage feedback из вторички OPT в катод 1-го каскада
    через Rfb + Cfb.
  - Включает все 4 типа файлов template'а (`.kicad_sch`,
    `.kicad_pro`, manifest, README).
- **Secondary (для cross-validation auto-detect и Tian method)** —
  минимальная op-amp inverting fixture как `.cir` only (не full
  template; для unit tests). См. Phase A delivery.

## 6. Assumptions & Constraints

- **ngspice 45.2** (после T021/T159) — standard AC analysis path.
- **Linear small-signal regime** — Middlebrook injection
  предполагает linearizable operating point. На сильно нелинейных
  стадиях (clipping, deep saturation) PM не определён физически —
  caller отвечает за выбор разумных DC operating conditions.
- **Single SISO loop** — измеряем один loop за раз. Multi-loop
  feedback (например, local cathode + global voltage) → caller
  должен выбрать, какой loop разрезать. Tool не пытается их
  разделить.
- **Causality** — netlist должен симулироваться как-есть до
  injection (валидный DC operating point). Тест: AC sweep до
  injection не падает.
- **Точность crossover detection** — линейная интерполяция в `log f`
  / `dB`-масштабе достаточна для PM ±2° при `--points-per-decade
  ≥ 50`. Higher accuracy → больше points, не numerical reformulation.

## 7. Out of Scope

(После Clarify 2026-05-31 несколько изначальных out-of-scope пунктов
перенесены в-scope. См. Resolved.)

- **Compensation network suggestion.** Tool сообщает PM/GM, не
  предлагает «добавь 100 pF между collector и base». — T029/T032.
- **Schematic-side `feedback_break` property markup** в KiCad. Tool
  работает с netlist'ом, не с KiCad-метаданными.
- **Multi-loop decomposition** (inner-outer loops separation в
  multi-feedback circuit'е). Один loop per call.
- **Closed-loop transient stability** (step response, overshoot,
  ringing). Future task.
- **Gain margin как обязательное поле** (опциональное через
  `--with-gain-margin`, Q1=c).
- **ML-trained graph classification** для auto-detect. Heuristics
  rule-based на element-type metadata.
- **Сторонние injection methods** beyond четырёх стандартных
  (Middlebrook voltage/current, Tian, Rosenstark double). Roy's
  method, Hurst's symbolic injection — future tasks.

---

## Clarify (заполняется Claude)

### Open questions

**Q1. Gain margin: включать в VO как обязательное, опциональное или
отдельной командой?**

Контекст: PM и GM — стандартная пара stability metrics. PM = phase
margin в gain crossover. GM = `-20*log10|T(jω_π)|` в phase crossover
(точка `phase = -180°`). Маргинальная стоимость GM при готовом
sweep'е ≈ 0 (тот же AC dataset). Но:
- (а) GM может не существовать (phase никогда не пересекает -180° в
  диапазоне);
- (б) Single output `(PM, f_c)` проще для агента;
- (в) Опциональный flag добавляет surface.

**Варианты:**
- (a) **Только PM** — минимализм. GM — следующая задача.
- (b) **PM + GM обязательно** (`PhaseMarginMeasurement` всегда несёт
  оба, `gain_margin_db: float | None`). VO complete, агент получает
  всё разом.
- (c) **PM mandatory, GM опционально через `--with-gain-margin`
  флаг**. Default — только PM (proportional to BACKLOG triggering
  acceptance text). С флагом — оба.

**Моя рекомендация: (c).** Не раздуваем default output (BACKLOG
acceptance буквально просит `(margin_deg, crossover_hz)`); даём
escape hatch для тех, кому нужен GM.

---

**Q2. Injection method: только Middlebrook voltage или сразу
несколько?**

Контекст: Middlebrook voltage injection — простейший и достаточный
для voltage-mode loops (наш audio NFB case). Tian's method точнее
для feedback с current loops (например, transimpedance op-amp
configurations). Double-injection — самый robust, но 2× cost (два AC
sweep'а per measurement).

**Варианты:**
- (a) **Только Middlebrook voltage.** MVP, расширения — будущие
  задачи.
- (b) **Middlebrook voltage + current** (через `--injection {voltage,
  current}` flag).
- (c) **Middlebrook + Tian + double**, все три за раз.

**Моя рекомендация: (a).** Tube audio (наш use case) — voltage-mode.
Tian / double-injection — следующая итерация, не блокеры.

---

**Q3. Auto-detect break node — стоит ли пытаться?**

Контекст: scope текста BACKLOG: «caller-side hint на break node» —
caller указывает явно. Альтернатива: попытка auto-detect через
graph-анализ netlist'а (находим cycle в DAG элементов с
identifiable forward/feedback paths). Это:
- Сложная задача (false positives неизбежны при non-trivial
  топологии);
- Может ввести в заблуждение, если loop разорван не там, где надо;
- Не критична — caller знает свою схему.

**Варианты:**
- (a) **Только explicit `--loop-break-node`** — MVP.
- (b) **Default explicit + heuristic auto-detect** при отсутствии
  flag'а (с обязательным confirmation в text output: «detected break
  at node X — confirm or use --loop-break-node»).

**Моя рекомендация: (a).** Heuristics на feedback topologies — это
большая отдельная задача (графовый анализ + ML pattern matching);
не вписывается в scope T153. Caller достаточно умён указать руками.

---

**Q4. Phase convention.**

Контекст: ngspice AC возвращает phase в радианах (или градусах при
post-processing) в convention где `V(out) = |H| * exp(j*phase) *
V(in)`. Для negative feedback loop `T(jω)` мы инвертируем return
(см. injection patch); тогда `T = -V(forward) / V(reverse)` или с
прямым знаком — зависит от того, где Vinj стоит.

**Варианты:**
- (a) **Internal convention зафиксирована**: spec/code documenting
  «PM = 180° + arg(T) at gain crossover, where T includes -1 of
  feedback inversion». Reference: Sedra-Smith.
- (b) **Дать caller'у `--invert-sign` flag** на случай экзотической
  топологии.

**Моя рекомендация: (a).** Convention фиксируется in-code один раз;
docstring + KB topic объясняет; никаких flags на эту тему.

---

**Q5. Edge cases (no crossover / multi-crossover / always-above).**

Уже отражено в FR. Подтверждаем выбор:
- **No crossover (gain всегда < 1)**: exit 2 + message. Не fail
  silently, не возвращать NaN.
- **Multiple crossovers**: брать lowest-freq, остальные в
  `extra_crossovers_hz`; soft-warn в stderr.
- **Always > 1**: actionable error с подсказкой расширить
  `--f-high`.

**Моя рекомендация: подтверждаем выбор (как уже в FR).**

---

**Q6. Phase A feedback fixture — какую делаем?**

Варианты:
- (a) **NFB SE tube amp** — естественное расширение существующей
  `se-amp` фикстуры. 2 каскада на 6Н1П + global voltage feedback
  через резистор из вторички OPT в катод первого каскада. Pros:
  стилистически в духе efactory (tube audio), переиспользует уже
  существующие 6Н1П models + 5K:8Ω OPT. Cons: numerical PM
  значения у tube amp с NFB сильно зависят от OPT phase shift —
  reference-валидация трудоёмкая (нужно делать в KiCad GUI и
  сверять).
- (b) **Op-amp inverting amp** — pedagogical baseline. Один op-amp
  (LM741 / OPA134, что есть в `data/models/`) + 2 резистора (Rin,
  Rfb) + load. Pros: predictable numbers (PM от GBW и Rfb), easy
  cross-validate с аналитикой. Cons: нет op-amp моделей в текущей
  `data/models/`, придётся добавлять; не «в духе» tube-проекта.
- (c) **Обе**: и tube NFB, и op-amp. Pros: maximal coverage. Cons:
  Phase A раздувается, +50% time.

**Моя рекомендация: (a) — NFB SE tube amp.** Аргументы: (1)
вписывается в проектный narrative, (2) переиспользует существующую
SE-amp фикстуру через copy-rename (не full new schematic), (3)
reference-валидация — single trusted run в KiCad GUI Vladimir-ом
перед merge (есть feedback_kicad_fixtures memory о двухстадийной
валидации). Op-amp фикстура — natural T027 work (templates
preamp / filter могут включать op-amp в будущем).

---

**Q7. Auto-detect input AC source — нужно ли?**

Контекст: T023 (gain/bw/thd) auto-detect'ит V-source по принципу
«ровно одна V в netlist'е → берём». В T153 injection-источник Vinj
создаётся **нами** в патче — это не «caller's input source». При
этом для AC sweep нужен один stimulus, и Vinj им и является.
Других sources до injection не должно быть в circuit (DC sources
можно — они зануляются в AC analysis ngspice).

**Варианты:**
- (a) **Vinj — единственный AC source, никакого auto-detect.** Все
  существующие V-источники в netlist'е остаются как DC bias (их AC
  компонент = 0). Это чисто и однозначно.
- (b) **Caller указывает existing source** через `--input-source`,
  как в T023.

**Моя рекомендация: (a).** В measure phase-margin семантика «caller
input source» не имеет смысла — измеряем loop transmission, не
amplifier gain.

---

**Q8. Output format defaults.**

T021 / T023 default — text aligned table; json через `--output
json`. Подтверждаем тот же default для T153.

**Моя рекомендация: same as T021/T023 (text default + --output json).**

---

**Q9. Persistence через `SimResultsRepository`.**

T023 ввёл optional `--save-result` который пишет в `SimResults`.
Для phase-margin AnalysisType расширяется `phase-margin`. Sweep
data (full AC dataset до crossover detection) — сохранять или
только VO? Объём AC sweep'а 100 pts × log10(1e6) = ~600 sample
points × (mag + phase) = ~10 KB JSON — несущественно.

**Варианты:**
- (a) Сохранять **только VO** (legkij, decisional output).
- (b) Сохранять **VO + полный sweep dataset** (для аудита, можно
  потом перерисовать Bode плот через T024).

**Моя рекомендация: (b).** Phase margin без подкладки полного Bode
графика — слепое число. Storing 10 KB JSON не больно. Visualization
через T024 — обвязка на этом dataset'е (follow-up).

---

**Q10. Подсветка опасной зоны в text output.**

Стандартные thresholds:
- PM > 60° — high stability margin.
- 45° < PM ≤ 60° — adequate.
- 30° < PM ≤ 45° — marginal.
- PM ≤ 30° — likely ringing / instability.

**Варианты:**
- (a) Только числа, без интерпретации.
- (b) Числа + classification tag в text output (`adequate`,
  `marginal`, `risky`) — agent видит словарную метку и
  интерпретирует пользователю.
- (c) Числа + полный mini-textbook footnote (рисковано — bloat).

**Моя рекомендация: (b).** Coloring через terminal text без
extra dependencies; classification tag в VO как `stability_class:
Literal["high", "adequate", "marginal", "risky"]` — нативный rich
output для агента.

---

**Q11. Интеграция с T021 `edit_and_resim_with_delta`.**

T021 поддерживает `--measure {gain, bandwidth, thd}` — теоретически
можно добавить `phase-margin`. Но: T021 не знает `--loop-break-node`
в своём API. Расширение либо требует propagating loop-break flag
через T021 (ломает clean discriminator union), либо отдельный
edit-and-resim для phase-margin (Q11 → b).

**Варианты:**
- (a) Расширяем T021 (`--measure phase-margin` с обязательным
  `--loop-break-node` если выбран этот metric).
- (b) Отдельная задача в backlog (`bridge edit-and-resim-pm`) —
  не блокирует T153 MVP.
- (c) Оставляем как future enhancement, не делаем follow-up задачу.

**Моя рекомендация: (b).** Заводим в BACKLOG follow-up задачу.
Сейчас не блокирует.

---

**Q12. Level 3 smoke в `efactory:linux` — обязательный?**

KB sync дисциплина (CLAUDE.md, T134): Level 1+2 — every PR с user-
facing функционалом; Level 3 — на milestone / infrastructure
change. T153 — user-facing функционал, но не infrastructure change.

**Варианты:**
- (a) Level 1+2 only (как T021 / T161). Level 3 — на milestone
  acceptance gate.
- (b) Level 3 obligatory.

**Моя рекомендация: (a).** Стандарт для подобных задач.

---

**Q13. Symbol для injection patch — `Vinj` или конфликт с user
namespace?**

ngspice case-insensitive по reference designators. Если в caller's
netlist уже есть `Vinj`, патч его перезатрёт. Защита: prefix
typical уникальной строкой типа `Veft153inj`. Bloat имени —
терпимо.

**Варианты:**
- (a) Hard-coded `Veftpminj` (короткий unique префикс).
- (b) Pre-scan netlist, выбрать collision-free name динамически.
- (c) Параметризовать через `--injection-source-name <name>` (escape
  hatch).

**Моя рекомендация: (b).** Pre-scan тривиален, дублирует логику
T021 schematic editor'а; никаких magic strings или escape hatches.

---

### Resolved (с ответами)

Clarify прошёл 2026-05-31. Из 13 вопросов 9 — «по рекомендации», 4
— расширяющие scope (Q2/Q3/Q11/Q12). Расширения **осознанные**,
ради полнофункциональной реализации, а не MVP.

- **Q1 = c.** PM mandatory, GM опционально через флаг
  `--with-gain-margin`. По рекомендации.

- **Q2 = c.** **Все четыре injection methods** в strategy pattern:
  Middlebrook voltage (default), Middlebrook current, Tian's
  method, Rosenstark double-injection. Не MVP — полная коллекция
  стандартных методов из IEEE literature. Triggers `DECISIONS.md`
  ADR-T153a с math derivations и references.

- **Q3 = b.** **Heuristic auto-detect feedback break node** включён
  default-режимом, explicit `--loop-break-node` — escape hatch.
  Auto-detect через netlist graph analyzer (cycle detection +
  forward/feedback heuristics по element-type metadata). Confirmation
  prompt в TTY; auto-accept выше confidence threshold в non-TTY.
  Triggers `DECISIONS.md` ADR-T153b с algorithm description.

- **Q4 = a.** Internal phase convention фиксируется in-code (PM = 180°
  + arg T at gain crossover, negative feedback inversion built in).
  Документация в docstring + KB topic. Никакого `--invert-sign`. По
  рекомендации.

- **Q5 = a.** Edge cases как в FR: no crossover → exit 2 + message;
  multi-crossover → lowest-freq в primary, остальные в
  `extra_crossovers_hz` + soft warn; gain always > 1 → actionable
  error «расширь `--f-high`». По рекомендации.

- **Q6 = a.** **NFB SE tube amp** как Phase A фикстура — copy-extend
  существующей `data/templates/se-amp/` с global voltage feedback из
  вторички OPT в катод 1-го каскада 6Н1П через Rfb + Cfb (зануляет
  bypass-cap effect feedback'а на низких частотах). Дополнительная
  op-amp inverting fixture как `.cir`-only для cross-validation
  Tian/double-injection (см. § Phase A feedback fixtures). По
  рекомендации.

- **Q7 = a.** Vinj — единственный AC source, никакого auto-detect
  существующего V-источника. Семантически phase-margin отличается
  от gain/bw/thd: измеряем loop transmission, не amplifier gain.
  По рекомендации.

- **Q8 = a.** Text aligned по умолчанию, json через `--output json`.
  Same as T021/T023. По рекомендации.

- **Q9 = b.** Persistence VO + полный sweep dataset. ~10 KB JSON,
  обеспечивает поздний Bode plot через T024 follow-up. По
  рекомендации.

- **Q10 = b.** PM + stability classification tag в VO и text output:
  `high` (> 60°), `adequate` (45-60°), `marginal` (30-45°), `risky`
  (≤ 30°). Tag — derived field в `PhaseMarginMeasurement`. По
  рекомендации.

- **Q11 = a.** **T021 `edit_and_resim_with_delta` extension в этой
  же задаче.** Добавляется четвёртая метрика `phase-margin` через
  `--measure phase-margin`. Новый `PhaseMarginDelta` VO (T021 family,
  phase-coherent с GainDelta/BandwidthDelta/ThdDelta). Slash
  `/edit-and-resim` docs обновляются. Формально нарушает «PR =
  одна задача», но scope логически связан и сознательно объединён
  ради single delivery.

- **Q12 = b.** **Level 3 smoke в `efactory:linux` obligatory** —
  Phase E acceptance gate. 6+ scenarios через `docker run efactory:
  linux claude -p "..."` headless. Включает test agent правильно
  выбирает /measure-phase-margin и /edit-and-resim --measure
  phase-margin.

- **Q13 = b.** Pre-scan netlist для collision-free Vinj name
  выбирается динамически. Никаких magic strings. По рекомендации.

---

## Analyze (заполняется Claude)

<!-- После Clarify. -->
