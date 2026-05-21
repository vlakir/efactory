# Spec: Elmer FEM pivot — nonlinear B-H + DC-bias closure 242% gap (T133)

**Статус:** Phase 0 complete (Critical questions resolved, готова к Phase 1)
**Дата создания:** 2026-05-21
**Связанные документы:**
- ADR `2026-05-20 — T129 closure: analytical (PyOM ZHANG) — source of truth
  для incremental L at operating point; FEM cross-check откладывается на
  T133 (Elmer)` в `DECISIONS.md`
- T129 spec — `specs/T129-nonlinear-fem-dc-bias/spec.md` (infrastructure
  reuse: `FrohlichBHCurve`, central-diff method, `FemSolveOutcome` DTO)
- T113 spec — `specs/T113-fem-solver/spec.md` (pilot infrastructure
  reuse: `scripts/pilot/elmer/magnetostatic.sif`, `pilot.Dockerfile`
  pattern, T113 Phase 1 cross-check baseline Lp = 23.78 H)
- BACKLOG T133 entry — изначальное описание pivot'а
- Auto-memory `feedback_elmer_savescalars_quirks.md` (4 pitfall'а
  обнаружены в T113 Stage D)

---

## 1. Overview

T113 Phase 1 pilot выявил систематическое расхождение **242%** между
analytical inductance из PyOpenMagnetics (6.96 H по ZHANG reluctance
model) и FEM inductance из GetDP с линейным μ_r=8000 (23.78 H) на
fixture OPT 6П14П SE. T129 попыталась закрыть gap через nonlinear
material model (Frohlich-Kennelly) + DC-bias central-difference в
GetDP, но **закрытие не состоялось**: на 2D-planar split-coil
топологии open-domain не достигает proper flux closure, Frohlich
curve не engaging (L_nl/L_lin ≈ 0.997 после ultrareview bug_001 fix).
Phase A/B остались как pure infrastructure для будущего reuse.

T133 — **Elmer FEM pivot**: переход на Elmer FEM с native `H-B Curve`
keyword (out-of-the-box nonlinear support, Newton iteration) и
**топологический rework**: single-coil + outer Kelvin transformation
(shell mapping) — proper open-domain flux closure для magnetostatic.
Reuses T129 infrastructure (`FrohlichBHCurve`, central-diff DC-bias,
`FemSolveOutcome` DTO) без переписывания domain layer, добавляет
новый adapter `fem_solver_elmer` параллельно существующему
`fem_solver_getdp`.

Цель — закрыть 242% gap до acceptance ±25% (target ±10%) к PyOM ZHANG
на pilot fixture OPT 6П14П SE и предоставить FEM cross-check для
precision-critical client cases (top-tier interleaved OPT, power
transformer с tight HF-rolloff spec).

## 2. Сценарии использования

Скрипты / автоматизация / агент:

- **Агент верифицирует FEM-precision на DC-biased OPT** (real client
  case, top-tier audio): primary analytical путь — PyOM ZHANG
  reluctance — даёт точечную оценку, но client требует FEM cross-check
  на geometry с realistic fringing/leakage. Сейчас GetDP-only путь
  возвращает large-signal L (без operating-point μ), что неприменимо.
  Elmer adapter с nonlinear + DC bias возвращает incremental L_inc
  при operating point.
- **Регрессия T113 cross-check**: T113 Phase 1 Stage F показал
  Elmer↔GetDP сошлись 0.00% на linear physics. Elmer adapter в
  linear mode позволяет восстановить эту регрессию автоматически
  (integration test), а не из pilot one-off скрипта.
- **Cross-validation analytical leakage** (T135 follow-up): если T132
  Erickson formula требует FEM cross-check на дополнительных
  fixtures, Elmer FEM с native nonlinear — preferred backend.
- **Honest "infrastructure-only" graceful degradation**: если
  acceptance ±25% не достижим (model gap между ZHANG reluctance
  и planar FEM окажется фундаментальным), Elmer adapter всё равно
  даёт независимый FEM backend для cross-validation analytical
  путей — это уже win относительно T129 outcome.

## 3. Функциональные требования

### Elmer FEM adapter (`fem_solver_elmer`)

- **ДОЛЖНА**: реализовать новый adapter `src/adapters/outbound/
  fem_solver_elmer/` со структурой, симметричной существующему
  `fem_solver_getdp/`:
  - `adapter.py` — `ElmerFemSolver` класс с тем же `MagneticFieldSolver`
    Protocol interface (`async def solve(component) -> FemSolveOutcome`).
  - `geometry.py` — emit Gmsh `.geo` для **single-coil + Kelvin
    shell** топологии (новая, не reuse split-coil из getdp); shared
    `ECoreDimensions` через import из `fem_solver_getdp` ИЛИ выделить
    `ECoreDimensions` в common module (решит Analyze).
  - `sif_template.py` — render Elmer `.sif` с substituted params
    (linear `Relative Permeability` или nonlinear `H-B Curve` table).
- **ДОЛЖНА**: поддерживать оба режима `material_model`:
  - `'linear'` (back-compat, mirror GetDP shape) — constant μ_r,
    energy method `L_p = 2·W/I²`, T113 cross-check regression.
  - `'nonlinear-elmer'` (T133 primary win) — native Elmer `H-B Curve`
    keyword (tabulated B,H массивы от `FrohlichBHCurve`), Newton
    iteration (default; Picard fallback при non-convergence —
    implementation choice).
- **ДОЛЖНА**: использовать ту же DC-bias central-difference logic, что
  T129 для GetDP: 2 nonlinear solve'а (`I_dc ± ΔI/2`), `L_inc = (Φ₊ −
  Φ₋)/ΔI`, `ΔI = max(0.01·|I_dc|, 0.0001 A)` — reuse без re-обсуждения.
- **ДОЛЖНА**: возвращать `FemSolveOutcome` с `method ∈ {'linear',
  'nonlinear-frohlich'}` (existing `FemMethod` Literal). Если потребуется
  отличать backend в downstream — добавляем `'linear-elmer'` /
  `'nonlinear-frohlich-elmer'` варианты (решит Analyze).
- **ДОЛЖНА**: subprocess pipeline:
  1. PyOM `calculate_core_data` → E-core dims (shared с GetDP).
  2. `geometry.emit_single_coil_kelvin_geo(dims)` → `.geo` (новая
     топология).
  3. `gmsh -2 -format msh22 .geo -o mesh.msh` (shared subprocess).
  4. `ElmerGrid 14 2 mesh.msh -out mesh-elmer/` (конвертация
     Gmsh → Elmer mesh DB).
  5. `sif_template.render(...)` → `case.sif`.
  6. `ElmerSolver case.sif` (subprocess; cwd = work_dir).
  7. Parse `scalars.dat` (SaveScalars output, body integrals от A).
  8. `L_inc = (Φ₊ − Φ₋)/ΔI` (или `L_p = 2·W/I²` в linear).
- **МОЖЕТ**: добавить `'linear-elmer'` cross-check integration test
  против GetDP linear на same fixture (T113 Stage F regression).
- **НЕ ДОЛЖНА**: дублировать `FrohlichBHCurve` или `FemSolveOutcome`
  определения — reuse из domain.

### Топология: single-coil + Kelvin shell

- **ДОЛЖНА**: 2D-planar magnetostatic geometry содержит:
  - E-core (Iron region, nonlinear или linear μ).
  - **Один coil** (Primary) с тотальным MMF = `N_primary · I_excitation`,
    без split на Secondary return-leg.
  - **Outer Kelvin shell transformation** для proper open-domain
    flux closure: physical Air domain (radius `R_inner`) + shell
    region (`R_inner` → `R_outer`) с mapping coordinates, на
    `R_outer` — Dirichlet `A = 0`. Elmer штатно поддерживает через
    `Infinity BC` или manual shell coordinate transform (Phase 0
    pilot выберет конкретный механизм).
- **ДОЛЖНА**: Kelvin shell радиусы:
  - `R_inner` ≥ 5 × max(core OD) — выбирается tight enough чтобы
    mesh density на core области не падал.
  - `R_outer` = `R_inner · const` (Kelvin formula `r' = R_inner² / r`).
- **ДОЛЖНА**: integration test smoke-проверкой: на linear physics
  результат должен **отличаться** от T113 split-coil baseline
  (23.78 H) — если совпадёт, значит Kelvin shell не работает и flux
  не правильно закрывается. Точный target Elmer linear на новой
  топологии — отдельная числовая проверка после Phase 0 pilot
  (записать в spec revision как baseline reference).
- **МОЖЕТ**: fallback на closed Dirichlet box (Q1 option (c)) если
  Kelvin shell не сойдётся в Elmer 26.2 — Vladimir подтвердил
  fallback path. Решение принимается в Phase 0 pilot.
- **НЕ ДОЛЖНА**: реализовать split-coil топологию (это GetDP baseline,
  не reuse'ится).

### Frohlich / DC-bias reuse

- **ДОЛЖНА**: использовать существующий `FrohlichBHCurve` domain VO
  (`src/domain/material.py`). Добавить (если нужно) helper-метод
  `as_elmer_hb_table()` возвращающий формат для Elmer
  `H-B Curve = Variable Coupled iter; Real ... End` keyword.
- **ДОЛЖНА**: central-diff method идентичен T129 GetDP — 2 nonlinear
  solve'а, ΔI formula та же.
- **ДОЛЖНА**: extraction `(μ_initial, B_sat)` из PyOM material data —
  reuse `_read_initial_permeability` / `_read_saturation_flux_density`
  helpers из GetDP adapter (либо выделить в shared module — решит
  Analyze).

### Image / Dockerfile

- **ДОЛЖНА**: pilot phase 0 использует одноразовый `pilot.Dockerfile`
  pattern (T113 reuse) с `elmerfem-csc` через PPA `ppa:elmer-csc-
  ubuntu/elmer-csc-ppa` (Elmer 26.2, в noble universe отсутствует).
  Не модифицирует main Dockerfile до convergence on pilot.
- **ДОЛЖНА**: main Dockerfile получает `elmerfem-csc` только после
  Phase 0 pass (Phase 1). Image size +~300 MB (T113 spec estimate);
  CONCEPT §13 «6 GB ceiling» уже формально превышен на T112
  (Vladimir confirmed acceptable 2026-05-20).

### Integration / closing

- **ДОЛЖНА**: integration test
  `test_elmer_fem_pilot_dc_bias_acceptance` в
  `tests/integration/adapters/fem_solver_elmer/` — на pilot fixture
  (OPT 6П14П SE, `primary_dc_bias_a` = T113 baseline value):
  Acceptance `relative_difference <= 0.25` к PyOM ZHANG (6.96 H);
  target ≤ 0.10 (если попадает — bonus, не блокирует closure).
- **ДОЛЖНА**: integration test Elmer↔GetDP linear cross-validation
  (T113 Stage F restoration) — `relative_difference <= 0.01` (0.00%
  ожидаем; ≤1% threshold защищает от numerical drift).
- **ДОЛЖНА**: ADR override в `DECISIONS.md` — «2026-MM-DD — T133
  closure: Elmer для nonlinear FEM, GetDP остаётся primary для
  linear/geometry; T113 242% gap closed/relaxed на pilot fixture».
- **ДОЛЖНА**: BACKLOG cleanup — T133 entry удаляется, BOARD entry
  переводится в Done с closing message.

## 4. Success Criteria

**Primary (acceptance, gates на closing):**

- На pilot fixture OPT 6П14П SE с `material_model='nonlinear-elmer'`
  + DC bias + Kelvin shell single-coil топологией: `L_inc` относительно
  PyOM ZHANG (6.96 H) с **relative_difference ≤ 0.25** (acceptance).
- На той же fixture с `material_model='linear'`: cross-check
  Elmer↔GetDP linear с **relative_difference ≤ 0.01** на T113
  baseline 23.78 H ИЛИ (если new topology даёт другой baseline)
  на новом baseline с явным docstring обоснованием.
- 4 pre-push gates зелёные (ruff check / format / mypy / pytest);
  coverage ≥ 86% на `src/` (Elmer adapter subprocess paths
  exercise'ятся integration tests; pure unit coverage будет ниже,
  что компенсируется integration).

**Target (bonus, не блокирует closure):**

- `relative_difference ≤ 0.10` к PyOM ZHANG — полное закрытие 242%
  gap, изначальная цель T129 переразожжена. Если достигается —
  ADR закрывает как «T113 gap closed», иначе — «T113 gap relaxed
  на pilot, infrastructure ready для дальнейшего refinement».

**Plumbing:**

- End-to-end pipeline через port `MagneticFieldSolver.solve(component)
  → FemSolveOutcome` работает с обоими adapters (GetDP + Elmer) на
  same fixture — interchangeable backend.
- `FemSolveOutcome.method` корректно прокидывает Elmer-specific метод
  (либо через расширение `FemMethod` Literal, либо через docstring
  contract — решит Analyze).

**Performance:**

- 1 linear Elmer solve на pilot fixture mesh (≤ 20000 elements):
  < 10 s (T113 pilot baseline 3.14 s, accommodate новый mesh size).
- 2 nonlinear Newton solve'a (central-diff DC bias): < 60 s total.

**Image:**

- pilot.Dockerfile (Phase 0) — ephemeral, не committed в main tree.
- main Dockerfile (Phase 1) — `elmerfem-csc` PPA добавлен; size
  delta ≤ 350 MB (T113 estimate 300 MB; cushion 50 MB на новые
  Newton-related lib deps).

## 5. Key Entities

- **`ElmerFemSolver`** (new): `src/adapters/outbound/fem_solver_elmer/
  adapter.py` — параллельный `GetDpFemSolver`. Те же конструктор-
  параметры (`pyom_module`, `material_model`, `num_bh_points`,
  `work_dir_root`) + Elmer-specific (`elmer_solver_bin`, `elmer_grid_bin`).
- **`emit_single_coil_kelvin_geo(dims, kelvin_outer_factor)`**
  (new function in `fem_solver_elmer/geometry.py`): emit Gmsh `.geo`
  для single-coil E-core + Kelvin shell. `dims: ECoreDimensions`
  shared from getdp adapter (либо moved в common).
- **`render_magnetostatic_sif_*`** (new functions in `fem_solver_elmer/
  sif_template.py`): рендеры `.sif` для linear / nonlinear режимов.
- **`FrohlichBHCurve`** (existing, T131 Phase E moved to domain):
  reused as-is; возможный новый метод `as_elmer_hb_pairs()` если
  format отличается от GetDP `as_getdp_list_literal()`.
- **`FemSolveOutcome`** (existing, T129): reused as-is; возможное
  расширение `FemMethod` Literal на `'linear-elmer'` / 'nonlinear-
  elmer' — решит Analyze.
- **`MagneticFieldSolver`** Protocol (existing): interface не
  меняется; Elmer adapter подключается параллельно к GetDP.

## 6. Assumptions & Constraints

- **Elmer 26.2 (apt PPA `ppa:elmer-csc-ubuntu/elmer-csc-ppa`)
  поддерживает `H-B Curve` keyword в `MagnetoDynamics2D` solver +
  Newton iteration** — Phase 0 pilot подтверждает spike'ом, до
  спайка считается «вероятно да» (Elmer documented feature).
  Если не поддерживает — fallback варианты: (a) ResultOutputSolver
  для B/H dump → numpy postprocessing с manual reluctivity update
  Picard, (b) escalation к Newton в `MagnetoDynamics` (3D solver)
  с 2D-projection, (c) ADR pivot обратно к GetDP topology rework
  (T133 retried).
- **Single-coil + Kelvin shell топология даёт proper flux closure**
  достаточный для Frohlich engagement при operating-point I_dc от
  T113 baseline (~50 mA primary DC). Closed Dirichlet fallback —
  компромисс (acknowledge не строго правильный, но даёт numerical
  improvement к T113 baseline).
- **Mesh size ≤ 20000 elements** для pilot fixture — Phase 0
  поправит если оверкилл / underkill (T113 Phase 1 mesh = 12244
  triangles, target similar).
- **PyOM material extraction path** (`material.permeability.initial[0].
  value`, `material.saturation[0].magneticFluxDensity`) не меняется
  с T129 — shared между GetDP и Elmer adapters.
- **Pilot fixture single source-of-truth** — OPT 6П14П SE, тот же
  fixture, что T113 Phase 1 / T129 Phase B; ZHANG analytical
  reference 6.96 H, T113 linear baseline 23.78 H. 50 Hz power
  transformer, flyback choke, leakage backend — separate T-IDs
  (T127, T135).
- **Hexagonal architecture preserved** — domain VOs не меняются;
  port не меняется; новый adapter — pure backend swap.

## 7. Out of Scope

- **Leakage inductance FEM backend** (T135 follow-up): T132 закрылся
  с analytical Erickson formula; FEM cross-check на 5+ section
  fixtures — отдельная задача с extension `.sif` template на
  short-circuit secondary + energy integral.
- **50 Hz power transformer fixture** (T127 BACKLOG): cross-
  validation Elmer↔GetDP на second topology — отдельная задача.
- **3D mesh / 3D-planar coupling** — T133 ограничен 2D-planar.
  Если pilot покажет, что 2D physics inherent limit (например,
  proper out-of-plane flux лимитирует precision), 3D becomes
  new T-ID.
- **Jiles-Atherton hysteresis** model: anhysteretic Frohlich
  достаточен для magnetostatic; hysteresis loops — отдельная фича.
- **Eddy currents / complex permeability** — Elmer штатно
  поддерживает через `MagnetoDynamics2D` `Harmonic Analysis`,
  но T133 — magnetostatic only.
- **Adaptive mesh refinement** в окрестности saturation knee —
  fixed mesh достаточен для pilot.
- **Newton vs Picard pre-commitment** — implementation chooses
  (Picard default fallback if Newton non-converges); не
  архитектурный выбор, не spec-level.
- **Symmetric coil distribution** (multi-section interleaved layout
  как в T132): pilot fixture P-S basic OPT, не interleaved.

---

## Clarify (заполняется Claude)

### Open questions

<!-- Все resolved в session 2026-05-21 на основе T129 retrospective
     + T113 pilot context. Если в Phase 0 probe вскроются новые слепые
     зоны — добавляются здесь. -->

### Resolved (с ответами)

**Q1 — Топология (split-coil vs Kelvin shell vs closed Dirichlet vs
axisymmetric).** Принято: **(b) single-coil + outer Kelvin shell
transformation**. Это принципиально правильный путь — proper open-
domain magnetostatic с flux closure через mapped infinity. Elmer
штатно поддерживает (`Infinity BC` или manual shell). 2D-axisymmetric
(d) не подходит — E-core asymmetric. Split-coil (a) — повторил бы T129
non-engagement. Closed Dirichlet box (c) — fallback в Phase 0, если
Kelvin shell не сойдётся в Elmer 26.2; решение по fallback принимается
после первой попытки pilot.

**Q2 — Acceptance gate (±10% strict vs ±20-25% relax vs two-axis).**
Принято: **(γ) two-axis** — target ±10% (если попадаем, ADR
закрывает 242% gap), acceptance ±25% (если попадаем только в это —
gap relaxed, infrastructure ready). PyOM ZHANG reluctance model
предполагает fully closed magnetic circuit; 2D-planar FEM с
realistic fringing/leakage будет физически отличаться, потому
жёсткий ±10% не гарантированно достижим. Two-axis даёт честную
метрику без блокировки closure на model-gap.

**Q3 — Pilot container vs main Dockerfile сразу.** Принято: **(a)
pilot.Dockerfile first** (mirror T113 Phase 1 pattern). Elmer 26.2
уже отметился отсутствием `MagnetoDynamics2DCalcFields` (T113
quirk); до integration верифицировать что `H-B Curve` keyword
+ Newton iteration работают в этой PPA-сборке. После Phase 0 pass —
main Dockerfile delta в Phase 1.

**Q4 — Newton vs Picard pre-commit.** Принято: **implementation
chooses, Picard default fallback при Newton non-convergence**.
Это конфиг-line в `.sif` (`Nonlinear System Newton After Iterations
= 3` или `Newton`), не архитектурный выбор. Phase 0 pilot
определит, нужен ли явный Newton-after-N или Picard-only sufficient.

**Q5 — Phasing.** Принято:
- **Phase 0** — Pilot probe: `pilot.Dockerfile` + nonlinear `.sif` +
  Kelvin shell топология. Smoke: Elmer сходится, L_inc finitely
  вычисляется. Один session/commit на T133 ветке.
- **Phase 1** — Main Dockerfile (+elmerfem-csc PPA), new adapter
  scaffolding (linear mode). T113 Stage F linear cross-check
  regression test. Session/commit.
- **Phase 2** — Nonlinear mode (`material_model='nonlinear-elmer'`),
  FrohlichBHCurve table conversion, central-diff DC-bias, integration
  test на pilot fixture. Session/commit.
- **Phase 3** — Acceptance test ±25% (target ±10%), ADR override в
  DECISIONS.md, BOARD Doing → Done, BACKLOG T133 cleanup. Session/
  commit. Squash в один commit при merge.

**Q6 — Scope adapter режимов (linear + nonlinear vs nonlinear only).**
Принято: **оба** (linear + nonlinear-elmer симметрично GetDP).
Symmetry adapter shapes облегчает regression test'ы (T113 Stage F
cross-check Elmer↔GetDP linear автоматизирован) и упрощает code
review.

**Q7 — Pilot fixture (только OPT 6П14П SE vs +вторая).** Принято:
**только OPT 6П14П SE** в T133 scope. Вторая fixture (50 Hz power
transformer) = T127 BACKLOG, отдельный T-ID. Scope discipline:
не «заодно».

---

## Analyze (заполняется Claude)

<!-- Перечитал spec+clarify после Q1–Q7 resolved (2026-05-21). Issues
     помечены Critical / Warning / Note. Critical — фиксим до Phase 0;
     Warning — обсуждаем, возможно фиксим в pilot; Note — к сведению. -->

### Critical

- **~~C1.~~ ✅ RESOLVED in Phase 0 (2026-05-21).** Elmer 26.2
  `MagnetoDynamics2D.so` поддерживает `Infinity BC = Logical True`
  как Robin-type natural BC (asymptotic decay constraint, не
  Dirichlet anchor). Empirically verified в
  `scripts/pilot/elmer/probe_infinity_bc.sif`: linear material +
  Infinity BC + current density дают finite NRM ≈ 0.47 (vs. NRM ≈
  1.5e+12 при wrong boundary tag), Unused keywords pусто. Robin
  natural BC означает что для magnetostatic с current source flux
  затухает на бесконечности правильно. Combined с anchor Dirichlet
  если нужно (для single-coil net-MMF ≠ 0) — может потребоваться
  поinted Dirichlet A=0 на одном узле + Infinity BC на outer
  boundary.

- **~~C2.~~ ✅ RESOLVED in Phase 0 (2026-05-21).** Elmer 26.2
  `MagnetoDynamics2D.so` поддерживает `H-B Curve` через стандартный
  Elmer tabulated property syntax:
  ```
  H-B Curve = Variable Coupled iter
    Real cubic
      H_1  B_1
      H_2  B_2
      ...
    End
  ```
  Empirically verified в `scripts/pilot/elmer/probe_hb_curve.sif`:
  Newton iteration сходится на 4-точечной Frohlich-like таблице
  с RELC: 2.0 → 1.97 → 0.26 → 0.067 → 0.019 → 0.0057 за 6
  iterations (Newton kicks in после iteration 3 per
  `Nonlinear System Newton After Iterations = 3`). Cubic spline
  interpolation между точками (per strings `Cubic spline for H-B
  curve` в binary). 3D-only keyword `H-B Curve Variable` (explicit
  variable binding) не нужен для 2D — Elmer auto-couples через
  `Variable Coupled iter`.

- **C3. `ECoreDimensions` cross-adapter import — hex-architecture
  question.** Spec §5 предполагает reuse `ECoreDimensions` из
  `fem_solver_getdp/geometry.py` в Elmer adapter. Прямой import
  adapter → adapter — нарушение hex-discipline (adapters независимы
  от друг друга, общаются только через domain/ports). **Mitigation
  options:**
  - **(a)** Выделить `ECoreDimensions` в новый shared module
    `src/adapters/outbound/_fem_geometry_common/` (acceptable: adapter
    family с common helpers, явно prefixed `_`). Минус: вводит
    inter-adapter coupling в build, осложняет independent refactor.
  - **(b)** Переместить `ECoreDimensions` в domain (`src/domain/
    magnetic.py` или новый `core_geometry.py`). Минус: VO привязан к
    PyOM data extraction (`from_pyom_core` classmethod) — domain
    становится PyOM-aware (хотя только через staticmethod factory,
    domain payload — pure floats).
  - **(c)** Duplicate copy в Elmer adapter. Минус: DRY violation,
    drift risk.
  - **Решение принимается в Phase 1** (когда adapter scaffolding
    начинается); spec не pre-commits. Vladimir может pre-decide
    если есть strong preference. По умолчанию predisposition к **(a)**
    — pure-geometric VO без `from_pyom_core` (его перенести в
    callsite extraction), либо **(b)** если PyOM-aware factory
    остаётся как static method, payload pure.

### Warning

- **W1. Elmer 26.2 PPA build optional dependencies.** PPA
  `ppa:elmer-csc-ubuntu/elmer-csc-ppa` собирает Elmer с конкретным
  набором опциональных зависимостей (Hypre, MUMPS, Trilinos). Если
  Newton iteration требует Hypre/Trilinos и в этой PPA-сборке они
  отсутствуют — Newton fallback to direct solver может быть slow или
  fail. **Mitigation:** Phase 0 task #3 — `ElmerSolver -help` или
  trivial benchmark на Newton с known fixture. Если direct solver
  too slow — добавить `apt install libhypre-dev` (Ubuntu noble)
  до Elmer setup в pilot.Dockerfile. Picard fallback не требует
  Hypre.

- **W2. ZHANG analytical ↔ Kelvin-shell-FEM model gap inherent.**
  PyOM ZHANG reluctance модель предполагает **fully closed magnetic
  circuit** (no leakage, no fringing). 2D-planar FEM даже с
  идеальным Kelvin shell имеет out-of-plane leakage = 0 (по
  определению 2D), но in-plane fringing вокруг air gaps captured.
  ZHANG считает gap reluctance как `R_gap = l_gap / (μ₀ · A_gap)`
  без fringing correction. Net: даже с perfect convergence Elmer
  nonlinear на правильной topology может отличаться от ZHANG на
  ~10-20% inherent model gap. **Implication:** target ±10% может
  быть фундаментально недостижим; acceptance ±25% — single source-
  of-truth gate. Если acceptance тоже не попадает — spec §4 уже
  предусматривает «infrastructure-only closure» как outcome
  (graceful degradation, T129-style). Worth noting в Phase 3 ADR
  что-то типа «ZHANG-FEM model gap ~X% inherent, acceptance ±25%
  consumes this + numerical noise».

- **W3. Newton on Frohlich derivative behavior in saturation.**
  Frohlich-Kennelly монотонно возрастающая, дифференцируемая;
  derivative `dB/dH → 0` асимптотически в `B → B_sat`. Newton
  iteration требует `∂ν/∂B²` для jacobian; в knee region (`B ≈ B_sat
  · 0.9-0.99`) jacobian становится ill-conditioned (большая variance
  в neighborhood). Elmer обычно справляется с Picard relaxation
  `0.5-0.7`, но Newton может расходиться без adaptive damping.
  **Mitigation:** Phase 0 .sif включает `Nonlinear System Relaxation
  Factor = 0.7` + `Nonlinear System Newton After Iterations = 3`
  (Picard первые 3 → Newton). Если Newton расходится — drop to
  Picard-only с `Max Iterations = 50, Convergence Tolerance = 1e-5`
  (T129 Q2 reused). Phase 2 fixates choice в .sif template после
  Phase 0 empirical result.

- **W4. ΔI signal-to-noise в central difference.** ΔI = max(0.01·
  |I_dc|, 0.0001 A) — для T113 pilot fixture I_dc ~ 50 mA это
  ΔI = 0.5 mA. Elmer nonlinear convergence tolerance 1e-5 даёт
  flux precision ~1e-5 · |Φ|; relative noise в (Φ₊ − Φ₋) ~
  2·1e-5/Δrelative ≈ 2e-3 (0.2%) — well below 25% acceptance, OK.
  Но если в Phase 0 Newton tolerance loose'ит (Elmer 26.2 default
  обычно 1e-4 not 1e-5) — relative noise может вырасти до 4%.
  **Mitigation:** explicit `Nonlinear System Convergence Tolerance =
  1.0e-5` в .sif template + `Linear System Convergence Tolerance =
  1.0e-10`. Phase 0 verify.

### Note

- **N1. T113 Stage F linear cross-check Elmer↔GetDP — на разной
  топологии.** Split-coil GetDP даёт 23.78 H; single-coil + Kelvin
  shell Elmer linear даст **другое** значение (другая A-field
  distribution из-за proper open-domain). Spec §4 `relative_difference
  ≤ 0.01` к T113 baseline не применим напрямую. **Решение:**
  cross-check выполняется как «Elmer linear на same fixture даёт
  стабильное значение между runs» (numerical reproducibility,
  не cross-backend agreement). Если потребуется реальный
  Elmer↔GetDP linear cross-check — нужно реализовать также
  single-coil + Kelvin shell в GetDP (отдельный T-ID, не T133
  scope; T127 expansion candidate). Spec §4 уже допускает «или
  на новом baseline с явным docstring обоснованием».

- **N2. `FemMethod` Literal расширение.** Existing `FemMethod =
  Literal['linear', 'nonlinear-frohlich']` не различает backend.
  Если в downstream важно (для логов / diagnostics): расширить
  на `['linear-getdp', 'linear-elmer', 'nonlinear-frohlich-getdp',
  'nonlinear-frohlich-elmer']`. Phase 2 переоценит после
  acceptance — если backend distinction не consumer'ом нужен,
  оставляем существующий literal + docstring contract «который
  adapter, видно по dependency injection».

- **N3. Image size — main Dockerfile delta +300 MB.** T133 Phase 1
  добавит `elmerfem-csc` PPA → `efactory:linux` 6.65 GB → ~6.95 GB.
  CONCEPT §13 «6 GB ceiling» formally нарушен на T112, Vladimir
  confirmed acceptable. Phase 1 commit message fixates delta как
  documentation; future slimming task — отдельный T-ID (T120
  AppImage cleanup уже частично адресует; будет ещё одна).

- **N4. Picard `RelaxationFactor` default.** T129 GetDP использовал
  `RelaxationFactor 0.7` (W1 mitigation для Picard на saturation
  knee). Elmer аналог: `Nonlinear System Relaxation Factor = 0.7`.
  Phase 0 default — same value; Phase 2 tunes если convergence
  drift'ит.

- **N5. `ElmerGrid 14 2 mesh.msh` — +1 subprocess в pipeline.** GetDP
  pipeline: `gmsh → getdp` (2 subprocess); Elmer pipeline: `gmsh →
  ElmerGrid → ElmerSolver` (3 subprocess). Performance hit ~40 ms
  per T113 baseline (ElmerGrid converts mesh files без heavy
  computation); negligible vs ~3-10 s ElmerSolver time.

- **N8. ElmerGrid `-autoclean` flag renumber'ит Physical tags
  (Phase 0 finding, 2026-05-21).** T113 pilot использовал
  `ElmerGrid 14 2 geometry.msh -autoclean -out mesh-elmer`; флаг
  `-autoclean` renumber'ит entity tags в sequential 1-indexed
  (Physical Surface tags 1-7 + Physical Curve tag 8 → Bodies 1-7
  + Boundary 1). Без `-autoclean` (как в моих probes Phase 0
  initial run) ElmerGrid сохраняет original Gmsh Physical tags
  → `Target Boundaries(1) = <original_tag>` обязательно.
  **Phase 1/2 implication:** Elmer adapter pipeline ДОЛЖЕН
  использовать `-autoclean` (T113 convention) — это даёт
  consistent BC numbering, predictable .sif templates. Auto-memory
  `feedback_elmer_savescalars_quirks` будет расширена этим pitfall'ом.

- **N9. CheckKeyword "Unlisted keyword: [a]" — informational only.**
  Elmer 26.2 reports `Unlisted keyword: [a] in section: [boundary
  condition 1]` для `A = Real 0.0` Dirichlet BC, но Dirichlet
  применяется корректно (`EnforceDirichletConditions: Enforcing
  total of N Dirichlet conditions`). Warning не блокирующий —
  variable `A` registered через `Solver Variable = "A"`, BC
  matching работает по variable name, keyword catalog
  предусматривает только subset known keywords. T113 .sif
  тоже выдавал этот warning (verified Phase 0 probe).

- **N6. Phase 0 pilot — единая branch, отдельный commit.** Per
  project rule «один PR — один коммит», Phase 0/1/2/3 коммитятся
  как четыре отдельных commit'а на ветке `T133-elmer-fem-pivot`,
  squash в один при merge. Phase 0 commit может содержать
  pilot.Dockerfile + smoke `.sif` + spec revision (если Phase 0
  обнаружит pivot — например, Dirichlet fallback); Phase 1/2/3 —
  adapter implementation, integration tests, closing.

- **N7. Auto-memory reuse.** `feedback_elmer_savescalars_quirks` (4
  pitfall'а) — directly applicable для T133 .sif design. Plus
  `feedback_kicad_sexpr_lessons` Y-down note — NOT applicable
  (Elmer 2D coordinates стандартные Y-up); упомянуто только для
  напоминания, что разные toolchains имеют разные orientation
  conventions.
