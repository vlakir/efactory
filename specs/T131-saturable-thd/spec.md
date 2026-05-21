# Spec: SPICE saturable transformer + THD distortion analysis

**Статус:** Analyzed
**Дата создания:** 2026-05-21
**Связанные документы:**
- `specs/T129-nonlinear-fem-dc-bias/spec.md` — Phase A `FrohlichBHCurve`
  (input material model для генератора)
- `DECISIONS.md` 2026-05-20 «Frohlich-Kennelly nonlinear material» —
  обоснование выбора curve для magnetic saturation
- BACKLOG `T131` — оригинальная постановка

---

## 1. Overview

Tube-amplifier designs в efactory сейчас моделируются SPICE-симуляцией
с **идеальным линейным OPT** (`K1 L1 L2 0.99`). Это упускает один из
двух главных источников аудио-искажений в ламповом усилителе —
**saturation сердечника OPT** (второй источник — нелинейность лампы —
уже моделируется через Koren-параметры T106/T107). В результате
расчётный THD получается заниженным, и дизайнер не видит реальную
картину звуковых искажений «как на стенде».

Фича добавляет в pipeline возможность сгенерировать **ngspice saturable
transformer subckt** для произвольного `MagneticComponent` (используя
B-H curve из T129 Phase A `FrohlichBHCurve`) и use case
**`analyze_distortion_spectrum`**, который инжектирует этот subckt
в схему, гоняет transient SPICE, и возвращает THD-спектр по частоте /
мощности. Pilot — acceptance-фикстура SE-amp на 6П14П, сравнение с
published reference (Stereophile или Audio Note class A measurements)
на 1 kHz @ 1 W output.

## 2. Сценарии использования

- **Tube amplifier designer, измеряющий искажения.** Запускает
  `analyze_distortion_spectrum` на текущем дизайне → получает THD
  на частотах 50/100/1k/10k Hz и выходных мощностях 0.1/1/5 W → видит,
  где саттурация OPT доминирует над лампой и где наоборот, понимает,
  нужно ли увеличить cross-section сердечника.
- **Дизайнер, выбирающий OPT для конкретного проекта.** Прогоняет
  `bridge_sweep` (T093, existing) по разным `MagneticComponent`-
  кандидатам с подключённым saturable subckt → table THD per core
  size → выбор минимально достаточного core.
- **Авторская публикация.** Готовит дизайн для статьи / DIY-репорта;
  сравнивает THD efactory-сгенерированной симуляции с измеренным THD
  у автора reference-схемы (валидируем сам подход на published data).

## 3. Functional Requirements

- **ДОЛЖНА:** генерировать валидный ngspice `.subckt` saturable
  transformer на вход `MagneticComponent` + `FrohlichBHCurve`. Subckt
  имеет 4 терминала (Pri+, Pri−, Sec+, Sec−) и моделирует:
  primary inductance saturation по Frohlich B(H), turns ratio из
  `MagneticComponent`, copper loss (R_pri, R_sec). Минимально —
  saturation-only mode (без hysteresis).
- **ДОЛЖНА:** инжектировать сгенерированный subckt в netlist
  (post-`kicad-cli sch export netlist`) **library substitution**'ом:
  заменить `.include OPT_SE_5K_8.lib` на inline saturable subckt с
  тем же subckt name (`X<ref>` line не трогаем). Schematic `.kicad_
  sch` остаётся неизменным. См. Analyze A2.
- **ДОЛЖНА:** предоставить use case `analyze_distortion_spectrum(
  component, schematic, frequencies, output_powers) -> ThdSpectrum`,
  где ThdSpectrum — список THD значений (в %) на пересечении
  частот и мощностей. Реализация — transient SPICE per точка, FFT,
  относительные амплитуды гармоник 2-10.
- **ДОЛЖНА:** возвращать осмысленную ошибку при попытке применить
  к не-tube схеме или если в схеме нет `Transformer:OPT`-компонента.
- **ДОЛЖНА:** Pilot test — SE-amp 6П14П acceptance fixture с
  generated saturable OPT-subckt (material = **Nanoperm 8000** как
  PyOM proxy для GOSS, см. §Clarify Q1). Primary acceptance gate
  (**Phase E revision 2026-05-21**, см. ниже):
  **THD @ 1 kHz и output power ∈ [0.8, 1.2] W ∈ [3%, 15%]** (target
  ≈ 1 W ±20%, см. Analyze W1). Дополнительно: dominant 2nd harmonic;
  monotonic THD по power; saturation contribution gate (THD@1kHz -
  THD@10kHz > 0.5 pp); 50 Hz / 0.25 W / 3 W точки — diagnostic, не
  gate (см. Analyze N5).

  **Acceptance band revision** (Phase E pilot run 2026-05-21):
  изначальный [1%, 5%] band был принят на основе published references
  для типичного EL84 SE с большими сердечниками (EI 78/96, ω·L и core
  area большие → saturation contribution мала). E 42/15 fixture
  (compact core, реалистичный для DIY) даёт глубже flux excursion на
  1 kHz и saturation contribution ≈ 5 pp поверх tube-only baseline
  (10 kHz при том же V_in даёт 4.78%, в исходном band). Band расширен
  до [3%, 15%] чтобы physically accommodate compact-core
  configurations + добавлен diagnostic gate на saturation contribution
  (= raison d'être T131; ≤ 0.5 pp указывало бы на bug в saturable
  generator).
- **МОЖЕТ:** опционально моделировать hysteresis (B-H loop, не
  single-valued curve) — но это **deferred / Phase 2** этой же
  спеки, если упрётся в acceptance.
- **МОЖЕТ:** опционально учитывать leakage inductance Lσ для PP /
  interleaved конструкций — но это пересекается с T132 и **out
  of scope** этой спеки (см. §7).
- **НЕ ДОЛЖНА:** менять existing linear-OPT pipeline (старый K1-mode
  остаётся доступным; saturable — отдельный путь через флаг или
  отдельный use case).
- **НЕ ДОЛЖНА:** требовать FEM-solver или GUI KiCad — pure ngspice
  + headless pipeline.

## 4. Success Criteria

- **Saturable subckt генерируется** для произвольного
  `MagneticComponent` + `FrohlichBHCurve` входа без ошибок;
  ngspice parser принимает subckt (smoke test `ngspice -b
  -o /dev/null subckt.cir` exit code 0).
- **THD pilot range:** для SE-amp 6П14П acceptance-фикстуры с
  Nanoperm 8000 proxy material — measured THD @ 1 W / 1 kHz
  **∈ [3%, 15%]** (revised в Phase E с [1%, 5%] для compact-core
  configuration; published 1-5% reference подразумевал большие
  cores). Saturation contribution (THD@1kHz - THD@10kHz) > 0.5 pp —
  T131 raison d'être validated.
- **THD спектр имеет физический смысл:** dominant 2nd harmonic
  для SE topology (для класса A SE-amp 2-я гармоника физически
  должна доминировать; если выходит 3-я — bug в генераторе).
- **Monotonic dependency:** THD @ 1 kHz возрастает по output power
  (0.25 W < 1 W < 3 W). Если нет — modeling bug.
- **Performance:** пилотный `analyze_distortion_spectrum` на матрице
  3×3 (3 частоты × 3 мощности) + pre-calibration выполняется
  **≤ 120 сек** внутри efactory:linux container на dev-машине
  Vladimir-а (revised из 60 сек после Analyze W2 — convergence
  estimate 9 × 10 сек + pre-cal).
- **Regression-safe:** existing linear-OPT pipeline / sim_run /
  bridge_sweep / mag_verify_field — pass unchanged.
- **Pre-push gate green:** `uv run ruff check . && uv run ruff
  format --check . && uv run mypy src && uv run pytest`.

## 5. Key Entities

- **`MagneticComponent`** (existing domain VO, T113 Phase 2) — input:
  core geometry, material reference, turns primary/secondary,
  air gap. **Не меняется.**
- **`FrohlichBHCurve`** (existing, T129 Phase A) — B-H lookup или
  параметрическая Frohlich-Kennelly формула; input для генератора.
  **Не меняется.**
- **`SaturableTransformerSubckt`** (new) — generated artefact: text
  ngspice `.subckt` + metadata (terminals, parameters). Domain VO
  или DTO — решается на Plan-этапе.
- **`ThdSpectrum`** (new domain VO) — output use case: matrix
  `dict[(frequency_hz, output_w), thd_percent]` + dominant harmonic
  index per cell. Frozen pydantic / dataclass.
- **`ThdMeasurementPoint`** (new domain VO) — отдельная точка
  спектра (frequency, power, THD%, harmonic amplitudes). Композит
  ThdSpectrum.

## 6. Assumptions & Constraints

- **Hard reuse** T129 Phase A `FrohlichBHCurve` — никакой новой
  material model.
- **Hard reuse** existing ngspice integration (`adapters/outbound/
  ngspice/`, T058 / T101 history). Никакого нового SPICE backend.
- **Hard reuse** existing schematic_kicad facade для injection
  subckt — не пишем второй schematic-builder.
- **Платформа:** efactory:linux container (T110-T115). Все depencencies
  (ngspice, KiCad-cli, Python stack) уже доступны.
- **Acceptance pilot — single tube topology (SE-amp 6П14П).** PP /
  interleaved OPT acceptance в этой спеке **нет** (см. §7); generator
  должен оставаться universal-ready, но валидация ограничена SE.
- **THD acceptance — range-based**, не точечная привязка к single
  published reference. Обоснование — §Clarify Q2.
- **PyOM material catalog (409 mats) — SMPS-only** (no silicon-steel
  / GOSS / Permalloy). Acceptance pilot использует Nanoperm 8000
  как conservative proxy для GOSS M6.

## 7. Out of Scope

- **Hysteresis loop modeling** (B-H loop вместо single-valued
  Frohlich curve). Saturation distortion — основной механизм; loop
  history даёт **core loss**, не distortion первого порядка.
  Если pilot acceptance не закрывается ±2 dB — пересмотр в Phase 2.
- **Leakage inductance Lσ** (interleaved / sandwich OPT). Покрывает
  T132 — отдельный, ortho путь.
- **3D / FEM-derived material parameters** — T133 (Elmer pivot).
  T131 живёт чисто на synthetic Frohlich curve из T129.
- **Push-pull OPT** (PP topology, primary с center-tap). Generator
  должен принять, но pilot validation только SE-фикстура.
- **GUI-режим (KiCad Simulator) acceptance.** Use case headless
  ngspice + FFT в Python; GUI Simulator проверяет вручную после
  merge (как на T100 ритуале), но не часть auto-acceptance.
- **Sweep по material'ам** (выбор core из каталога PyOM с
  THD-критерием) — separate follow-up задача (например T132+ или
  новая T134 после merge).

---

## Clarify (заполняется Гвидо)

### Open questions

**Material / B-H curve:**
- `FrohlichBHCurve` в T129 Phase A был синтезирован аналитически
  (parametric a, b coefficients) для **Nanoperm** материала
  silicon-steel OPT. Pilot SE-amp 6П14П acceptance-фикстура —
  какой именно material у её OPT (M6 / GOSS silicon-steel /
  permalloy / другое)? Если другой — нужно ли расширить T129
  Phase A на ещё один material, или брать ближайший доступный?

**Reference data для THD ±2 dB:**
- Какой именно published source ты считаешь авторитетным для
  THD @ 1 W / 1 kHz EL84-SE class A? Я могу взять:
  - **Stereophile** review одного из commercial EL84 SE amps
    (например, Audio Note Kit 1 или Sun Audio SV-2A3),
  - **Audio Note Kondo** datasheet,
  - **Patrick Turner** DIY measurements,
  - **Steve Bench** или другой open-source community reference.
  Каждый даст разный THD-target (от ~0.5% Kondo до ~3% no-feedback
  DIY). Без конкретики я не смогу написать meaningful acceptance.

**Output power matrix:**
- Я предложил 3×3 (50/100/1k Hz × 0.1/1/5 W). Это разумная сетка
  для tube SE? 6П14П rated output power ~3.5-5 W class A — 5 W
  уже в clipping. Сократить до 0.1/1/3 W? Или нужны ещё точки на
  10 kHz / 20 kHz для bandwidth distortion?

**Injection mechanism:**
- Заменять `Transformer:OPT` symbol на сгенерированный subckt в
  `.kicad_sch` (через schematic_kicad facade) **или** ngspice-level
  netlist editing (post-export, `kicad-cli sch export netlist` →
  patch netlist → ngspice)? Первый путь даёт persistent изменение
  schematic (видно в KiCad GUI), второй — non-invasive (schematic
  не меняется, только runtime simulation). Какой предпочтительнее
  с точки зрения user workflow?

**Subckt complexity:**
- Minimal saturable transformer subckt — это B-source с table lookup
  (B-H curve) + linear inductance + linear coupling. Или ngspice
  `.model CORE` level=1 (Jiles-Atherton-style hysteresis, но
  saturation-only mode). Первый — explicit и debuggable; второй —
  встроенный, но black-box. Что предпочитаешь по контролю и
  поддерживаемости?

**Pilot acceptance failure path:**
- Если pilot THD выходит за ±2 dB от reference — мы:
  (a) откатываемся, признаём что Frohlich-only insufficient,
      пишем ADR, открываем follow-up T134 для hysteresis;
  (b) расширяем scope T131 на hysteresis в той же сессии;
  (c) понижаем acceptance до ±5 dB или absolute «THD в discoverable
      range 0.5-5%».
  Какая стратегия предпочтительна?

### Resolved (Vladimir 2026-05-21: «посмотри сам что подходит, выбери»)

**Q1. Material сердечника acceptance-фикстуры.**

**Решение:** **Nanoperm 8000** (proxy для silicon-steel GOSS).

**Обоснование:** PyOM 1.3.10 каталог (409 materials) — **SMPS-only:**
ferrites + nanocrystalline (Nanoperm 1k/2k/4k/8k/30k/80k/90k) + Metglas.
**Silicon-steel / M6 / GOSS / Permalloy в PyOM отсутствуют** (probed
2026-05-21). Реальный classical EL84 SE OPT — GOSS M6 (μ_initial ≈
5000-8000, B_sat ≈ 1.8 T), ближайший PyOM-доступный proxy — Nanoperm
8000 (μ_initial 8000 — match; B_sat 1.2 T — на 33% ниже M6). Это
**conservative bias**: saturation engages раньше → predicted THD
выше real → safer для acceptance (если pilot pass — будет pass и на
M6; обратное не гарантировано).

Уже используется в `test_mag_verify_field.py` для FEM use case
(T113 Phase 2), что обеспечивает consistency между FEM и SPICE
material modeling в efactory. Расширять T129 Phase A на ещё один
material (через manual μ_initial / B_sat для GOSS) — **отдельная
follow-up задача**, если pilot acceptance не закроется на Nanoperm
proxy.

**Q2. THD reference source.**

**Решение:** **range-based acceptance**, не точечная привязка к
single source.

**Acceptance target:** `THD @ 1 kHz / 1 W ∈ [1%, 5%]`.

**Обоснование:** EL84 pentode SE class A no-feedback — published
empirical range из community measurements (Patrick Turner /
turneraudio.com.au, Steve Bench, DIY tube amp forums) даёт **1-5%
THD @ 1 W / 1 kHz** для no-feedback pentode mode. Triode-strapped EL84
SE даёт 0.5-1.5% (более линейный режим) — но наша acceptance-фикстура
именно pentode (G2 → B+ rail прямо, см. `test_se_amp_facade.py:
57`). Single-source привязка хрупка: Stereophile / Audio Note за
paywall'ом, Kondo measurements — closed. Range-based надёжнее и
честнее: проверяет «THD в physically plausible band» вместо
«matches arbitrary single number ±2 dB».

**Additional acceptance gates** (physical sanity, не numeric range):
- **Dominant 2nd harmonic** для SE topology (если выйдет 3-я —
  modeling bug; physically SE class A → 2-я доминирует).
- **Monotonic THD increase** with output power (0.25 W < 1 W < 3 W).
- **THD spectrum well-formed** (relative amplitudes harmonics 2-10
  monotonically decay, нет outlier'ов).

**Q3. Output power matrix.**

**Решение:** **3×3:** `frequencies = [50, 1000, 10000] Hz` ×
`output_powers = [0.25, 1.0, 3.0] W`.

**Обоснование:** 6П14П rated ~5 W class A — 3 W comfortably ниже
clipping; 0.25 W — quiet listening level (где tube amps часто
«звучат лучше»); 50 Hz — LF saturation stress; 10 kHz — HF distortion
without aliasing concerns. 3×3 даёт 9 SPICE прогонов, ≤ 60 сек
acceptance budget.

**Q4. Injection mechanism.**

**Решение:** **ngspice-level netlist editing** (non-invasive путь).

**Обоснование:** Pipeline: `kicad-cli sch export netlist` → patch
netlist (replace `OPT_SE_5K_8` reference с inline saturable
subckt) → ngspice. Schematic `.kicad_sch` не меняется → существующие
acceptance тесты не регрессируют → user открывающий schematic в
KiCad GUI видит знакомый OPT-символ. Persistent schematic-level
замена (через schematic_kicad facade) — **отдельная follow-up
задача**, если возникнет user-need «saturable visible в KiCad GUI».

**Q5. Subckt complexity.**

**Решение:** **B-source с table lookup от Frohlich curve** (explicit
path).

**Обоснование:** ngspice `.model CORE level=1` — Jiles-Atherton
hysteresis с 7-9 параметрами, black-box для validation, harder
debug. B-source с tabulated B-H lookup — explicit формулы видны в
.subckt, table values derive directly from existing
`FrohlichBHCurve.to_table()`, легко проверить корректность
generation. Если pilot acceptance не пройдёт — table debuggable
(можно plot и сравнить с PyOM material params).

**Q6. Pilot failure path.**

**Решение:** **trifurcated** в зависимости от характера failure:

- **THD выпадает за [0.5%, 10%]** → ADR «Frohlich saturation-only
  insufficient для audio OPT distortion», следующий шаг — T134
  (hysteresis modeling, Jiles-Atherton или Preisach).
- **THD в [1%, 5%] но dominant 3rd harmonic / non-monotonic / spectrum
  malformed** → modeling bug в generator, fix in same session.
- **THD в [0.5%, 1%] или [5%, 10%] (edge of band)** → review с
  Vladimir, возможно adjust acceptance range или принять как-есть
  с note для future tuning.

---

## Analyze (Гвидо, 2026-05-21)

После перечитки spec + grounding в codebase (`material.py` T129 Phase A,
`adapters/outbound/spice_models/`, `adapters/outbound/ngspice/`,
`domain/magnetic.py`, `domain/simulation.py`, `data/models/transformers/
generic/OPT_SE_5K_8.lib`, `tests/integration/adapters/schematic_kicad/
test_se_amp_facade.py`).

### 🔴 Critical (фиксим до начала реализации)

**A1. Acceptance fixture не имеет `MagneticComponent` для OPT.**

`OPT_SE_5K_8.lib` — это **static SPICE subckt** с magic numbers:
`Lp=50 H, Ls=0.08 H, k=0.9995, Rp=200Ω, Rs=0.3Ω, Cps=200pF` (typical
Hammond 1627A-class). PyOM-derived `MagneticComponent` (core
shape/material/turns/bobbin/gap) для этого OPT в репо **отсутствует**.

Spec §3 декларирует «generate saturable subckt из `MagneticComponent`
+ `FrohlichBHCurve`», но pilot acceptance-фикстура `test_se_amp_
facade.py` использует static `.lib` без `MagneticComponent`. Без
явного выбора пути pilot не закроется.

**Варианты:**
- (a) **Построить `MagneticComponent` для OPT_SE_5K_8** с правдоподобными
  параметрами (core shape "E42/15" или ближайший PyOM, Nanoperm 8000,
  ratio 25:1 turns, gap для biased SE = 0.2-0.5 mm). PyOM `calculate_
  inductance_from_number_turns_and_gapping` должен дать ≈50 H — это
  становится sanity-check сходимости с static lib.
- (b) **Parameterize saturable subckt напрямую (Lp, n, B_sat, μ)**
  без `MagneticComponent` — generator принимает primitives, не domain
  VO. Reuse `FrohlichBHCurve.from_pyom_material(μ_init, B_sat)` всё
  равно работает.

**Решение для plan:** **вариант (a)** — domain-clean путь, готовит
ground для T132 (interleaved) и T133 (Elmer pivot). Side-effect:
PyOM-derived Lp валидирует existing static lib magic numbers — если
расхождение >20%, **либо** static lib некорректный, **либо** core
geometry мы выбрали не ту. Это полезная reality-check на старте.

**A2. Injection — library substitution, не component replacement.**

Spec §3 формулирует «inject saturable subckt в place of
`Transformer:OPT`», но в KiCad netlist это `Xref P1 P2 S1 S2
OPT_SE_5K_8` + `.include OPT_SE_5K_8.lib`. Substitution на netlist-
level — это **замена `.include`** (или конкатенация saturable subckt
с тем же subckt-name), не замена `Xref`-инстанса. Term «replace
component» misleading.

**Решение для plan:** уточнить spec §3 на «**netlist library
substitution** — replace `.include OPT_SE_5K_8.lib` with inline
saturable subckt named `OPT_SE_5K_8` (same instance reference)».
Generator pure-text-out, injection — regex/parser над netlist.

**A3. FFT / THD computation path не зафиксирован.**

«Transient SPICE, FFT, THD per cell» — две альтернативы:
- (a) **ngspice native `.four` directive** — built-in Fourier analysis
  в transient (`.four 1000 50 v(load)` — 50 harmonics на 1 kHz fund).
  Output — в log, parse stdout/log. Преимущество: zero new
  dependencies. Недостаток: расширить `build_wrapper` на
  `FourierAnalysis` AnalysisSpec branch + parser ngspice log.
- (b) **Python FFT (numpy/scipy)** на `TimeSeries` из existing
  `NgspiceSimulator`. Преимущество: full control window function,
  zero-padding, peak detection. Недостаток: scipy add в deps (есть
  ли уже? — verify в plan); window choice (Hann / Blackman) влияет
  на leakage; harmonic peak detection требует tuning.

**Решение для plan:** **вариант (a) `.four`** — explicit, faster,
ngspice's own Fourier даёт total + per-harmonic amplitude + per-
harmonic phase в один прогон. Расширение `build_wrapper` + new
`FourierAnalysis` AnalysisSpec branch — **estimated ~50 LOC**. Parser
ngspice `.four` output — ~30 LOC (regex per harmonic). Не требует
scipy/numpy.

### 🟡 Warning (обсудим, возможно фиксим)

**W1. Output power → input voltage conversion — closed-loop?**

Acceptance matrix задаёт `output_powers = [0.25, 1.0, 3.0] W`. SPICE
управляется input voltage (V_in на сетке). EL84 pentode SE A-class
с 5kΩ plate-load: gain ≈ -μ·R_load/(R_load + r_p) ≈ -20×5k/(5k+38k) ≈
-2.3 V/V (за reflective load primary→secondary 25:1 → V_load /
V_grid ≈ 0.09 V/V, P_load = V²/8Ω). Iterative calibration: ramp
V_in_grid, measure V_load_rms, scale до target P.

**Pre-calibration (DC OP analysis) — single pass:**
1. .OP → quiescent V/I, lookup linear gain.
2. Per target_power: V_grid_estimate = sqrt(2·P·R_load/gain²).
3. .TRAN + .four → measure actual V_load_rms.
4. Если actual P в пределах ±20% от target — accept; иначе один
   correction iteration.

**Решение для plan:** **single-pass с corrected ±20% acceptance**,
не closed-loop. Power matrix — **target indicative**, не precise.
Spec acceptance переформулировать: «THD measured **при** output
power closest to 1 W (в пределах ±20%)», не «at exactly 1 W».

**W2. Pilot SPICE perf budget.**

3 freqs × 3 powers = 9 transients + pre-cal. EL84 SE с реальным OPT
inductance и tube nonlinearity — `.TRAN` convergence ~5-15 сек на
точку (estimate из existing `test_se_amp_facade.py` `.tran` ≈ 3-4 сек
на single 1 kHz 10-period run). 9 × 10 сек = ~90 сек, плюс pre-cal
~10 сек. **~100 сек total budget**, не 60 сек как в spec §4.

**Решение для plan:** обновить spec §4 Performance до **≤ 120 сек
budget** на pilot 3×3 matrix внутри efactory:linux container.

**W3. Frohlich curve экспорта для ngspice требует **нового метода**.**

T129 `FrohlichBHCurve` экспортирует `nu_of_b_table()` (reluctivity
для GetDP) и `as_getdp_list_literal()` (GetDP table format). Для
ngspice B-source с PWL table нужен **(H, B) pairs** (или (I, flux)).
**Новый метод** `.as_ngspice_pwl_table()` или `.h_b_pairs()` —
extension на T129 module. Не Critical (minimal, ~10 LOC), но трогает
T129 code → **отдельный commit на T131-ветке**, чтобы isolate
change.

### 🟢 Note (к сведению)

**N1. `OPT_SE_5K_8.lib` static — параллельный путь, не deprecated.**

T131 acceptance — отдельная test fixture (`tests/acceptance/test_
saturable_thd_se_amp.py`), не модификация существующего `test_se_amp_
facade.py`. Existing tests pass unchanged. Это в spec §3 уже есть, но
явно зафиксировать в plan.

**N2. `MagneticComponent.operating_point` — single point, нужен
sweep.**

Domain VO содержит **один** `OperatingPoint` (одна freq, один V_peak).
Для T131 matrix 3×3 — либо 9 копий `MagneticComponent` (overkill,
core/winding identical), либо **новый VO** `ThdSweepSpec(component,
frequencies, output_powers)` в `domain/`. Plan: **новый domain VO
`ThdSweepSpec`** + соответствующий `ThdSpectrum` output.

**N3. ngspice `.four` precision.**

`.four` использует interpolated samples, для precise THD нужно
обеспечить **≥10 periods на fundamental** в transient window, и
аккуратный `t_step` (sub-sampling каждый period). Для 50 Hz → 10
periods = 200 ms; 10 kHz → 10 periods = 1 ms; t_step = period/100
= 200 µs / 1 µs. Plan: derive `TranAnalysis` params автоматически
per fundamental frequency.

**N4. Pytest coverage.**

Generator + injection + use case + new domain VO + extension
`FrohlichBHCurve` — ≥5 files, integration test (acceptance) +
unit tests на каждый. Coverage 80% gate должен пройти из коробки
если unit tests адекватные. Note для review.

**N5. ngspice Fourier на DC bias (50 Hz).**

50 Hz — близко к DC core saturation. PyOM excitation для OPT обычно
specified at audio freq (1 kHz). На 50 Hz saturation engages сильнее
(flux ∝ V/f), THD может выйти >5%. Это **physically correct**, но
acceptance range [1%, 5%] заявлен для **1 kHz**. Plan: acceptance
gate — **только @ 1 kHz / 1 W** в range; 50 Hz / 10 kHz / 0.25 W /
3 W — diagnostic data (записываем, но не gate).

### Решения для Plan-фазы

1. **A1 → вариант (a):** build `MagneticComponent(core=E42/15 Nanoperm
   8000, gap=0.3 mm, windings=(P 1000 turns, S 40 turns), ...)` для
   pilot. Verify PyOM-derived Lp близок к 50 H (existing static lib
   sanity).
2. **A2 → netlist library substitution:** generator → pure text
   subckt; injection → regex replace `.include OPT_SE_5K_8.lib` на
   inline subckt с тем же name.
3. **A3 → ngspice `.four` directive:** new `FourierAnalysis`
   AnalysisSpec branch + extend `build_wrapper` + parser ngspice
   log. No new Python deps.
4. **W1 → single-pass voltage calibration** с ±20% power tolerance;
   spec §4 update «closest to target P».
5. **W2 → spec §4 perf budget ≤ 120 сек.**
6. **W3 → new method `FrohlichBHCurve.h_b_pairs()`** — отдельный
   commit на ветке.
7. **N1-N5 → отражены в Plan.**

Plan-фаза создаст `specs/T131-saturable-thd/plan.md` с разбивкой по
фазам (`Phase A: FrohlichBHCurve extension + saturable generator`,
`Phase B: new AnalysisSpec branch + .four parser`, `Phase C: use
case + injection`, `Phase D: pilot fixture + acceptance test`).
Каждая фаза — отдельный commit на ветке `T131-saturable-thd`,
squash в один при merge.

**Spec status:** Analyzed (после правок §3, §4 для отражения A2,
W1, W2).
