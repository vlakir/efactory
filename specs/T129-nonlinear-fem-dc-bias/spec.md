# Spec: Nonlinear FEM material + DC-bias load line (T129 + T130)

**Статус:** Draft
**Дата создания:** 2026-05-20
**Связанные документы:**
- ADR `2026-05-20 — Magnetic field verification: GetDP+Gmsh выбран` в
  `DECISIONS.md`
- T113 spec — `specs/T113-fem-solver/spec.md` (Phase 1 pilot, Phase 2
  integration; этот spec — Phase 3 follow-up)
- T128 BACKLOG entry в `BACKLOG.md` (investigation phase; split в
  T129 + T130)
- Auto-memory `feedback_pyom_advisor_quirks.md` (PyOM 1.3.10 material
  data limitations probed 2026-05-20)

---

## 1. Overview

T113 Phase 1 pilot выявил систематическое расхождение в 242% между
analytical inductance из PyOpenMagnetics (6.96 H по ZHANG reluctance
model) и FEM inductance из GetDP с линейным μ_r=8000 (23.78 H) на
fixture OPT 6П14П SE. T128 investigation показал, что расхождение
вызвано **двумя независимыми причинами**, которые нужно адресовать
вместе:

1. PyOM учитывает operating-point effective μ при DC bias, а linear
   FEM считает только μ_initial.
2. Iron в pilot fixture глубоко в saturation regime: H_dc=1289 A/m
   при PyOM H_sat=200 A/m (6.4× выше), что делает incremental
   inductance радикально ниже линейной оценки.

Эта фича — реализация **nonlinear material model** в FEM-адаптере
**и** **DC-bias load-line** modelling, которые вместе закроют
242% gap и сделают `mag_verify_field` use case реально полезным
для DC-biased magnetic components (OPT, choke, push-pull
transformers с DC magnetization).

## 2. Сценарии использования

Скрипты / автоматизация / агент:

- **Агент проектирует SE/PP output transformer**: знает primary
  DC plate current класса A, хочет получить **incremental Lp at
  operating point**, не large-signal. Сейчас FEM возвращает large-
  signal Lp (завышен в 3-4×), что вводит в заблуждение при mid-band
  audio rolloff calculation.
- **Агент верифицирует SMPS choke** (T128 BACKLOG flyback fixture
  follow-up): DC current через дроссель кладёт ядро близко к
  saturation; incremental L (для switching ripple) сильно ниже
  initial L. Без T130 FEM-валидация для choke бесполезна.
- **Validation against PyOM**: при cross-check FEM ↔ PyOM на
  любом DC-biased компоненте текущий 242% gap делает acceptance
  test useless (он всегда падает с known-gap pattern). После
  T129+T130 acceptance становится реальной regression-защитой.

## 3. Функциональные требования

### T129 — Synthetic nonlinear material model

- **ДОЛЖНА**: генерировать B-H curve таблицу (≥10 точек, B от
  0 до 0.99 × B_sat) из доступных PyOM material параметров
  (`permeability.initial`, `saturation`) методом Frohlich-Kennelly:
  `B(H) = μ₀·μ_init·H / (1 + μ₀·μ_init·H / B_sat)`.
- **ДОЛЖНА**: расширить `pro_template.py` поддержкой nonlinear
  iron region — таблица интерполируется через `InterpolationLinear`
  (GetDP built-in), Resolution использует `IterativeLoop` (fixed-
  point Picard метод) с tolerance 1e-5 и max 50 iterations.
- **ДОЛЖНА**: ввести параметр `material_model:
  Literal["linear","nonlinear-frohlich"]` в `GetDpFemSolver`;
  по умолчанию `"linear"` (back-compat); pipeline runs end-to-end
  в обоих режимах без regression existing tests.
- **МОЖЕТ**: добавить опциональный override через explicit B-H
  point list (для будущих use cases когда PyOM научится
  экспортировать bhCycle).
- **НЕ ДОЛЖНА**: реализовывать advanced nonlinear models
  (Jiles-Atherton hysteresis, anisotropic ferrites, frequency-
  dependent permeability) — это отдельные фичи.

### T130 — DC-bias load line

- **ДОЛЖНА**: при вычислении inductance с
  `material_model="nonlinear-frohlich"` использовать operating
  point из `MagneticComponent.operating_point.primary_dc_bias_a`
  для DC бэкграунд-возбуждения.
- **ДОЛЖНА**: вычислять **incremental inductance**
  `L_inc = ΔΦ / ΔI` вокруг operating point через одну из двух
  моделей (выбор — в Clarify phase):
  - (A) Two-point combined: solve nonlinear для `I = I_dc`,
    solve nonlinear для `I = I_dc + ΔI`, finite difference на Φ.
  - (B) Proper linearization: solve nonlinear для `I = I_dc` →
    `A_0(x,y)`, compute `μ_diff(B(x,y)) = dB/dH` per element,
    solve linear для AC probe small-signal с μ_diff(x,y) →
    `L_inc = 2·W_AC / I_AC²`.
- **ДОЛЖНА**: при `primary_dc_bias_a = 0.0` сводиться к чистому
  small-signal solve (consistency с линейным режимом до тех пор,
  пока iron не насыщается probe current'ом).
- **МОЖЕТ**: возвращать дополнительные metrics в
  `MagneticVerificationResult` (peak flux density, saturation
  margin) для diagnostic purposes.

### Integration

- **ДОЛЖНА**: integration test
  `test_analytical_plus_fem_pilot_regression` в
  `tests/integration/application/test_mag_verify_field.py`
  переписан с `discrepancy_flagged=True` (текущее regression
  к 242% gap) на `relative_difference <= 0.10`.
- **ДОЛЖНА**: closing-правка в `DECISIONS.md` — новый ADR
  `2026-MM-DD — Nonlinear FEM + DC-bias load line closes T113
  242% gap` (с заменой acceptance footnote из `T113-fem-solver/spec.md`
  на фактический result).
- **ДОЛЖНА**: BACKLOG cleanup — T129 + T130 entries удаляются;
  если возникли side-tasks (например, advanced material model) —
  заводятся как новые T-ID.

## 4. Success Criteria

- **Primary**: FEM Lp на OPT 6П14П SE fixture с
  `material_model="nonlinear-frohlich"` + DC-bias load line
  совпадает с PyOM analytical ZHANG (6.96 H) в пределах **±10%**.
- **Secondary**: linear mode (без DC bias) даёт тот же Lp что
  baseline T113 Phase 1 pilot (23.78 H ±5%) — back-compat не
  сломан.
- **Performance**: nonlinear solve завершается за **< 30s** на
  pilot fixture (mesh 12244 quad triangles) при default
  IterativeLoop settings. Если медленнее — open question
  про Newton-Raphson vs fixed-point.
- **Code quality**: 4 pre-push gates зелёные; coverage не падает
  ниже текущих 87% на src/.
- **Image**: efactory:linux size не растёт значительно (только
  Python код + GetDP .pro extension — apt deps те же).

## 5. Key Entities

- **`FrohlichBHCurve`** (new VO в `src/domain/magnetic.py` или
  internal в adapter): tabulated points (B[T], H[A/m]); generated
  из `(mu_initial, b_sat)` PyOM data; передаётся в .pro template
  как InterpolationLinear input.
- **`OperatingPoint.primary_dc_bias_a`** (existing field в
  `src/domain/magnetic.py`): используется как DC excitation
  source в .pro Function block.
- **`GetDpFemSolver`** (existing class): + параметр
  `material_model`, + параметр `dc_bias_method:
  Literal["two-point","linearization"]` (после Clarify).
- **`MagneticVerificationResult`** (existing): optional
  additional fields `fem_method: str`, `peak_flux_density_t:
  float | None` для диагностики.

## 6. Assumptions & Constraints

- PyOM 1.3.10 не экспонирует `bhCycle` (probe 2026-05-20:
  все 409 materials имеют `bhCycle: null`). Если в новой
  версии PyOM появится — мы переключимся на real data
  отдельной задачей.
- Frohlich-Kennelly — простейшая 2-параметровая модель; не
  моделирует hysteresis loop, остаточную намагниченность,
  frequency-dependent permeability. Этого достаточно для
  acceptance ±10% на DC-biased linear excitation; advanced
  hysteresis (Jiles-Atherton) — отдельная задача.
- DC bias считается строго primary winding only (secondary в
  pilot fixture не энергизована per pilot Stage B+C). Multi-
  winding load line — будущее follow-up.
- GetDP 3.2.0 (Ubuntu 24.04 noble apt) поддерживает
  `InterpolationLinear` + `IterativeLoop` — проверено косвенно
  через документацию ONELAB; в Clarify phase спайк подтвердит.
- Pilot fixture (OPT 6П14П SE) — единственная reference
  geometry в Phase 3. 50 Hz power transformer (T127 BACKLOG)
  и flyback choke — separate follow-up'ы.

## 7. Out of Scope

- **Jiles-Atherton hysteresis** model (frequency-dependent losses).
- **Anisotropic ferromagnetic materials** (grain-oriented steel,
  amorphous metals с directional B-H).
- **Eddy currents** + **complex permeability** (Phase Cross-platform
  fixtures для AC operating points).
- **Multi-winding DC bias** (secondary + tertiary currents в load
  line) — pilot fixture одну primary энергизует.
- **3D geometry** support (`processedDescription.depth` пока
  scaling factor для 2D-planar результата; full 3D mesh — отдельный
  большой следующий шаг).
- **Adaptive mesh refinement** в окрестности saturation knee —
  mesh-converged result B+C достаточен для pilot.

---

## Clarify (заполняется Claude)

### Open questions

1. **DC-bias method**: (A) two-point combined или (B) proper
   linearization (см. §3 T130)? B физически правильнее, но
   требует extraction `μ_diff` per-element и второго linear
   solve; A проще, но точность зависит от ΔI choice.
2. **GetDP solver**: fixed-point IterativeLoop (Picard) vs
   Newton-Raphson с `JacNL` term? Newton быстрее (~10 iter
   vs 50), но требует analytic ∂ν/∂(B²) от Frohlich curve.
3. **Frohlich vs alternative analytical models**: достаточно
   ли точна Frohlich-Kennelly на 2 параметрах, или нужны
   более сложные модели (например, Brillouin / arctan-based)
   когда у нас в принципе только 2 точки данных?
4. **Где живёт BH-генератор** — `src/adapters/outbound/
   fem_solver_getdp/material.py` (domain-free) или
   `src/domain/magnetic.py` (если VO BHCurve вынести в domain)?
5. **Operating point coverage**: incremental L считается на
   одном `primary_dc_bias_a` — если у компонента нужно
   characterize Lp(I_dc) curve, это отдельная задача?

### Resolved (с ответами)

- ...

---

## Analyze (заполняется Claude)

<!-- В новой сессии после Clarify. Список Issues с пометками. -->

- ...
