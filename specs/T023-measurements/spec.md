# Spec: Измерения как отдельные bridge-инструменты (gain / bandwidth / THD / phase margin)

**Статус:** Draft
**Дата создания:** 2026-05-26
**Связанные документы:**
- `BACKLOG.md → ### Фаза 2 → T023`.
- `domain/simulation.py` — `AcAnalysis` / `TranAnalysis` / `FourierAnalysis` /
  `AcSweep` / `FourierResult` / `TimeSeries` (готовая инфраструктура).
- `application/analyze_distortion_spectrum.py` — T131 saturable THD sweep
  (рядом, но не overlap: T131 — sweep по (freq, power) с saturable
  injection; T023 — одиночная точка/диапазон на as-is netlist'е).
- `application/bridge_sweep.py` — T022 candidate (parametric sweep).
- T021 (BACKLOG) и T022 (BACKLOG) — оба упираются в T023 как фундамент.

---

## 1. Overview

`efactory bridge measure <type>` — четыре одиночных «измерителя» поверх
готового SPICE-netlist'а: **gain**, **bandwidth**, **THD**, **phase
margin**. Каждый возвращает одно число (или малую структуру) + точку или
диапазон, в которой измерение зафиксировано (например, gain = 14.3 dB
при `f = 1 kHz`; bandwidth = 25 Hz – 35 kHz по `-3 dB` от пассбанд-
midpoint).

Цель — выделить «инструменты-наблюдатели» в самостоятельные use case'ы.
Это нужно как для прямого использования агентом («какой у этой схемы THD
на 1 кГц при 1 Вт?»), так и как **фундамент** для двух следующих задач
Фазы 2: T021 (`bridge_edit_and_resim` с auto-delta по метрикам) и T022
(parametric sweep с метриками в таблице).

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
  при 1 W output. Вызывает `efactory bridge measure thd <schematic>
  --freq 1000 --power 1.0` → THD %, доминирующий harmonic, frequency.
- **Сценарий D (T021 prerequisite, programmatic).** Use case
  `bridge_edit_and_resim` после edit'а netlist'а зовёт `measure_gain`
  + `measure_thd` ДО и ПОСЛЕ, вычисляет delta. Use case-уровневая
  reuse, не CLI re-shell.
- **Сценарий E (T022 prerequisite, programmatic).** Parametric sweep
  для каждой combination'и зовёт нужные `measure_*` use cases и
  кладёт значения в строку таблицы.

## 3. Functional Requirements

- **ДОЛЖНА** предоставить четыре отдельных use case'а в `application/`
  и четыре CLI subcommand'а под `efactory bridge measure …`:
  `gain`, `bandwidth`, `thd`, `phase-margin`.
- **ДОЛЖНА** каждый use case возвращать структурированный VO с
  числовым значением + контекстом (frequency / range / harmonic
  number и т.п.), а не голым `float`.
- **ДОЛЖНА** работать с готовым `.kicad_sch` (через тот же путь, что
  `sim-run`) ИЛИ с готовым SPICE-netlist'ом — единый интерфейс.
- **ДОЛЖНА** не требовать модификации схемы для измерения (никакого
  injecting источников / нагрузок сверх того, что caller явно
  попросил через флаги).
- **ДОЛЖНА** опираться на существующую инфраструктуру `Simulator`
  port'а; ни один measure не пишет собственный subprocess-wrapper над
  ngspice.
- **ДОЛЖНА** опционально писать `SimResult` (через тот же
  `SimResultsRepository` из T016), если caller передал repository
  (выравнивается с `sim_run` поведением).
- **МОЖЕТ** иметь `--output json` flag для structured output (как
  альтернатива human-readable).
- **НЕ ДОЛЖНА** включать визуализацию (ASCII-графики / Sixel — это
  T024 / T025, отдельные задачи).
- **НЕ ДОЛЖНА** делать parametric sweep / multi-point — это T022.
- **НЕ ДОЛЖНА** делать diff measurement / before-after — это T021.

## 4. Success Criteria

- Agent в `efactory:linux` TUI на `se-amp-demo` (после T147 merge)
  получает корректные значения на все четыре measure-команды:
  - `gain --freq 1000` → конечное число (dB или V/V), `f = 1000 Hz`.
  - `bandwidth` → пара (f_low, f_high), оба в Hz, для SE 6П14П
    типично `(20–40 Hz, 25–50 kHz)`.
  - `thd --freq 1000 --power 1.0` → THD% (single point), для SE
    6П14П типично 1–15% (зависит от выбранной OPT, V_in).
  - `phase-margin` — для feedback-схем (если включена в Phase 0);
    для open-loop SE может вернуть «not applicable» / специальный
    enum.
- Каждый measure-call < 30 s runtime на типичной фикстуре (SE amp,
  AC sweep 1 Hz – 1 MHz, dec=10 → ~70 точек; TRAN 100 ms, dt=1us
  → 100k samples).
- Все 5 pre-push gates зелёные (ruff / format / mypy / lint-imports
  3/3 KEPT / pytest); coverage ≥ 80% на новом коде.
- Acceptance тесты: ≥ 1 happy-path тест на каждый measure type +
  ≥ 1 unhappy (signal not found / convergence failure / empty
  result).
- Use case'ы programmatically callable из других use case'ов
  (validation для будущих T021 / T022) — без CLI-shell-out.

## 5. Key Entities

- **`GainMeasurement`** — `value_db: float`, `value_linear: float`,
  `frequency_hz: float`, `input_signal: str`, `output_signal: str`.
- **`BandwidthMeasurement`** — `f_low_hz: float`, `f_high_hz: float`,
  `bandwidth_hz: float` (= f_high - f_low), `ref_db: float` (например
  -3.0), `midpoint_db: float`, `passband_signal: str`.
- **`ThdMeasurement`** — `thd_percent: float`, `fundamental_hz: float`,
  `target_power_w: float | None`, `measured_power_w: float | None`,
  `dominant_harmonic_n: int`, `dominant_harmonic_percent: float`,
  `signal: str`.
- **`PhaseMarginMeasurement`** — `margin_deg: float`, `crossover_hz:
  float`, `loop_signal: str`. Применимо только к feedback-loop
  схемам — open-loop SE/PP не имеют его в каноническом смысле
  (см. Clarify).
- **Discriminated union** `Measurement = Gain | Bandwidth | Thd |
  PhaseMargin` (или сохраняем как самостоятельные VO без union'а —
  см. Clarify Q-A).

## 6. Assumptions & Constraints

- **`Simulator` port** (ngspice) уже есть и протестирован — для всех
  четырёх measure нужны AC / TRAN+Fourier выходы, которые он умеет.
- **Single-input источник в схеме.** Большинство наших фикстур имеют
  ровно один `V_in` (sin / pulse / DC). Если их несколько — caller
  указывает через флаг.
- **Output node** определяется флагом (`--output-signal v(load)` /
  `v(out)` etc.). Default — `v(load)` для audio-схем.
- **Schematic ИЛИ netlist** — caller выбирает один. По умолчанию
  `bridge measure <type> <schematic.kicad_sch>` запускает
  design-to-netlist→measure pipeline; флаг `--netlist <file.cir>`
  работает напрямую с готовым netlist'ом.
- **THD на single freq** — упрощённая версия T131
  `analyze_distortion_spectrum` (один cell вместо sweep). Не
  reimplement — wrap'ит TRAN + ngspice `fourier` через тот же
  `Simulator` interface (см. Clarify Q-D).
- **Phase margin** — концептуально требует open-loop transfer function
  с feedback-loop break point. Для feedback-схем (op-amp, NFB tube
  amp) — стандартная процедура «cut the loop». Для open-loop SE/PP
  — не применимо. См. Clarify Q-E.

## 7. Out of Scope

- **Визуализация** (ASCII-графики через plotext / Sixel render) — T024,
  T025.
- **Parametric sweep** с метриками в таблице — T022.
- **Auto-delta до/после edit'а** — T021.
- **Multi-point / sweep по всем measure'ам сразу** — phase 2-pattern,
  явно out of T023.
- **Loop-cutting helpers / open-loop transfer function extraction для
  arbitrary схем** — phase margin для open-loop SE не имеет смысла;
  для feedback-схем — caller сам подсказывает loop break node
  (см. Clarify Q-E).
- **Tube-specific специальные measure'ы** (anode dissipation, optimal
  load, headroom) — отдельные задачи Phase 4-5.

---

## Clarify (заполняется Гвидо)

### Open questions

**Q-A. Объединять ли четыре `*Measurement` VO в discriminated
union `Measurement`?**

Контекст: они структурно разные (gain — единичное число; bandwidth —
пара чисел; THD — число + dominant harmonic; phase margin — число +
crossover). Каждый use case возвращает свой type — есть ли пользователь
у `Measurement` union'а?

- (a) Union с discriminator `type: Literal['gain'|'bandwidth'|'thd'|
  'phase_margin']` — единообразный return для будущего «multi-measure»
  endpoint и SimResult JSON serialisation.
- (b) Четыре независимых VO, caller знает, какой use case зовёт —
  return type однозначен.

Я голосую за **(b)**: каждый use case вызывается с конкретным intent'ом,
union ничего не даёт сверх (a) и усложняет type-narrowing у caller'а.
SimResult писать раздельно по `analysis_type` (т.е. `gain`, `bandwidth`,
`thd-single`, `phase-margin`) — это уже паттерн T016 (`AnalysisType`
StrEnum).

**Q-B. Какие именно measure'ы входят в Phase 0 (первая итерация)?**

Контекст: phase margin сложнее остальных трёх (требует loop-cutting и
open-loop transfer function extraction). Open-loop SE/PP — наш базовый
use case — phase margin **не имеет**.

- (a) Все 4 сразу в Phase 0. Phase margin для feedback-only схем,
  для open-loop возвращает `NotApplicable` enum.
- (b) Gain + Bandwidth + THD в Phase 0, Phase margin отложить в Phase 1
  с честным loop-cut механизмом (нужен hint от пользователя на
  loop break node).
- (c) Только Gain + Bandwidth + THD; Phase margin — отдельная задача
  T<NEW>, заведённая в BACKLOG для feedback-фазы.

Я голосую за **(c)**: phase margin для audio SE/PP без NFB не нужен;
для feedback-схем требует отдельной спеки и дисциплины loop-cut. Не
блокируем основной T023 ради него. Если ответ (a) — нужен design
для NotApplicable case.

**Q-C. `gain` — small-signal (AC, 1 frequency) или large-signal
(TRAN-based RMS Vout/Vin)?**

- (a) Small-signal AC (`AcAnalysis` с одной точкой `f`). Линейное
  приближение. Быстро, но не отражает clipping / saturation /
  tube compression.
- (b) Large-signal TRAN — caller задаёт `V_in_amplitude`, `freq`,
  `t_stop`, мы запускаем TRAN, считаем RMS Vin/Vout, делим. Реальный
  gain нелинейной схемы.
- (c) **Оба** через флаг `--mode small|large` (default small).

Я голосую за **(c)**: для типичного «какой у меня gain @ 1 kHz»
small-signal достаточно и быстро; для large-signal headroom-проверки
(«какой gain на peak 1 W output?») нужен large-signal mode. Один
use case с mode-параметром — не два разных.

**Q-D. THD — wrapper над T131 `analyze_distortion_spectrum` или
самостоятельный лёгкий use case?**

Контекст: T131 — sweep по (freq, power) cells через **saturable
injection** в OPT-aware netlist. Для single-point THD на arbitrary
netlist (не обязательно с OPT) saturable injection не нужен.

- (a) `measure_thd` — wrapper над T131 use case с `cells=[(freq,
  power)]`, передаёт ThdSpectrum с single point → возвращает
  `ThdMeasurement`. Reuse, но тащит saturable infrastructure (нужен
  `MagneticComponent` + `FrohlichBHCurve` даже если их в схеме нет).
- (b) `measure_thd` — независимый use case: TRAN + ngspice `fourier`
  на as-is netlist'е через `Simulator`. Не требует
  `MagneticComponent` / saturable. Использует тот же `FourierResult`
  domain VO.

Я голосую за **(b)**: T131 рождён для специфичной saturable-OPT
acceptance, его DI-граф нагружен. `measure_thd` должен работать на
любом netlist'е без знаний о магнитных компонентах. Это естественный
T131 «лёгкий брат».

**Q-E. Phase margin (если входит в Phase 0): как caller указывает
loop break?**

Контекст: phase margin = open-loop transfer at unity-gain frequency
minus 180°. Для feedback-схемы нужно «разорвать петлю» в одной точке,
снять transfer function в ней, найти crossover.

- (a) Caller передаёт `--loop-break-node <node>` — мы инжектируем
  AC stimulus в этой ноде и измеряем return.
- (b) Caller передаёт два signal'а: `--loop-input <signal_in>
  --loop-output <signal_out>` — мы считаем |Vout/Vin| и phase при
  AC sweep.
- (c) Отложить phase margin до отдельной задачи (см. Q-B вариант (c)).

Связано с Q-B. Если идём по (c) — этот вопрос отпадает.

**Q-F. `--output-signal` default — какой?**

- (a) `v(load)` — есть в наших audio-фикстурах (R_load).
- (b) `v(out)` — generic-name, требует переименования в фикстурах.
- (c) Caller всегда указывает явно — никаких default'ов; CLI fail
  без флага.

Я голосую за **(a)** — в наших фикстурах action рабочий сигнал
сидит на `v(load)`; default уменьшает friction. Если нет — error
с подсказкой «pass --output-signal v(node)».

**Q-G. Input signal source — как находить?**

- (a) Default `V_in` (имя источника); caller перекрывает `--input-
  source V_<name>`.
- (b) Caller всегда указывает явно.
- (c) Auto-detect: если в схеме ровно один V-source — берём его;
  больше одного — error.

Я голосую за **(c)** — это устраняет default'ы для нестандартных
имён и одновременно избавляет от ручного указания в 90% случаев.
Error при ambiguity → подсказка списка V-source'ов.

**Q-H. Bandwidth — пассбанд auto-detect или caller указывает?**

Контекст: `-3 dB` относительно чего? Стандарт — относительно midband
gain. Midband = максимум АЧХ в типичном случае, но не всегда (например,
гитарные усилители с deliberately bumpy АЧХ).

- (a) Auto: midband = `max(|H(f)|)` по sweep, ref = `midband - 3 dB`.
- (b) Caller передаёт `--ref-freq <Hz>` — midband = `|H(ref_freq)|`,
  стандартно 1 kHz для audio.
- (c) Оба варианта (flag): `--ref auto` (default) / `--ref-freq <Hz>`.

Я голосую за **(c)**: auto — sane default для 80% случаев, ref-freq
— escape hatch для bumpy responses. Минимальный overhead в API.

**Q-I. Persistence в `.efactory/sim-results/`?**

Контекст: T016 `sim_run` пишет SimResult JSON в `<PROJECT>/.efactory/
sim-results/<TS>-<analysis>.json` через `SimResultsRepository` (если
caller передал repository + project_root). Согласованность поведения
для measure_*?

- (a) Да: каждый measure_* принимает optional `sim_results_writer`
  + `project_root` (как `sim_run`); пишет JSON с `analysis_type=
  gain|bandwidth|thd|phase-margin`.
- (b) Нет: measure_* — read-only «инспектор», результат только в
  return value / stdout.

Я голосую за **(a)** — agent benefits от persistent истории всех
measure'ов: SessionStart hook (T016) показывает «последние 3 sim-
результата», включая measure'ы; T021 (delta до/после) тоже может
читать JSON для baseline. AnalysisType enum в T016 — расширяемая.

**Q-J. CLI nesting — `bridge measure <type>` (sub-Typer) или flat
`bridge measure-<type>`?**

- (a) Sub-Typer: `bridge measure gain ...`, `bridge measure thd ...`.
  Структурно, аналог `bridge sim-run op|tran|ac`.
- (b) Flat: `bridge measure-gain ...`, `bridge measure-thd ...`.

Я голосую за **(a)** — гомогенно с уже существующим `bridge sim-run
<type>`. Slash-команда `/measure-<type>` в Claude Code (T014) при
этом будет flat (hyphenated per Analyze A1 T014), что нормально —
slash-команды transpile'ятся в CLI calls.

### Resolved (с ответами)

- ...

---

## Analyze (заполняется Гвидо)

- ...
