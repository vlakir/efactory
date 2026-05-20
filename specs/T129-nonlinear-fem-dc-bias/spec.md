# Spec: Nonlinear FEM material + DC-bias load line (T129)

**Статус:** Clarified (готова к Analyze)
**Дата создания:** 2026-05-20
**История:** preliminary split T128 → T129 + T130 (2026-05-20
investigation) был отменён в Clarify-фазе (2026-05-20 wave 2) — задачи
признаны атомарными, T130 поглощена T129, ID T130 не переиспользуется.
**Связанные документы:**
- ADR `2026-05-20 — Magnetic field verification: GetDP+Gmsh выбран` в
  `DECISIONS.md`
- T113 spec — `specs/T113-fem-solver/spec.md` (Phase 1 pilot, Phase 2
  integration; этот spec — Phase 3 follow-up)
- T128 BACKLOG entry в `BACKLOG.md` (investigation phase; см. historical
  comment с описанием обоих merge'ев)
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
  initial L. Без DC-bias load line FEM-валидация для choke бесполезна.
- **Validation against PyOM**: при cross-check FEM ↔ PyOM на
  любом DC-biased компоненте текущий 242% gap делает acceptance
  test useless (он всегда падает с known-gap pattern). После
  T129 acceptance становится реальной regression-защитой.

## 3. Функциональные требования

### Nonlinear material model (Frohlich-Kennelly)

- **ДОЛЖНА**: генерировать B-H curve таблицу (≥10 точек, B от
  0 до 0.99 × B_sat) из доступных PyOM material параметров
  методом Frohlich-Kennelly:
  `B(H) = μ₀·μ_init·H / (1 + μ₀·μ_init·H / B_sat)`.
  Источник параметров: `material.permeability.initial.value`
  (μ_initial, dimensionless) и `material.saturation.value`
  (B_sat в Tesla) — те же поля, что probed в T113 Phase 1 Stage A.
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

### DC-bias load line (incremental inductance at operating point)

- **ДОЛЖНА**: при вычислении inductance с
  `material_model="nonlinear-frohlich"` использовать operating
  point из `MagneticComponent.operating_point.primary_dc_bias_a`
  для DC бэкграунд-возбуждения.
- **ДОЛЖНА**: вычислять **incremental inductance** вокруг
  operating point через **central finite difference** на трёх
  nonlinear solve'ах:
  - solve nonlinear для `I = I_dc − ΔI/2` → Φ₋
  - solve nonlinear для `I = I_dc` → Φ₀ (используется также
    для `peak_flux_density_t` diagnostic)
  - solve nonlinear для `I = I_dc + ΔI/2` → Φ₊
  - `L_inc = (Φ₊ − Φ₋) / ΔI`
  ΔI выбирается `max(0.05·|I_dc|, 0.1 A)` — относительная
  амплитуда 5% с абсолютной floor'ой для устойчивости вокруг
  zero-bias.
  Central difference даёт O(ΔI²) точность и симметрично вокруг
  operating point — лучше чем asymmetric two-point, который
  систематически занижает L_inc в глубокой saturation (см.
  Analyze Critical C1). Метод (B) proper linearization
  (per-element `μ_diff`, second linear solve) — кандидат на
  refinement отдельной T-ID, если central difference поплывёт
  по точности или скорости.
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
- **ДОЛЖНА**: BACKLOG cleanup — T129 entry удаляется (T130 уже
  поглощена T129 в Clarify-фазе, отдельной записи в BACKLOG нет);
  если возникли side-tasks (например, advanced material model или
  proper linearization fallback) — заводятся как новые T-ID.

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
   linearization (см. §3 "DC-bias load line")? B физически правильнее, но
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

**Q1 — DC-bias method.** Принято **central finite difference на
трёх nonlinear solve'ах** (refinement two-point после Analyze C1):
solve в `I_dc − ΔI/2`, `I_dc`, `I_dc + ΔI/2`, `L_inc = (Φ₊ − Φ₋)/ΔI`.
Стоит +1 nonlinear solve относительно asymmetric two-point, но
даёт O(ΔI²) точность вместо O(ΔI) и симметрично — нет
систематического сдвига вглубь saturation. Метод (B) proper
linearization (per-element `μ_diff`, second linear solve) —
кандидат на refinement отдельной T-ID если central difference
поплывёт.

- **ΔI choice:** `max(0.05 · |I_dc|, 0.1 A)` — относительная
  амплитуда 5% perturbation с абсолютной floor'ой для устойчивости
  вокруг zero-bias. При `I_dc = 0` central difference solve'ит в
  `±0.05 A` (small-signal probe), даёт chord L ≈ L_initial —
  согласовано с §3 «DC-bias load line» последним bullet'ом.

**Q2 — GetDP solver.** Принято **fixed-point Picard
(IterativeLoop)** с tolerance 1e-5, max 50 iterations. Newton-
Raphson требует analytic `∂ν/∂(B²)` от Frohlich curve и
JacNL term — больше кода, выше риск sign-error в derivative.
Picard проще и сходится монотонно на Frohlich (B-H монотонна,
no inflection). Если Performance criterion <30s не выполнен —
заводим новую T-ID на Newton с JacNL.

**Q3 — Frohlich vs alternative models.** Принято **Frohlich-
Kennelly как единственный nonlinear model в Phase 3**. PyOM
1.3.10 даёт только `(μ_initial, B_sat)` — 2 параметра. Frohlich-
Kennelly канонически проходит через `(0, 0)` с начальной
касательной `μ₀·μ_initial` и асимптотически приближается к
`B_sat`. Alternative 2-параметровые формы (Langevin, arctan-
based, tanh) дают близкие кривые в operating range; выбор
между ними при том же fit'е — bikeshedding. Brillouin /
Jiles-Atherton требуют 3+ параметров (knee sharpness, anisotropy),
которых нет. Альтернатива появится отдельной задачей если PyOM
расширит material schema (или добавим override через explicit
B-H point list — §3 опциональный MAY).

**Q4 — Где живёт BH-генератор.** Принято: **adapter-internal**
в `src/adapters/outbound/fem_solver_getdp/material.py`. Domain
содержит **что** (модель магнетика как абстракция через
`MagneticComponent`); GetDP-specific формат точек (B[T], H[A/m]
arrays для `InterpolationLinear`) — это **как**, technical
detail backend'а. Когда появится второй FEM backend (Elmer
в рамках T127 cross-validation), у него будет свой
`material.py` с тем же VO — это нормально по hex-discipline,
разные backend'ы. В `src/domain/magnetic.py` `FrohlichBHCurve`
не выношу, пока нет второго domain-consumer'а.

**Q5 — Operating point coverage.** Принято: **одна точка** —
incremental L считается на `operating_point.primary_dc_bias_a`,
возвращается один скаляр `L_inc`. Sweep `L(I_dc)` curve для
choke design — отдельная задача (новая T-ID), не входит в T129.
Domain VO `MagneticVerificationResult` не меняется по схеме
(остаётся скалярное поле inductance_h); опциональные diagnostic
metrics из §3 MAY (`peak_flux_density_t`, `fem_method`)
добавляются в этой же T129 как Optional поля для одной operating
point.

---

## Analyze (заполняется Claude)

<!-- Перечитал spec+clarify после Q1–Q5 resolved. Issues помечены
     Critical / Warning / Note. -->

### Critical

- **C1. ΔI choice и nonlinearity around operating point.** Two-point
  finite difference даёт *secant* slope `(Φ₂ − Φ₁)/ΔI` между двумя
  large-signal solve'ами. При сильно нелинейной кривой это
  отличается от *tangent* (incremental) slope в точке `I_dc`. На
  pilot fixture `I_dc = 8 A` (плановый, см. T113 Stage A) +
  ΔI = 0.4 A (5%) → точка `I_dc + ΔI = 8.4 A` ещё глубже в saturation,
  что **систематически занижает** L_inc относительно истинного
  tangent. **Mitigation:** использовать **central difference**:
  solve трижды (`I_dc - ΔI/2`, `I_dc`, `I_dc + ΔI/2`), вычислять
  `L_inc = (Φ_+ − Φ_-) / ΔI`. Стоит +1 nonlinear solve (3 вместо 2),
  но даёт O(ΔI²) точность вместо O(ΔI) и симметрично вокруг
  operating point. Решение: **central difference, 3 solve'a**.
  Обновить §3 «DC-bias load line» и Q1 в Resolved.

- **C2. `I_dc = 0` central difference вырождение.** При `I_dc = 0`
  central difference даёт solve в `±ΔI/2` — это small-signal probe,
  ОК. Но Q1 ΔI floor «0.1 A absolute» относится к asymmetric two-
  point. Для central difference floor нужен другой: при `I_dc = 0`
  и ΔI = 0.1 A central → solve в `±0.05 A` — нормально, μ_diff ≈
  μ_initial. **Решение:** ΔI = `max(0.05 · |I_dc|, 0.1 A)` остаётся,
  central difference устойчиво вокруг нуля без дополнительной
  обработки.

### Warning

- **W1. Picard convergence на saturation knee.** Fixed-point Picard
  на Frohlich-Kennelly теоретически сходится монотонно (B-H
  монотонна без перегиба), но на 50 iterations limit и tolerance
  1e-5 может не уложиться при `H_dc >> H_sat` (deep saturation —
  как раз pilot OPT 6П14П, `H_dc = 1289`, `H_sat ≈ 200` A/m,
  6.4× выше knee). Picard relaxation factor (`Relaxation = 0.5..0.8`
  в IterativeLoop) часто решает. **Решение:** включить
  `RelaxationFactor 0.7` в IterativeLoop по умолчанию; если
  Performance <30s не выполнен или Picard не сходится — fallback
  branch на Newton-Raphson отдельной T-ID (Q2 уже предусматривает).

- **W2. PyOM data extraction path для `mu_initial` и `b_sat`.**
  Спека не фиксирует, откуда `FrohlichBHCurve.from_pyom_material()`
  читает параметры. T113 Phase 1 pilot брал их из
  `material.permeability.initial.value` и `material.saturation.value`
  (probed). Нужно проверить, что в новой PyOM advisor flow
  (`design_for_*`) эти поля доступны на том же пути, или
  ввести explicit material query до nonlinear solve.
  **Решение:** добавить в spec §3 явное упоминание pyom path —
  «`material.permeability.initial.value` (μ_initial, dimensionless)
  + `material.saturation.value` (B_sat в Tesla)»; integration
  test проверяет, что на pilot fixture эти поля непустые.

- **W3. Acceptance ±10% против fixture с iron в deep saturation.**
  PyOM ZHANG model даёт 6.96 H для `H_dc = 1289 A/m`; это
  reluctance-model, она тоже саппроксимирует через operating
  point effective μ. FEM nonlinear + DC-bias load line + Frohlich
  — это **другая** approximation. Ожидание ±10% между двумя
  approximation'ами эмпирическое; нет физической гарантии. Если
  не сойдётся — нужен либо разбор причин (Frohlich knee shape vs
  ZHANG effective μ), либо relax acceptance до ±20%. **Решение:**
  оставить ±10% как primary target; если на implementation
  не достижимо — открываем обсуждение (новая T-ID или relax
  acceptance в DECISIONS.md).

### Note

- **N1. `MagneticVerificationResult` diagnostic поля.** §3 MAY
  упоминает `peak_flux_density_t` и (в §5) `fem_method: str`.
  Решено в Q5 добавить **в эту же T129** как Optional. Уточнение:
  - `fem_method: Literal["linear", "nonlinear-frohlich"] | None` —
    повторяет `material_model` параметр solver'a, но в результате
    (для downstream consumer'ов и логов).
  - `peak_flux_density_t: float | None` — max(|B|) по mesh после
    nonlinear solve; nullable в linear mode.

- **N2. Back-compat default `material_model="linear"`.** §3 говорит
  «`linear` по умолчанию — back-compat». Это значит, что все
  существующие тесты в `tests/integration/application/
  test_mag_verify_field.py` (кроме переписываемого pilot
  regression) НЕ должны заметить изменения. Acceptance Secondary
  «linear mode = 23.78 H ±5%» — это и есть проверка back-compat.

- **N3. Граф фаз implementation.** Логичная декомпозиция:
  - **Phase A** — Frohlich BH-генератор + InterpolationLinear в
    .pro template (linear mode остаётся default; добавляется
    nonlinear path под флагом). Pre-existing тесты — green
    (no regression).
  - **Phase B** — DC-bias central difference (3 solve'a) + extraction
    incremental L_inc. Integration test `test_analytical_plus_fem_
    pilot_regression` переписывается на `relative_difference ≤ 0.10`.
  - **Phase C** — closing-правки: ADR в DECISIONS.md, BACKLOG
    cleanup, перенос BOARD Doing → Done.
  Каждая фаза — отдельный commit на task-ветке; squash в один
  при merge (правило «один PR — один коммит»).
