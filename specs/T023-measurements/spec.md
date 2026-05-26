# Spec: Измерения как отдельные bridge-инструменты (gain / bandwidth / THD)

**Статус:** Analyzed
**Дата создания:** 2026-05-26
**Clarify прошёл:** 2026-05-26 (10 вопросов, все «по рекомендации»)
**Analyze прошёл:** 2026-05-26 (12 issues: 1 Critical разрешён in-spec,
4 Warning отражены в FR/Assumptions, 7 Note — реализационные guidance)
**Связанные документы:**
- `BACKLOG.md → ### Фаза 2 → T023`.
- `domain/simulation.py` — `AcAnalysis` / `TranAnalysis` / `FourierAnalysis` /
  `AcSweep` / `FourierResult` / `TimeSeries` (готовая инфраструктура).
- `application/analyze_distortion_spectrum.py` — T131 saturable THD sweep
  (рядом, но не overlap: T131 — sweep по (freq, power) с saturable
  injection; T023 — одиночная точка/диапазон на as-is netlist'е).
- `application/bridge_sweep.py` — T022 candidate (parametric sweep).
- T021 (BACKLOG) и T022 (BACKLOG) — оба упираются в T023 как фундамент.
- **T153** (BACKLOG, заведена 2026-05-26 после Q-B clarify) — phase
  margin как отдельная задача с собственным spec'ом, когда появится
  первая feedback-схема в efactory-фикстурах.

---

## 1. Overview

`efactory bridge measure <type>` — три одиночных «измерителя» поверх
готового SPICE-netlist'а: **gain**, **bandwidth**, **THD**. Каждый
возвращает одно число (или малую структуру) + точку или диапазон, в
которой измерение зафиксировано (например, gain = 14.3 dB при `f = 1
kHz`; bandwidth = 25 Hz – 35 kHz по `-3 dB` от пассбанд-midpoint).

Цель — выделить «инструменты-наблюдатели» в самостоятельные use case'ы.
Это нужно как для прямого использования агентом («какой у этой схемы THD
на 1 кГц при 1 Вт?»), так и как **фундамент** для двух следующих задач
Фазы 2: T021 (`bridge_edit_and_resim` с auto-delta по метрикам) и T022
(parametric sweep с метриками в таблице).

**Phase margin** изначально планировался четвёртым измерителем, но по
Clarify Q-B вынесен в отдельную задачу **T153** — open-loop SE/PP (наш
основной use case) phase margin не имеют, а для feedback-схем требуется
дисциплина loop-cut, заслуживающая своего спека.

## 2. Сценарии использования

> Проект без явных «ролей» — efactory работает с агентом и Разработчиком
> через CLI / chat-обёртку.

- **Сценарий A (Agent / single measurement).** Агент проектирует SE
  amp, хочет сверить gain на 1 кГц с целевой спецификацией. Вызывает
  `efactory bridge measure gain <schematic> --freq 1000` → получает
  число + точку измерения.
- **Сценарий B (Agent / band sweep).** Агент хочет узнать полосу
  пропускания готового усилителя. Вызывает `efactory bridge measure
  bandwidth <schematic> --f-low 1 --f-high 1e6 --ref-db -3` →
  возвращает `(f_low_3dB, f_high_3dB, bandwidth_hz)`.
- **Сценарий C (Agent / quick THD).** Агент хочет узнать THD на 1 кГц
  при заданной амплитуде входа. Вызывает `efactory bridge measure thd
  <schematic> --freq 1000 --v-in-peak 0.1` → THD %, доминирующий
  harmonic, фактическая мощность в нагрузке. (T023 не делает
  calibration loop по target-power — это специализация T131.)
- **Сценарий D (T021 prerequisite, programmatic).** Use case
  `bridge_edit_and_resim` после edit'а netlist'а зовёт `measure_gain`
  + `measure_thd` ДО и ПОСЛЕ, вычисляет delta. Use case-уровневая
  reuse, не CLI re-shell.
- **Сценарий E (T022 prerequisite, programmatic).** Parametric sweep
  для каждой combination'и зовёт нужные `measure_*` use cases и
  кладёт значения в строку таблицы.

## 3. Functional Requirements

- **ДОЛЖНА** предоставить три отдельных use case'а в `application/`
  и три CLI subcommand'а под `efactory bridge measure …`:
  `gain`, `bandwidth`, `thd` (Q-J → sub-Typer).
- **ДОЛЖНА** каждый use case возвращать структурированный VO с
  числовым значением + контекстом (frequency / range / harmonic
  number и т.п.), а не голым `float`. Три **независимых** VO
  (`GainMeasurement`, `BandwidthMeasurement`, `ThdMeasurement`) без
  discriminated union (Q-A → b).
- **ДОЛЖНА** работать с готовым `.kicad_sch` (через тот же путь, что
  `sim-run`) ИЛИ с готовым SPICE-netlist'ом — единый интерфейс.
- **ДОЛЖНА** не требовать модификации схемы для измерения (никакого
  injecting источников / нагрузок сверх того, что caller явно
  попросил через флаги).
- **ДОЛЖНА** опираться на существующую инфраструктуру `Simulator`
  port'а; ни один measure не пишет собственный subprocess-wrapper над
  ngspice. **THD не wrap'ит T131** `analyze_distortion_spectrum` —
  независимый use case (TRAN + ngspice `fourier`), без зависимости
  на `MagneticComponent` / saturable subckt (Q-D → b).
- **ДОЛЖНА** опционально писать `SimResult` (через тот же
  `SimResultsRepository` из T016), если caller передал repository
  (Q-I → a). `AnalysisType` enum расширяется значениями `gain`,
  `bandwidth`, `thd-single`.
- **ДОЛЖНА** auto-detect input V-source если caller не указал явно
  (Q-G → c): ровно один V-source в netlist'е → берём его; больше
  одного без явного `--input-source` → error с listed candidates.
- **ДОЛЖНА** для `bandwidth` поддерживать оба режима выбора reference
  midpoint'а (Q-H → c): default `--ref auto` (midband = max |H(f)|
  по sweep'у) и escape hatch `--ref-freq <Hz>` (midband = |H(ref_freq)|,
  стандартно 1 kHz для audio).
- **ДОЛЖНА** для `gain` поддерживать оба режима (Q-C → c): default
  `--mode small` (AC analysis, одна точка) и `--mode large` (TRAN-
  based RMS Vout/Vin, отражает clipping / saturation).
- **ДОЛЖНА** требовать обязательного `--freq <Hz>` для `gain` и `thd`;
  для `bandwidth` — `--f-low <Hz>` и `--f-high <Hz>` с default'ами
  `(1, 1e6)` (audio envelope).
- **ДОЛЖНА** для `thd` принимать только `--v-in-peak <V>` (input
  amplitude), **без** target-power calibration loop — это T131
  специализация (Analyze A1).
- **МОЖЕТ** иметь `--output json` flag для structured output (как
  альтернатива human-readable).
- **МОЖЕТ** принимать TRAN tuning через `--t-stop` / `--t-step`;
  default — `t_stop = 10 / freq`, `t_step = period / 100` (Analyze A3).
- **НЕ ДОЛЖНА** включать визуализацию (ASCII-графики / Sixel — это
  T024 / T025, отдельные задачи).
- **НЕ ДОЛЖНА** делать parametric sweep / multi-point — это T022.
- **НЕ ДОЛЖНА** делать diff measurement / before-after — это T021.
- **НЕ ДОЛЖНА** делать phase margin — это **T153** (отдельный спек).
- **НЕ ДОЛЖНА** делать target-power calibration loop для thd —
  это T131 специализация (Analyze A1).

## 4. Success Criteria

- Agent в `efactory:linux` TUI на `se-amp-demo` (после T147 merge)
  получает корректные значения на все три measure-команды:
  - `gain --freq 1000 --mode small` → конечное число (dB и V/V),
    `f = 1000 Hz`. Для SE 6П14П типично 10–30 dB.
  - `gain --freq 1000 --mode large --v-in-peak 0.1` → RMS-based
    gain, может отличаться от small-signal value при approach к
    clipping.
  - `bandwidth` → пара (f_low, f_high), оба в Hz, для SE 6П14П
    типично `(20–40 Hz, 25–50 kHz)`.
  - `thd --freq 1000 --v-in-peak <V>` → THD% (single point), для SE
    6П14П типично 1–15% (зависит от выбранной OPT, V_in). Возвращает
    также `measured_power_w` — фактическая мощность в нагрузке,
    информационно.
- Каждый measure-call < 30 s runtime на типичной фикстуре (SE amp,
  AC sweep 1 Hz – 1 MHz, dec=10 → ~70 точек; TRAN 100 ms, dt=1us
  → 100k samples).
- Все 5 pre-push gates зелёные (ruff / format / mypy / lint-imports
  3/3 KEPT / pytest); coverage ≥ 80% на новом коде.
- Acceptance тесты: ≥ 1 happy-path тест на каждый measure type +
  ≥ 1 unhappy (signal not found / convergence failure / multiple
  V-sources без `--input-source`).
- Use case'ы programmatically callable из других use case'ов
  (validation для будущих T021 / T022) — без CLI-shell-out.
- `--output-signal v(load)` работает по умолчанию на `se-amp-demo`
  (Q-F → a); при отсутствии node — error с подсказкой передать
  `--output-signal v(<node>)`.

## 5. Key Entities

Три **независимых** Pydantic VO (Q-A → b: discriminated union'а нет):

- **`GainMeasurement`** — `value_db: float`, `value_linear: float`,
  `frequency_hz: float`, `mode: Literal['small', 'large']`,
  `input_signal: str`, `output_signal: str`, `v_in_peak: float | None`
  (только для `mode='large'`).
- **`BandwidthMeasurement`** — `f_low_hz: float`, `f_high_hz: float`,
  `bandwidth_hz: float` (= f_high - f_low), `ref_db: float` (например
  -3.0), `midpoint_db: float`, `midpoint_source: Literal['auto',
  'ref_freq']`, `ref_freq_hz: float | None`, `passband_signal: str`,
  `input_signal: str`.
- **`ThdMeasurement`** — `thd_percent: float`, `fundamental_hz: float`,
  `v_in_peak: float`, `measured_power_w: float`, `dominant_harmonic_n:
  int`, `dominant_harmonic_percent: float`, `signal: str`,
  `n_harmonics: int`. **Строится из `FourierResult`** (готовое VO в
  `domain/simulation.py`) — extraction + enrichment с v_in_peak /
  dominant-harmonic logic (Analyze A8).

Из `domain/sim_results.py` расширяется enum `AnalysisType` **двумя**
значениями: `gain`, `bandwidth`. `THD = 'thd'` уже существует в
T016 enum'е (Analyze A6) — используем его. SimResult JSON
serialisation (Q-I → a) использует существующий `metrics: dict[str,
Any]` (T016 — Any, не float) для всех VO-полей включая string'и
и enum'ы.

Все signal-поля используют SPICE-нотацию: `v(<node>)` для напряжений,
`i(<element>)` для токов (Analyze A5) — передаются в ngspice script
напрямую.

## 6. Assumptions & Constraints

- **`Simulator` port** (ngspice) уже есть и протестирован — для всех
  трёх measure нужны AC / TRAN+Fourier выходы, которые он умеет.
- **Single-input источник в схеме.** Большинство наших фикстур имеют
  ровно один V-source. Auto-detect через парсинг netlist'а (top-level
  `^V\w+` строки, исключая subckt-internal — Analyze A4); реализация
  переиспользует существующий V-source парсер из
  `adapters/outbound/ngspice/netlist_substitution.py`.
- **Output node** определяется флагом `--output-signal v(<node>)`.
  Default — `v(load)` для audio-схем (Q-F → a).
- **Path argument auto-detection.** Positional `<path>` — если
  `.kicad_sch`, запускается design-to-netlist→measure pipeline; если
  `.cir`/`.spice` — напрямую (Analyze A12).
- **THD на single freq** — независимый use case (Q-D → b): TRAN +
  ngspice `fourier` через тот же `Simulator` interface, без зависимости
  на `MagneticComponent` / saturable. Строит `ThdMeasurement` из
  `FourierResult` extraction.
- **Small-signal gain через AcAnalysis с n_points=2.** Текущий
  `AcAnalysis` validator требует `f_stop > f_start`. Single-point
  workaround: `f_start = f, f_stop = f * 1.0001, n_points = 2`,
  берём первый результат (Analyze A2). Альтернатива — ослабить
  validator (≥), но трогать существующий contract без других нужд не
  оправдано.
- **AC source modifier auto-injection.** ngspice AC analysis требует
  чтобы V-source имел `AC <magnitude>` модификатор; наши tube-amp
  фикстуры (включая `_build_se_amp`) имеют только `SIN(...)`-form для
  TRAN, без AC modifier. Решение (Phase B mid-decision 2026-05-26,
  вариант 1): **`NetlistEditor` port extended** методом
  `ensure_ac_modifier(source_ref, ac_magnitude=1.0)` — идемпотентная
  injection. Use case'ы `measure_gain --mode small` и
  `measure_bandwidth` auto-инжектируют `AC 1` перед запуском AC analysis.
  Фикстуры не трогаем; semantics «small-signal = AC analysis» сохранена.
- **TRAN default'ы для large-gain и thd:** `t_stop = 10 / freq`
  (10 циклов, settle time), `t_step = (1 / freq) / 100` (Nyquist
  100× oversample). Caller перекрывает `--t-stop` / `--t-step`
  (Analyze A3).

## 7. Out of Scope

- **Phase margin** — отдельная задача **T153** (Q-B → c, заведена в
  BACKLOG 2026-05-26). Open-loop SE/PP (наш базовый use case) phase
  margin не имеют; для feedback-схем нужен явный loop-cut с собственным
  спеком и фикстурой.
- **Визуализация** (ASCII-графики через plotext / Sixel render) — T024,
  T025.
- **Parametric sweep** с метриками в таблице — T022.
- **Auto-delta до/после edit'а** — T021.
- **Multi-point / sweep по всем measure'ам сразу** — phase 2-pattern,
  явно out of T023.
- **Tube-specific специальные measure'ы** (anode dissipation, optimal
  load, headroom) — отдельные задачи Phase 4-5.

## 8. Phase plan (implementation)

Каждая фаза = одна сессия, отдельный commit (squash в один при merge).

- **Phase A — domain + AnalysisType extension.** Три VO в
  `domain/measurement.py` (новый module) с unit-тестами; добавить
  `GAIN`, `BANDWIDTH` в `AnalysisType` enum + миграционные правки
  T016 (если нужны). Coverage 100% на новом domain.
- **Phase B — use cases с fake-Simulator.** Три use case'а в
  `application/measure_*.py`. Outside-in TDD: тест с fake `Simulator`
  port'ом, dependency через DI. Расширения V-source-парсера в
  `adapters/outbound/ngspice/netlist_substitution.py` (если
  переиспользуем).
- **Phase C — CLI bindings + e2e.** `bridge measure <type>` sub-Typer
  в `adapters/inbound/cli/app.py`. E2e тесты с real ngspice subprocess
  на `se-amp-demo` фикстуре (после T147 merge). `--output json` flag.
- **Phase D — Claude Code slash-команды + docs.** Три slash-команды
  `/measure-gain`, `/measure-bandwidth`, `/measure-thd` в
  `docker/runtime-agent-commands/` (per T014 паттерн).
  CHANGELOG `[Unreleased]`, README quick-start update; mention
  «после merge — docker build + одноразовый `--reset-claude-state`».

---

## Clarify (заполняется Гвидо)

### Resolved (с ответами)

Все 10 вопросов разрешены 2026-05-26 ответом Vladimir-а «по
рекомендации» — выбран мой предварительный голос по каждому. Сводка:

| ID | Решение | Влияние |
|----|---------|---------|
| **Q-A** | (b) Три **независимых** VO, без discriminated union'а. | `Measurement`-union не вводим. SimResult JSON — раздельно по `analysis_type`. |
| **Q-B** | (c) **Phase margin вынесен в T153** (BACKLOG, отдельный спек, когда появится feedback-фикстура). | Phase 0 T023 = только gain + bandwidth + thd. Q-E автоматически закрыт. |
| **Q-C** | (c) `gain` — оба mode'а через `--mode small|large` (default small). | Один use case `measure_gain(mode=...)`, не два. |
| **Q-D** | (b) `measure_thd` — **независимый use case**, не wrapper T131. | TRAN + ngspice `fourier` через `Simulator`, без `MagneticComponent` / saturable. Работает на arbitrary netlist'е. |
| **Q-E** | n/a (закрыт Q-B). | — |
| **Q-F** | (a) Default `--output-signal v(load)`. | Error при missing node → message «pass --output-signal v(<node>)». |
| **Q-G** | (c) Auto-detect single V-source; ambiguity → error со списком кандидатов. | Не требует `--input-source` в 90% случаев. |
| **Q-H** | (c) `--ref auto` (default, midband = max\|H(f)\|) или `--ref-freq <Hz>`. | API: один enum + optional value. |
| **Q-I** | (a) Persistence в `.efactory/sim-results/` через `SimResultsRepository` T016. | `AnalysisType` enum расширяется: `gain`, `bandwidth`, `thd-single`. |
| **Q-J** | (a) Sub-Typer `bridge measure <type>`. | Slash-команды (T014) — flat hyphenated `/measure-<type>`. |

**Сторонний эффект** — заведена задача **T153** в BACKLOG (отдельный
PR не нужен — пишем прямо в этом же T023 PR, так как T023 спека
ссылается на T153 в Out of Scope и Связанных документах).

---

## Analyze (заполняется Гвидо)

Analyze pass 2026-05-26: 12 issues найдено, **1 Critical** разрешён
in-spec до начала implementation; 4 Warning'а — отражены в FR /
Assumptions, не блокируют (имплементация прямолинейна); 7 Note'ов —
руководства для реализатора без spec-правок. Detailed list:

### 🔴 Critical — все разрешены в spec'е

- **A1. `--power` vs `--v-in-peak` несогласованность в THD-interface.**
  Изначальный draft показывал в Сценарии C `thd ... --power 1.0`
  (target output power, Watts), а в Success Criteria — `--v-in-peak
  <V>` (input voltage amplitude). Это два разных stimulus-режима:
  `--power` требует calibration loop (T131 паттерн), `--v-in-peak`
  — deterministic single TRAN. По Q-D (THD independent от T131)
  выбран **только `--v-in-peak`** — calibration loop тянет половину
  T131 complexity, что противоречит «независимому use case».
  **Резолюция:** Сценарий C, FR, Success Criteria, Out of Scope
  обновлены — `--v-in-peak` everywhere; target-power calibration
  явно out of scope. `measured_power_w` остаётся в `ThdMeasurement`
  как информационное поле.

### 🟡 Warning — отражены в spec'е

- **A2. Small-signal AcAnalysis с n_points=2.** Существующий
  `AcAnalysis` validator требует `f_stop > f_start` (строгое
  неравенство). Для single-point gain (`--mode small`) workaround:
  `f_start = f, f_stop = f * 1.0001, n_points = 2`, берём первое
  значение. Альтернатива — ослабить validator до `≥`, но трогать
  существующий contract без других мотивов scope discipline
  запрещает. **В spec §6 Assumptions** добавлен явный note.
- **A3. TRAN default'ы для large-gain и THD.** Spec изначально
  не указывал `t_stop` / `t_step`. Audio-standard: 10 циклов
  settle + Nyquist 100× oversample → `t_stop = 10 / freq`,
  `t_step = period / 100`. Caller перекрывает `--t-stop` / `--t-step`.
  **В spec §3 FR + §6 Assumptions** добавлен явный note.
- **A4. V-source auto-detection — какой парсер?** Regex `^V\w+`
  по top-level строкам netlist'а с фильтрацией subckt-internal
  (между `.subckt`/`.ends`). Реализация — **переиспользовать**
  существующий парсер из
  `adapters/outbound/ngspice/netlist_substitution.py` (там работа с
  `SinSourceLine`), не писать новый. **В spec §6 Assumptions** —
  явный note.
- **A12. Schematic vs netlist — positional path с extension auto-
  detection.** `.kicad_sch` → design-to-netlist pipeline; `.cir` /
  `.spice` → напрямую. **В spec §6 Assumptions** — явный note.

### 🟢 Note — руководства реализатору без spec-правок

- **A5. SPICE-нотация `v(<node>)` для signal-полей.** Зафиксировано
  в Key Entities — все signal-поля хранят SPICE-string как есть
  (`v(load)`, `i(v1)`), передаются ngspice'у напрямую. Не parseable
  identifier.
- **A6. `AnalysisType.THD` уже существует в T016 enum'е.** Расширять
  enum только двумя значениями (`GAIN`, `BANDWIDTH`), не тремя.
  Зафиксировано в Key Entities.
- **A7. `metrics: dict[str, Any]` (не float) — `T016` flexibility.**
  Все VO-поля (включая string-enums, list'ы harmonics) сериализуются
  без специального treatment'а. Зафиксировано в Key Entities.
- **A8. `ThdMeasurement` строится из `FourierResult`.** Use case
  делает extraction + enrichment (dominant-harmonic logic). При
  имплементации — посмотреть на T131
  (`analyze_distortion_spectrum.py`), там dominant-extraction логика
  уже есть, можно скопировать pattern. Зафиксировано в Key Entities.
- **A9. `--freq` required для gain/thd.** Зафиксировано в FR.
- **A10. `--f-low / --f-high` default'ы для bandwidth.** Default
  `(1, 1e6)` audio envelope. Зафиксировано в FR.
- **A11. Phase plan.** Четыре phase A→B→C→D, каждая ≈ 1 сессия.
  Добавлен §8 в spec.
- **A8b (под номером A8). FourierResult reuse.** При имплементации
  Phase B — assert'нуть что `domain/simulation.py:FourierResult`
  достаточно богат (есть `thd_percent`, `harmonics` tuple) — да,
  достаточен; никаких domain-extension'ов под T023 не требуется.
