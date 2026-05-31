# Spec: `bridge measure phase-margin` — запас по фазе для feedback-схем

**Статус:** Analyzed
**Дата создания:** 2026-05-31
**Clarify прошёл:** 2026-05-31 (13 вопросов; 9 «по рекомендации» +
4 расширения scope — Q2/Q3/Q11/Q12 — осознанные, ради
полнофункциональной реализации, не MVP).
**Analyze прошёл:** 2026-05-31 (20 issues: 6 Critical, 8 Warning,
6 Note; C1 resolved via TDD cross-validation path после Phase 0
research; C3/C4 закрыты inline в FR; W2 resolved sanity-check'ом
`AcSweep` уже pydantic frozen).
**Phase 0 scope correction (2026-05-31):** Clarify Q2=c терминология
неточна — «Rosenstark double-injection» заменён на «Rosenstark
return-ratio open/short-circuit (1984)»; Tian год исправлен 1998
→ 2001 (IEEE Circuits & Devices Magazine).
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

- **Четыре loop-gain measurement methodologies** (Q2=c, terminology
  corrected в Phase 0 research): Middlebrook voltage injection (1975),
  Middlebrook current injection (1975), Tian's symmetric method (2001,
  IEEE Circuits & Devices Magazine; часто эквивалентна Middlebrook
  double-injection в результате), Rosenstark return-ratio open/short-
  circuit method (1984, Int. J. Electronics). Strategy pattern с
  per-method validation reference circuits.
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

- **ДОЛЖНА** поддерживать **два способа** определить break edge
  (Q3=b; revision 2026-06-01 — edge, не node; pair `node +
  element_ref` задаёт уникальный wire в circuit graph):
  - **Explicit override:** `--loop-break-node <node>
    --loop-break-element <element_ref>` — обе строки **обязательны**
    одновременно. Никаких heuristics, прямой приказ caller'у. Если
    указан только один из флагов → exit 2 + actionable error
    «оба флага требуются для explicit override».
  - **Heuristic auto-detect (default):** при отсутствии флагов tool
    строит граф netlist'а, ищет cycle'ы, классифицирует пути на
    forward / feedback по element-type heuristics, выбирает наиболее
    вероятный break edge `(node, element_ref)` + рассчитывает
    confidence score.
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
- **ДОЛЖНА** иметь флаг `--confidence-threshold <0..1>` (default
  `0.8`) для override default. **Convention** (C4): confidence
  auto-detect ≥ threshold → accept; < threshold → reject в non-TTY
  (exit 2 + actionable message) или confirmation prompt в TTY.
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
  3. **`tian`** (Michael Tian et al., IEEE Circuits & Devices Magazine
     2001, «Striving for Small-Signal Stability»): два sweep'а —
     voltage injection даёт `T_v(jω)` и current injection даёт
     `T_i(jω)` в одной точке; combined через symmetric formula
     (hypothesis: `T(jω) = (T_v·T_i − 1) / (T_v + T_i + 2)` —
     **C1 hypothesis, verification path = TDD cross-validation на
     op-amp reference в Phase B**, не reference-doc-based). Главное
     преимущество — symmetric (independent от probe orientation).
     Часто численно эквивалентна Middlebrook double-injection (1975).
     Используется как default в Cadence Spectre `stb`. Validation
     reference: op-amp inverting amp + tube NFB cross-check.
  4. **`rosenstark_return_ratio`** (Sol Rosenstark, Int. J. Electronics
     1984, «Loop gain measurements in feedback amplifiers»): не
     injection-based — анализ break point под двумя нагрузками,
     open-circuit и short-circuit. Combined formula (hypothesis,
     verification как у Tian): `T_RR = (T_oc · T_sc + T_oc + T_sc) /
     (T_oc · T_sc − 1)`. Академически интересен как cross-validation
     methodology vs Middlebrook-семейства; в commercial SPICE tools
     не используется как default, но даёт independent verification.
     Validation reference: same op-amp setup для cross-check всеми
     методами.
- **ДОЛЖНА** иметь CLI flag `--injection-method
  {middlebrook-voltage,middlebrook-current,tian,rosenstark-return-ratio}`
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
      [--loop-break-node <node> --loop-break-element <ref>]  # explicit pair (revision 2026-06-01); default: auto-detect
      [--confidence-threshold 0.8]
      [--no-confirm]
      [--injection-method {middlebrook-voltage,middlebrook-current,tian,rosenstark-return-ratio}]
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
    "middlebrook_current", "tian", "rosenstark_return_ratio"]`.
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
  - `chosen_element_ref: str` (edge-vs-node revision 2026-06-01;
    ref элемента, через который физически режется loop),
  - `confidence: float ∈ [0, 1]`,
  - `alternatives: tuple[tuple[str, str, float], ...]` — top-N
    candidates `(node, element_ref, confidence)`,
  - `algorithm_notes: str` — short human-readable.

- **`FeedbackCycle`** (frozen, used internally by graph analyzer):
  - `nodes: tuple[str, ...]`, `elements: tuple[str, ...]`,
  - `forward_path_score: float`, `feedback_path_score: float`,
  - `suggested_break_node: str` (∈ `nodes`),
  - `suggested_break_element_ref: str` (∈ `elements`, edge-vs-node
    revision 2026-06-01),
  - `confidence: float`.

### Injection strategies (ABC + 4 impls)

- **`InjectionStrategy`** (abstract base, `domain/phase_margin.py`):
  - `def prepare(netlist: str, *, break_node: str,
    break_element_ref: str) -> InjectionSetup` (edge-vs-node revision
    2026-06-01: edge определяется парой node+element_ref).
  - `def combine(sweeps: tuple[AcSweep, ...], setup: InjectionSetup)
    -> LoopGain: T(jω) calculated по method-specific formula`.

- **`MiddlebrookVoltageStrategy`**: voltage source insertion +
  single sweep + `T = -V(rev)/V(fwd)`.
- **`MiddlebrookCurrentStrategy`**: current source insertion +
  single sweep + `T = -I(rev)/I(fwd)`.
- **`TianStrategy`**: voltage + current sweeps → Tian combine
  formula.
- **`RosenstarkReturnRatioStrategy`**: two sweeps на break point
  при open-circuit + short-circuit модификациях netlist'а →
  combined через Rosenstark formula.

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

- **`NetlistGraphAnalyzer`** (`src/domain/netlist_graph.py`, C3
  resolved — pure algorithmic, без ports):
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

Прошёл 2026-05-31 после Clarify. Перечитал spec, нашёл 20 issues:
6 Critical (требуют resolve перед Phase 0), 8 Warning (обсуждаем),
6 Note (к сведению, реализационные guidance).

### 🔴 Critical (фиксим до Phase 0)

**C1. Tian / Rosenstark combine formulas требуют verification —
RESOLVED via TDD cross-validation path (Phase 0 decision 2026-05-31).**

WebFetch reference docs (IEEE PDF за paywall, EDN timeout, designers-
guide 403) **не доступны** для прямого extraction точных формул.
Hypothesis formula (записаны в FR):
- Tian: `T = (T_v·T_i − 1) / (T_v + T_i + 2)`.
- Rosenstark return-ratio: `T_RR = (T_oc·T_sc + T_oc + T_sc) /
  (T_oc·T_sc − 1)`.

Path forward: **TDD cross-validation на op-amp reference (Phase A
generic_opamp.subckt)**: для analytical-known PM-circuit все 4
methods должны дать same PM ±2°. Если formula неправильная —
каскадный fail в integration tests на этом reference, найдём
причину в debugging. Это **gold-standard verification** (numerical
equivalence на known reference), сильнее чем blind trust к
reference doc. Дополнительная sanity-check возможна в Phase 0 ADR-
T153a math derivation (мы выводим формулы сами из определения T_v
+ T_i + linear superposition).

Phase 0 ADR-T153a содержит:
- Math derivation Middlebrook V/I из first principles (defined T as
  «what gain accumulates after one full loop traversal»).
- Tian formula derivation как symmetric improvement Middlebrook
  double.
- Rosenstark return-ratio formula derivation из open-circuit +
  short-circuit responses.
- References (Middlebrook 1975, Tian 2001, Rosenstark 1984) даже
  если formulas verified TDD-style — для historical context.

**C2. Op-amp SPICE model — отсутствует в `data/models/`.**

Phase A planning: «op-amp inverting fixture для cross-validation» —
но в `data/models/` сейчас только tube models (Duncan triodes). Нет
ни одной op-amp модели. Без неё:
- Phase A фикстура неполная (только NFB tube amp, без cross-
  validation).
- Phase B unit testing strategies без referenсе circuit'а становится
  сложнее.
- Tian/Rosenstark validation без op-amp reference — нечем верифицировать.

**Action:** в Phase A добавить минимальный generic ideal op-amp как
SPICE `.subckt` (Voltage-Controlled Voltage Source E + RC dominant
pole + output resistor). ~10-15 строк. Не production-grade,
достаточно для unit tests. Положить в
`data/models/opamps/generic/GENERIC_OPAMP.lib` (option B chosen
2026-05-31: full ComponentCategory integration, не helper-папка —
позволяет `efactory opamp list/show` + user overlay). Не конкретная
модель типа LM741/OPA134 — это T030 (model_import_url) future task.

**Phase A.1 closed 2026-05-31:** Topology G·R·C·E·Rout
(gm=1, R1=100k → A0=100 dB; C1=159.155n → fp=10 Hz, GBW=1 MHz;
Rout=50 Ω). Acceptance tests на open-loop AC sweep дают expected
A0, GBW, -90° phase at GBW, Rout divider. Adapter / CLI / docs
обновлены под `ComponentCategory.OPAMP` + `OpampKind.SINGLE_POLE`.

**C3. NetlistGraphAnalyzer placement — `domain/` vs `application/`.**

В Key Entities я неоднозначно записал. По hexagonal architecture
(efactory adheres):
- **Domain** — pure business logic без зависимостей от ports
  (Simulator, NgspiceNetlistEditor).
- **Application** — use case orchestration с ports inputs.

Graph analyzer чисто алгоритмический (netlist parsing + cycle
detection + heuristic scoring) — без simulator dependencies. **Это
domain.** Action: spec фиксирует `src/domain/netlist_graph.py`.
Один-к-одному с `domain/simulation.py` (где AcSweep / TranAnalysis).

**C4. Confidence threshold convention undocumented.**

`--confidence-threshold 0.8` означает «accept выше этого значения»
или «warn ниже»? Стандартно lower-bound (accept ≥). Spec не
фиксирует. Action: явно записать в FR (§Loop break):

> «`confidence_threshold`: float ∈ [0, 1], confidence
> auto-detect ≥ threshold → accept; < threshold → reject в
> non-TTY (exit 2) или confirmation prompt в TTY. Default = 0.8.»

**C5. NFB SE tube amp self-stability не гарантирована.**

NFB feedback в tube amp с OPT — system может оказаться unstable при
certain Rfb values (over-feedback). Phase A фикстура должна
**заведомо стабильна** для PM measurement (PM ∈ [20°, 80°] range —
worth measuring). Если получится PM negative — фикстура
бесполезна для acceptance tests.

Action: в Phase A проектировать Rfb / Cfb с целевой PM ~ 45-60° (по
analytical estimate). Validate в KiCad GUI Vladimir-ом перед merge
(memory: feedback_kicad_fixtures.md двухстадийная валидация).

**C6. Multi-loop в NFB SE tube amp.**

«NFB SE tube amp» обычно содержит и (1) global voltage NFB через
Rfb, и (2) local cathode degeneration (если cathode resistor без
bypass cap). Это **multi-loop**, что мы explicit ставим Out of
Scope. Tool должен корректно brать **global loop** при auto-detect.

Action: в Phase A фикстуре либо (a) использовать cathode bypass cap
на 1-м каскаде (де-факто закорачивает local cathode loop в AC,
оставляя global), либо (b) — в Phase C graph analyzer heuristic
«lowest-frequency-significant cycle» предпочитает global (более
длинный) loop. Решение в Phase 0 ADR-T153b. Phase A фикстура — bypass
cap путь (проще для acceptance tests).

### 🟡 Warning (обсуждаем)

**W1. Coverage threshold ≥80% на graph analyzer — рискованно.**

Graph code часто содержит hard-to-reach error branches (degenerate
graphs, disconnected components). Тестировать каждый branch требует
synthetic fixture per branch. Может реально получиться 70-75%
coverage на `domain/netlist_graph.py`. Project-wide threshold
сохраняется (≥80% на `src/`), но локально на module — может
протестить.

Action: писать tests aggressively, не ослаблять threshold. Если на
финале не вытягиваем — обсудить локальный `# pragma: no cover` на
defensive branches (с явным комментарием почему).

**W2. `AcSweep` serializability для VO sweep_dataset persistence.
RESOLVED.**

Проверено в `src/domain/simulation.py:134`: `AcSweep(BaseModel)` с
`model_config = ConfigDict(frozen=True)`. Already pydantic frozen +
JSON-serializable из коробки. Никакого refactor'а не нужно.

**W3. T021 extension может сломать existing tests.**

`edit_and_resim_with_delta` принимает list of metrics. Добавление
`phase-margin` потенциально меняет signatures (новый optional
parameter `loop_break_node`). Existing T021 tests должны pass без
изменений (extend-only, no behavior break).

Action: в Phase F регрессить T021 test suite (52 теста по
CHANGELOG). Если что-то breaks — rollback approach, обсудить с
Vladimir-ом.

**W4. `extra_crossovers_hz` semantics в auto-detect.**

Если multiple crossovers detected И мы делаем auto-detect break
node — что в `extra_crossovers_hz`? Все crossovers для выбранного
auto-detect loop'а, или across alternative loops? Лучше — для
chosen loop only.

Action: явно в spec FR (§Crossover detection): «extra_crossovers_hz
relates to the chosen loop (single-loop semantics maintained)».

**W5. Tian/Rosenstark два sweep'а — performance impact.**

Tian требует 2 AC sweeps (voltage + current) per measurement → 2×
simulator time. Rosenstark return-ratio — тоже 2 sweeps (open + short
circuit). На больших циркуитах (NFB tube amp с OPT и nonlinear
elements) AC sweep может занять секунды. Default injection-method =
middlebrook_voltage (один sweep) — OK. Но если T021 вызывает phase-
margin × 2 (before/after) с Tian — 4 sweeps. На большой схеме это
10+ секунд.

Action: документировать в slash help / KB topic: «Tian / Rosenstark
return-ratio — accuracy at 2× simulation cost; default Middlebrook
voltage sufficient для most cases».

**W6. Op-amp generic_opamp.subckt vs real op-amp models.**

Generic op-amp (E + RC pole) хорош для unit tests, но не
representative для real-world phase margin (real op-amps имеют
multi-pole / zero / current limiting). Acceptance criteria PM ±2° на
generic op-amp — easy. На real op-amp может выйти ±5°.

Action: для T153 MVP — generic. В Phase A документировать что
acceptance tests на generic; real-op-amp validation — future task
(после T030 import_url).

**W7. Confirmation callback port — composition root complexity.**

`measure_phase_margin` accepting `confirmation_callback` для TTY
prompt. Composition root (`build_app`) должен decide:
- non-interactive (typer CLI script): callback = lambda → True
  если confidence ≥ threshold else False.
- interactive TTY: callback = `typer.confirm()`-based.
- testing: callback = injected mock.

Action: в Phase B спроектировать `ConfirmationPort` ABC или просто
callable type alias. Lean approach — callable type, port overkill
для one-method interface.

**W8. KiCad GUI manual smoke на Phase A — runtime cost.**

Phase A acceptance включает Vladimir manually opening NFB SE tube
amp в KiCad Simulator и сверки PM (T123 memory: Sim.Library warning
безвреден, но Simulator работает). Это **manual step**, занимает
~10-15 мин. Если acceptance fail — Phase A пере-итерация.

Action: Phase A design Rfb по analytical pole-zero estimate (не «на
глаз»), чтобы first KiCad run prob succeeded.

### 🟢 Note (реализационные guidance)

**N1. Pre-scan injection source name — helper в strategy base.**

`InjectionStrategy.patch()` сам отвечает за unique naming. Хелпер
`_unique_source_name(netlist: str, prefix: str = "Vinj") -> str` —
тривиальная функция (regex `^[VI]<prefix>...` lookup + counter).
Может жить в `domain/netlist_graph.py` (re-use parser).

**N2. AutoDetectInfo с tuple — pydantic frozen coercion.**

`alternatives: list[tuple[str, float]]` — pydantic v2 frozen with
tuple внутри: pydantic coerces tuples → lists в `.model_dump()`.
T021/T023 решали через `Annotated[tuple, ...]` или `model_config =
ConfigDict(arbitrary_types_allowed=False)`. Подсмотреть как в
GainMeasurement.

**N3. Implementation Plan в spec.md.**

Можно добавить короткую секцию «Implementation Plan» после §7 с
8-phase summary. Не критично (TaskList уже содержит), но дополняет
spec self-contained nature.

**N4. SPICE deck stripped comments — на injection patch.**

При patching netlist'а лучше strip `*` SPICE-комментарии в
output (минимизация diff'а для каждого injection method). Уже T021
делает так в `NgspiceNetlistEditor` — sanity check совместимости.

**N5. Confidence calibration на N≥3 fixtures.**

Confidence formula в graph analyzer — heuristic. Калибровка на
N≥3 фикстурах: NFB SE tube amp, op-amp inverting, multi-loop
edge case (synthetic). Если confidence-score линейная функция от
heuristic features, fit ~3 points.

**N6. KB topic про injection method selection guidelines.**

Phase E KB sync: добавить topic
`spice.phase-margin-injection-methods` с decision matrix:
- voltage-mode loop / high-impedance break → Middlebrook voltage.
- current-mode loop / low-impedance break → Middlebrook current.
- arbitrary impedance / high accuracy required → Tian.
- loading concerns → Rosenstark double-injection.

Agent читает это при выборе method для конкретной схемы.

---

### Action items перед Phase 0

1. **C1** — ✅ resolved via TDD cross-validation path в Phase B
   (hypothesis formula в FR, verification — 4 methods × same PM
   ±2° на op-amp reference). Reference docs не доступны WebFetch.
2. **C2** — generic op-amp `.subckt` спроектировать в Phase A. ~10-15
   строк (E + RC dominant pole). Не блокер до Phase A start.
3. **C3** — ✅ resolved inline в FR (Key Entities §Graph analyzer
   placement `src/domain/netlist_graph.py`).
4. **C4** — ✅ resolved inline в FR (Loop break §confidence threshold
   convention).
5. **C5+C6** — Phase A фикстура strategy (Rfb design pole-zero
   estimate ≈ 45-60° PM, cathode bypass cap eliminates local-loop).
6. **W2** — ✅ resolved sanity-check'ом (`AcSweep` уже pydantic
   frozen).

### Phase 0 entry checklist

После закрытия Critical issues → Phase 0 ADR drafts → Phase A.

---

## Clarify revision 2026-06-01 — edge vs node

Обнаружено при старте Phase B.3 (NgspiceInjectionNetlistPatcher
adapter). Затрагивает Phase B.1 (domain VO) и Phase B.2
(InjectionStrategy ABC + 4 impl) — оба заведены через retroactive
patch'и.

### Проблема

ADR-T153c определил `InjectionNetlistPatcher.insert_voltage_source(
netlist, *, break_node: str, ...)` — port принимает только имя
SPICE-нета. Аналогично `InjectionStrategy.prepare(netlist, *,
break_node)`. Контракт **не определяет однозначно topology cut**:

К типовому break-неду подключены 2-3 элемента. Например, в Phase A
NFB SE amp фикстуре нет `/sec_a` соединяет три элемента:
`L_sec` (OPT secondary), `R_load` (8 Ω нагрузка), `C_fb_block`
(feedback cap). Чтобы измерить loop-gain, source должен встать
**именно** в feedback-провод `C_fb_block ↔ /sec_a`, а не в OPT- или
load-edge. Конвенция «split node» сама по себе этого выбора не
делает.

Heuristic вроде «first-line element остаётся, last-line — на N_fwd»
работает только пока порядок элементов в netlist'е стабилен. KiCad-
exporter порядок не гарантирует, любая перерисовка / замена
элемента ломает конвенцию silently — пара тестов проходит, физика
ломается.

Эвристики по element-type (active vs passive) не помогают тоже:
break point деревенно может находиться в чисто passive-территории
(как `/sec_a` в NFB SE amp).

### Решение

**Edge вместо node.** Контракт breaking определяется парой
`(break_node, break_element_ref)` — ровно один wire в circuit graph.

**Port API расширяется** — все 4 метода
`InjectionNetlistPatcher` получают обязательный keyword
`break_element_ref: str`:

```python
def insert_voltage_source(
    self,
    netlist: str,
    *,
    break_node: str,
    break_element_ref: str,
    source_ref: str,
    ac_magnitude: float = 1.0,
) -> NetlistPatchResult: ...
```

Семантика: **в строке элемента `break_element_ref`** заменить ссылку
на `break_node` на новое имя `<break_node>__fwd`. Остальные строки
с `break_node` не трогаются. Source мостит `__fwd ↔ break_node` (или
к земле, для current/Rosenstark).

**Domain VO `AutoDetectInfo`** и **`FeedbackCycle`** (Phase B.1)
расширяются полем `chosen_element_ref: str` / `suggested_break_element_ref:
str` соответственно. Validator: ref ∈ `elements`.

**`InjectionStrategy.prepare(...)` ABC** — keyword `break_element_ref`
становится обязательным; 4 concrete impl пробрасывают arg в
patcher.

**`measure_phase_margin` use case** — принимает `break_node +
break_element_ref` от auto-detect (`NetlistGraphAnalyzer`) или
explicit CLI override.

**`NetlistGraphAnalyzer`** (ещё не имплементирован, ADR-T153b
описывает) — возвращает edge-pair, не только node. Heuristic
«highest-impedance feedback edge» уже работала на edge-level в
spec'е §3 («edge cut»), просто терминологически называлась
«break node».

**CLI** — два опциональных флага вместо одного:

```
--loop-break-node <node> --loop-break-element <ref>
```

Оба обязательны при explicit override (если один указан без
другого — exit 2 + actionable). Auto-detect возвращает обе строки
вместе.

`AutoDetectInfo.alternatives` — `tuple[tuple[node, element_ref,
confidence], ...]` (раньше `tuple[tuple[node, confidence], ...]`).

### Почему ровно один element-ref, а не «forward partition»

Set-based partition (`forward_elements: tuple[str, ...]`) — более
общий contract, но избыточный. В классической Middlebrook /
Rosenstark loop-cut методологии разрыв происходит в **одном
проводе** — это физика, не упрощение. Если нужен более сложный
patch (split нескольких эджей одного нета) — это другой
methodology, и нужен отдельный port-метод. Пока не нужно.

### Что **не** меняется

- Кол-во methodologies (4) — те же.
- Combine-формулы Middlebrook/Tian/Rosenstark — те же.
- `LoopGain` / `InjectionSetup` / `NetlistPatchResult` / `ProbePair`
  — не трогаются.
- CLI семантика (`--injection-method`, `--f-low/--f-high`,
  `--with-gain-margin`, etc.) — без изменений.
- Spec §4 Success Criteria, §6 Assumptions, §7 Out of Scope — без
  изменений.
- ADR-T153a общая мотивация — без изменений; ADR-T153c общая
  мотивация — без изменений. Меняются только signatures в их code-
  блоках (patch-комментарий в DECISIONS.md ниже фиксирует это).

### Откатные действия

| Артефакт | Действие |
| --- | --- |
| `src/domain/phase_margin.py` (B.1) | Расширить `AutoDetectInfo` / `FeedbackCycle` + validators. Retroactive commit `T153 Phase B.1 patch`. |
| `src/ports/outbound/injection_netlist_patcher.py` (B.2) | Добавить `break_element_ref` в 4 метода. Retroactive commit `T153 Phase B.2 patch`. |
| `src/domain/phase_margin_injection.py` (B.2) | `prepare()` ABC + 4 impl signature. Retroactive commit (тот же). |
| Tests (B.1 + B.2) | Обновить existing + добавить новые для validators. Те же retroactive commits. |
| `src/adapters/outbound/ngspice/injection_patcher.py` (B.3 new) | Реализация с edge-aware split. Новый commit `T153 Phase B.3`. |
| `DECISIONS.md` ADR-T153a / ADR-T153c | Patch-параграф «2026-06-01 revision» в каждый. |
| `specs/.../spec.md` §3 Loop break + §5 Key Entities | Обновляются inline. |

Vladimir подтвердил edge-based design 2026-06-01 при старте B.3.
