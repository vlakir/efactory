# Backlog

Парковка идей, побочных находок и «надо бы потом починить».

**Правило:** если в процессе работы над текущей задачей Claude или
Разработчик замечают что-то постороннее — оно идёт сюда, а не в текущий
коммит. Это защищает от расползания scope.

Это **не формальный таск-трекер** со сроками и метриками — это парковка
идей. Но **порядок имеет значение**: сверху — то, что планируется
ближайшим, ниже — менее срочное (FIFO по умолчанию, можно поднимать
приоритетное наверх). Когда из бэклога что-то берётся в работу — оно
вырастает в задачу или спеку (`specs/T<NNN>-…`) и удаляется отсюда.

## Формат

`- **T<NNN>** — [<дата находки>] <короткое описание> — <опционально: контекст / откуда всплыло>`

ID присваивается при создании; новый = `max(существующих T-ID в
BACKLOG.md, BOARD.md и CHANGELOG.md) + 1`. ID не переиспользуется
и сохраняется при перетекании задачи между BACKLOG и BOARD; после
релиза задача переходит в `CHANGELOG.md` (с тем же T-ID), что
гарантирует уникальность между релизами.

## Items

Задачи дорожной карты концепта (CONCEPT.md §13), фазы 1a/1b/2/3/4/5/6/7/8.
Плюс отдельный раздел архитектурных follow-up'ов сверху — то, что
выявилось при работе над фундаментом T085 / Walking Skeleton и не
вписывается напрямую в фазы дорожной карты.

### Архитектурные follow-up'ы Walking Skeleton

<!-- Задачи, выявленные при работе над hexagonal-фундаментом (T085)
     и его обкаткой полным CRUD-набором (T086–T092). Источник —
     ретроспективы milestone'ов в `CHANGELOG.md`. -->

- **T170** — [2026-06-02, discovered during T025 self-review]
  **`/sim-run` slash вызывает несуществующую CLI-команду.**
  `docker/runtime-agent-commands/sim-run.md` шаг 2 даёт agent'у
  инструкцию выполнить `efactory bridge sim-run --schematic <SCH>
  [--analysis TYPE]`, но реальная сигнатура `bridge sim-run` —
  subapp с subcommands `op|tran|ac` без `--schematic` option (только
  positional `<netlist>`). Существующий equivalent для full pipeline
  «.kicad_sch → netlist → симуляция» — `efactory bridge design-to-sim
  <op|tran|ac> <PROJECT> --schematic <SCH>`. То есть текущий slash
  при попытке agent'а выполнить даст `Error: No such option:
  --schematic` (или похожее), и T025 auto-show (`schematic-render:`
  строки в stdout, зацеплено в `_execute_design_to_sim` adapter)
  не сработает до фикса slash.

  **Acceptance:**
  - Slash инструкция исправлена так, чтобы agent выполнял реально
    работающую команду (`bridge design-to-sim <analysis> <PROJECT>
    --schematic ...`).
  - Реализация требует: (a) parse `--analysis TYPE` из `$ARGUMENTS`
    → subcommand `op`/`tran`/`ac` (default `op`), (b) auto-detect
    `PROJECT` (project.yaml в cwd / parents; если нет — попросить
    у пользователя).
  - L2 deterministic regression test: invocation полученной
    инструкции даёт exit 0 на acceptance fixture (e.g. созданный
    `project create --template op-amp-inverting`).
  - L3 smoke: agent выполняет `/sim-run` в `efactory:linux`
    контейнере, видит результат симуляции **и** T025-rendered PNG
    (auto-show отрабатывает через корректную команду).

  **Контекст.** Обнаружено при self-review T025 (PR #111).
  Существовавший gap, не введён T025 — но T025 auto-show опирался
  на работающий slash, поэтому фикс становится первой задачей по
  использованию T025 на end-user UX. T025 verified independently
  через CLI `efactory bridge design-to-sim` (Phase B e2e tests),
  но slash-level integration требует T170.

  **Возможный scope-creep:** похожая проблема может быть в других
  slash-командах (`/measure-gain`, `/measure-bandwidth`,
  `/measure-thd`, `/measure-phase-margin`) — они тоже могут
  указывать `--schematic` на subapp'ах без него. Перепроверить и
  при необходимости расширить T170 или завести parallel T-IDs.

<!-- T094 закрыт ADR от 2026-05-19 в DECISIONS.md (вариант "в":
     /ultrareview как primary external review, CodeRabbit best-effort). -->

<!-- T134 переехала в BOARD.md → Doing 2026-05-26 после Phase 1b
     закрытия (Claude Code as frontend → KB consumer существует).
     Spec — specs/T134-agent-knowledge-base/spec.md (Draft, 11
     clarify-вопросов). Originally заведено 2026-05-21 в Phase E
     T131 с 9 control examples из T131+T132+T133; в spec добавлен
     10-й example «agent.command-routing» (typical user-request →
     slash-command mapping). -->
<!-- ORIGINAL T134 ENTRY (full text moved to spec §1-§2 context):

- **T134** — [2026-05-21, заведено в Phase E T131] **Agent Knowledge
  Base — infrastructure для накопления technical knowledge у
  efactory CLI agent'а.**

  **Контекст.** efactory CLI agent (будущий, фаза 1b «Чат-клиент»)
  будет отдельной runtime-сущностью со своими ресурсами; **не имеет
  доступа** к auto-memory Гвидо (вне репо) и mem0 (приватная Vladimir
  + Гвидо). Md-файлы репо (`DECISIONS.md`, `CHANGELOG.md`, `specs/*`,
  `CLAUDE.md`) — dev-process артефакты для Гвидо и человека-ревьюера,
  **не** primary канал знаний для agent'а. Архив сохранится в git,
  но это не должно быть основным механизмом передачи знаний.

  **Цель.** Слой persistence для efactory CLI agent: формат хранения,
  initial-seed content (curated на release-bake), append-API (агент
  пополняет в проде), retrieval (context-aware lookup перед
  принятием решения).

  **Контрольный пример (regression target из T131).** Каждый из этих
  3 уроков должен быть представлен в KB после implementation:

  1. **«Saturable магнетика с активными элементами требует XSPICE
     gyrator-capacitor (lcouple+core), не PWL current-source».**
     Источник: Phase E redesign 2026-05-21. PWL B-source с C_int
     integrator + active EL84 Koren model давал numerical blow-up
     (magnitudes ~1e+65) из-за algebraic loop. XSPICE gyrator-cap
     (Hamill 1993) изолирует нелинейность в магнитной области.
     ⇒ Если agent попросят добавить новую saturable модель
     (capacitor, inductor) — должен предложить gyrator-cap путь.

  2. **«Floating secondary OPT требует R_dc_leak (~1 MΩ к GND) перед
     Fourier analysis».** Источник: Phase D acceptance test
     post-processing 2026-05-21. Без DC reference v(/sec_a) получает
     arbitrary DC offset, ngspice Fourier даёт нерелевантную fundamental
     magnitude. ⇒ Если agent проектирует netlist post-processing для
     любого транса с floating secondary — должен auto-inject leak.

  3. **«Saturation contribution metric = THD@f_low - THD@f_high как
     diagnostic для saturable models».** Источник: Phase E
     acceptance gate 2026-05-21. Чистая abs-THD bound недостаточна
     (compact-core configurations выходят за published [1%, 5%]
     band published для больших cores); positive saturation
     contribution = saturable модель реально активна. ⇒ Если agent
     создаёт похожий THD-acceptance gate — должен включать
     saturation contribution diagnostic.

  **Контрольный пример (regression target из T132).** Каждый из этих
  3 уроков должен быть представлен в KB после implementation:

  1. **«PyOM `calculate_leakage_inductance` mesh broken на всех
     1.3.0→1.3.12 versions — использовать pure-Python Erickson
     sandwich formula instead».** Источник: Phase B investigation
     2026-05-21 (4+ часа). Любой call к
     `pyom.calculate_leakage_inductance(magnetic, freq, idx)` после
     `pyom.wind(...)` consistently возвращает `[CALCULATION_ERROR]
     Mesh generation failed: induced field data is empty` — и через
     official `simulate(inputs, magnetic, models)` pipeline тоже.
     Cross-material sweep (12 PyOM materials), version sweep, и
     `magnetic_autocomplete` / `process_inputs` orchestration — не
     помогают. ⇒ Если agent попросят посчитать leakage inductance
     OPT — должен НЕ пытаться PyOM mesh-path, а использовать
     existing adapter `adapters.outbound.leakage_inductance_analytical.
     AnalyticalLeakage` (Erickson formula + PyOM catalog для
     geometry).

  2. **«Interleaving reduction: Lσ ∝ 1/N², где N = число inter-
     winding interfaces в pattern (P-S → N=1, P-S-P → N=2,
     P-S-P-S-P → N=4)».** Источник: Erickson & Maksimović §15.5 +
     Hurley & Wölfle §4.6, реализовано в `formula.py` Phase C
     2026-05-21. Standard sandwich-transformer leakage с
     interleaving reduction theorem. Verified exact для zero-
     insulation case на pilot (σ_2/σ_3 = 4.0, σ_2/σ_5 = 16.0).
     ⇒ Если agent спросят «как уменьшить HF-rolloff аудио OPT» —
     должен предложить interleaved sandwich layout, и оценить
     эффект через N² factor; для symmetric 5-section vs P-S
     layout reduction = 16×.

  3. **«PyOM bobbin processedDescription.columnWidth/columnDepth
     = null / 5e-315 uninitialized memory garbage; patch needed для
     любого FEM-touching path».** Источник: Phase B probe 2026-05-21.
     `Bobbin E42/15` из `pyom.get_bobbins()` имеет
     `columnWidth = None` и `columnDepth ≈ 5.45569116e-315` — bug в
     PyOM C++ catalog initializer. PyOM `calculate_leakage_inductance`
     bails out с `INVALID_BOBBIN_DATA` без patches; mesh API
     дополнительно требует full bobbin geometry. Patch: `columnWidth
     ← bobbin.functionalDescription.windingWindows[0].width`,
     `columnDepth ← core.processedDescription.depth`. ⇒ Если agent
     попытается ещё один PyOM FEM-touching path (например,
     `calculate_magnetic_field_strength_field`, `plot_field_map`) —
     должен auto-apply этот patch. Альтернатива: использовать только
     PyOM catalog-only APIs (`find_*_by_name`, `calculate_core_data`),
     которые не trigger mesh validation.

  **Контрольный пример (regression target из T133).** Каждый из этих
  3 уроков должен быть представлен в KB после implementation:

  1. **«2D-planar FEM на E-core inherent factor ~3× от ZHANG; для
     closure нужен 3D mesh».** Источник: T133 Phase 3 empirical
     (2026-05-21). Все 2D-planar варианты (split-coil + Dirichlet,
     single-coil + Infinity BC, linear или nonlinear Frohlich) дают
     +182-242% к PyOM ZHANG analytical на pilot fixture OPT 6П14П SE.
     Это **physics, не bug**: ZHANG reluctance model assumes fully
     closed magnetic circuit, 2D-planar inherently captures 3D
     out-of-plane leakage и fringing effects. 3D mesh с gaps закрыл
     gap до -13.3% (Lp = 6.04 H, acceptance ±25% к ZHANG 6.96 H).
     ⇒ Если agent попросят FEM cross-check к ZHANG-style analytical
     для E-core / EI / EE OPT — должен сразу планировать 3D mesh
     (`emit_e_core_geo_3d` + `dimensionality='3d'`), пропустить 2D
     iteration. Для axisymmetric topology (toroidal, pot) 2D-planar
     OK; для leakage-only (T132/T135) 2D также достаточен.

  2. **«Elmer 3D Whitney AV + MUMPS direct ceiling ~10K nodes на
     4 GB RAM dev-host; iterative path заблокирован в default
     elmerfem-csc PPA».** Источник: T133 Phase 3d.2 (2026-05-21).
     39K tetra → segfault rc=139 + system crash. MUMPS direct
     O(N²·BW) memory blow-up на edge basis. Iterative alternatives
     не работают в PPA build: `Preconditioning = BoomerAMG` не
     сходится для edge basis (designed для node Laplacian),
     `Preconditioning = "ams"` (Auxiliary Maxwell Space — proper
     для edge Maxwell) reported `Unknown preconditioner type: ams,
     feature disabled` (Hypre AMS не вкомпилирован в PPA).
     ⇒ Если agent создаёт Elmer 3D mesh для full E-core OPT:
     **default MUMPS direct с mesh sizing 20μm/5mm** (Phase 3d.2
     proven baseline, 10K nodes, ~14 s). Mesh > 15K nodes требует
     либо Elmer rebuild с AMS (отдельная задача), либо больше RAM,
     либо адаптивный mesh refinement (Distance + Threshold fields)
     для concentration nodes только near gaps. **НЕ пытаться mesh
     > 20K без verified iterative path** — система Vladimir-а
     перезагружалась.

  3. **«Elmer Stranded Coil mechanism требует connected 3D loop;
     для OPT primary через два disjoint windows нужны mesh bridges
     через top/bottom yokes».** Источник: T133 Phase 3d.2 Coil
     probe (2026-05-21). Закрытый coil (`Coil Closed = Logical True`)
     с `Master Bodies(2) = 2 3` (left + right window volumes) даёт
     `CoilSolver: Crappy potentials: No positive/negative current
     sources` — windows не connected без yoke bridges, current loop
     не замкнут. Open coil + `Coil Start` / `Coil End` BCs пропускает
     current через CoilSolver, но Whitney AV не consume coil current
     без proper Component-binding syntax (Component-level `Coil Type`
     / `Number of Turns` reported как `Unused keywords`; binding
     requires Elmer Models Manual investigation).
     ⇒ Если agent моделирует OPT primary winding на center leg в 3D
     Elmer: **либо** добавить mesh bridges через top + bottom yokes
     (closed 3D loop, preferred — physically correct), **либо**
     использовать simple Body Force `Current Density 3 = N·I/A`
     vector (works для acceptance ±25%, но div(J) implicitly
     violated; T133 Phase 3d.2 baseline). Coil mechanism с proper
     binding — open follow-up T-ID.

  **Acceptance.**
  - Spec формата KB (chunk schema, indexing strategy, retrieval API).
  - Skeleton implementation (read + write API минимум).
  - Initial-seed loader (bootstrap-script: parse curated content
    из репо при первом запуске efactory CLI agent).
  - Acceptance test: задаются **9 регрессионных query** из T131 +
    T132 + T133 control examples выше (по 3 от каждой задачи), KB
    возвращает релевантные chunks с правильным ranking.
  - **Не входит**: полный seeding текущих знаний (отдельная задача
    после KB skeleton готов); production-quality vector DB tuning.

  Scope ~3-5 дней. **Blocked by Phase 1b «Claude Code integration»** — KB
  спецификация зависит от characteristics самого agent'а (framework,
  retrieval strategy, context window, interaction API). До появления
  agent'а KB — premature investment без consumer'а. Знания на этапе
  разработки efactory собираются в .md-файлы репо + auto-memory
  Гвидо; T134 их **мигрирует в agent KB** когда agent появится.

  Не зависит от: T131 (T131 уже закрыт, ADR в `DECISIONS.md` +
  docstring обогащения адресуют immediate dev-process persistence).
-->

- **T154** — [2026-05-26, заведена в T134 Clarify Q-F → c]
  **Full migration dev-process knowledge → agent KB.**
  T134 core scope = infrastructure + 10 control examples. После
  его merge — отдельная curation-задача: пройти `DECISIONS.md`,
  `CHANGELOG.md`, ключевые `feedback_*` auto-memory Гвидо и
  релевантные mem0-entries; выделить те, что нужны runtime-агенту
  (не dev-process); сформировать заявку KB-entries в built-in seed
  (`docker/runtime-agent-knowledge-base/`).

  Не auto-portable: каждый entry требует review Vladimir + Гвидо
  на «нужно ли это агенту в проде» (vs «нужно только разработчику
  efactory»). Скоринг pessimistic: ~30-50 entries после фильтрации
  из сотен existing artefact'ов.

  **Phased:**
  - Phase 1 — `DECISIONS.md` ADR'ы, релевантные для проектирования
    (не «как мы выбрали Kùzu»): 6П14П SE-amp specific decisions,
    saturable backend choice, FEM-tool selection.
  - Phase 2 — `CHANGELOG.md` retrospectives (что зашло / что не
    зашло) — extract «lesson learned» nuggets.
  - Phase 3 — auto-memory Гвидо `feedback_*` files — те, что
    domain knowledge (KiCad pitfalls, FEM gotchas), не dev-process.
  - Phase 4 — mem0 review — что из приватной памяти cross-applicable
    в agent KB.

  Acceptance: ≥30 entries в built-in seed после migration; каждый
  cross-reviewed на «нужно агенту»; обновлены existing 10 control
  examples если применимо.

  Не блокирует: продукт работает с 10 control examples + agent сам
  пополняет в проде через `/kb-add`.

- **T135** — [2026-05-21, заведено в Phase B T132] **FEM cross-
  validation analytical leakage Lσ (T132 Phase C primary backend).**

  **Контекст.** T132 закрыт с pure-Python analytical backend
  (Erickson sandwich-transformer formula); acceptance gates passing
  на pilot fixture OPT_SE_5K_8: Lσ(5-section) = 6.5 mH (в spec band
  [0.1, 10] mH), monotonicity 1/N² ratio exact. PyOM
  `calculate_leakage_inductance` исключён из pipeline после
  investigation (1.3.0→1.3.12 version sweep: long-standing
  `[CALCULATION_ERROR] Mesh generation failed`, не version-specific).
  Analytical точность ±20-30% — приемлемо для T132 spec, но не
  hi-precision. FEM cross-check валидирует analytical formula на
  pilot fixture'ах с known FEM-truth.

  **Acceptance** (один из путей):
  - **(a) PyOM upstream issue resolved.** Воспроизвести minimal
    repro для https://github.com/OpenMagnetics/PyOpenMagnetics/issues,
    дождаться patch / workaround. Если рабочий — добавить
    `PyOmFemLeakage` adapter параллельно analytical, cross-check
    в acceptance test.
  - **(b) Elmer FEM pivot (T133 расширяется).** Реализовать leakage
    backend через Elmer cross-section solver (short-circuit
    secondary, energy integral) → новый adapter `ElmerLeakage`
    тот же port. Cross-check vs analytical на pilot; если в
    пределах ±25-30% — Erickson formula valid, иначе tighten.
  - **(c) GetDP+Gmsh leakage extension (T113 stack reuse).** Уже
    интегрированный FEM стек, расширить `.pro` template на leakage
    (short-circuit + energy integral). Lower effort чем Elmer
    pivot; same hexagonal port.

  **Acceptance pilot (любой FEM backend):** на OPT_SE_5K_8 pilot
  (E 42/15, 3500/140 turns, P-S-P-S-P 5-section), FEM Lσ должен
  match analytical 6.5 mH в пределах ±25% (т.е. FEM ∈ [4.9, 8.1] mH).
  Если outside — open analytical formula review, потенциально
  tighten formula refinements (proper per-section thickness, Dowell
  AC effects, etc.).

  **Не зависит от:** T132 Phase A/B/C уже merged (analytical
  primary backend + acceptance gates passing). Domain/port не
  меняются — только новый adapter добавляется параллельно.

  **Зависит от:** T133 Elmer pivot ready (preferred path) ИЛИ GetDP
  template extension (T113 stack). T135 — quality improvement,
  не блокирует existing T132 use case.

- **T136** — [2026-05-21, заведено в Phase 3e T133] **Elmer rebuild
  с AMS preconditioner — target ±10% к ZHANG closure.**

  **Контекст.** T133 Phase 3d.2 закрылся на acceptance ±25% (Lp=6.04H,
  -13.3% к ZHANG). Target ±10% [6.26, 7.65 H] не достигнут (off by
  3.5%). Mesh refinement к 39K nodes → MUMPS direct OOM/system crash;
  iterative alternatives (BoomerAMG / ILU) не сходятся для Whitney AV
  edge basis. **AMS preconditioner** (Hypre Auxiliary Maxwell Space,
  designed for edge basis curl-curl Maxwell) reported `feature
  disabled` в default `elmerfem-csc` PPA build.

  **Acceptance.**
  - Build Elmer с AMS preconditioner enabled (Hypre rebuild with
    `--enable-ams` или equivalent, потом Elmer link against custom
    Hypre).
  - Custom efactory:linux image variant `efactory:linux-elmer-ams`
    OR replace default elmerfem-csc PPA с custom build.
  - Mesh refinement к 50K+ nodes на pilot OPT 6П14П SE через
    iterative + AMS: Lp ∈ [6.26, 7.65] H = ±10% к ZHANG achieved.
  - Integration test обновлён на tighter baseline (±5% drift).

  **Альтернатива:** server-class machine с большим RAM (32+ GB)
  позволил бы MUMPS direct на 50K nodes без iterative path.

  Scope ~3-5 дней (Hypre/Elmer build + AMS configuration tuning).
  Триггер: реальный client case требующий ±10% precision.

- **T137** — [2026-05-21, заведено в Phase 3e T133] **3D Elmer Coil
  mechanism с mesh bridges через yokes — alternative path к ±10%.**

  **Контекст.** T133 Phase 3d.2 Coil mechanism probe (Stranded coil
  + CoilSolver) выявил: для OPT primary через два disjoint windows
  (left + right) closed coil не сходится ("Crappy potentials"),
  open coil + Start/End BCs пропускает CoilSolver но Whitney AV
  не consume coil current. Body Force vector path работает но
  div(J) implicitly violated (асимметричная current distribution
  — возможный источник residual -13.3% gap к ZHANG).

  **Подход.**
  - Расширить `emit_e_core_geo_3d` mesh: add `coil_bridge_top` и
    `coil_bridge_bottom` Volume boxes — extend primary winding
    region через top/bottom yokes (вокруг center leg), создавая
    closed 3D loop.
  - .sif: Component с `Coil Type = "stranded"` + `Coil Closed =
    True` + `Master Bodies(4) = 2 3 [bridge_top] [bridge_bottom]`.
  - CoilSolver pre-compute proper closed-loop current vector.
  - WhitneyAV Solver: verify `Coil Use W Vector` binding works
    (Phase 3d.2 reported keyword Unused; need Elmer Models Manual).

  **Acceptance.**
  - 3D mesh с bridge volumes generates cleanly (OCC boolean
    sequential).
  - CoilSolver converges на closed loop, не "Crappy potentials".
  - Whitney AV consumes coil current vector, Lp вычисляется.
  - Acceptance к ZHANG ±10% [6.26, 7.65 H] на OPT 6П14П SE.

  Scope ~2-4 дня (mesh redesign + Coil keyword investigation).
  Альтернатива к T136 (Elmer rebuild).

- **T138** — [2026-05-21, заведено в Phase 3e T133] **PyOM
  `lateral_x` semantics investigation + ECoreDimensions fix.**

  **Контекст.** T133 Phase 3b/3d empirical: для OPT 6П14П SE
  (E 42/21/15) PyOM `processedDescription.columns[1].coordinates[0]`
  = ±18.088 mm, `width` = 9.075 mm. Это даёт outer lateral leg
  edge x = 22.626 mm > core half-width 21.075 mm — geometrically
  impossible. Phase 3d использует geometrically-derived bounds
  из `core_w - center_w - 2·window_w` (lateral width = 6.025 mm,
  не PyOM-reported 9.075 mm).

  Гипотезы:
  - PyOM column.width — это full leg + bobbin flange, не iron.
  - PyOM column.coordinates — center с different reference frame.
  - PyOM data inconsistency для конкретного shape E 42/21/15.

  **Acceptance.**
  - Investigate PyOM data structure через minimal probe (calculate_
    core_data для E 42/21/15 + другие shapes, сравнить с datasheet
    geometry).
  - Fix `ECoreDimensions.from_pyom_core`: либо correct interpretation
    (e.g., `lateral_w = column.width − 2·bobbin_thickness`), либо
    fall back на geometrically-derived bounds explicitly.
  - Tests cover the fix.

  Scope ~1-2 дня. Влияет на T133 3D mesh accuracy, потенциально
  закрывает часть остатка к ±10% target.

- **T139** — [2026-05-21, заведено в Phase 3e T133] **3D Elmer
  nonlinear-frohlich path (H-B Curve + Newton в 3D Whitney AV).**

  **Контекст.** T133 Phase 3c integration: `material_model =
  'nonlinear-frohlich'` + `dimensionality = '3d'` → `NotImplementedError`.
  3D nonlinear path требует:
  - 3D Whitney AV solver с `H-B Curve = Variable Coupled iter; Real
    cubic; ... End` (verified в 2D Phase 0; need 3D-specific
    keyword `H-B Curve Variable` per strings probe).
  - Newton iteration на 3D edge basis — потенциально convergence
    issues аналогично T133 Phase 2 2D nonlinear (IEEE_UNDERFLOW
    на низком DC bias).
  - DC-bias central-diff reuse (T129 / T133 Phase 2 logic).

  **Acceptance.**
  - 3D nonlinear .sif template + adapter `_solve_nonlinear_3d`
    method.
  - Integration test на OPT 6П14П SE: nonlinear-frohlich-3d даёт
    finite L_inc, сравним с linear-3d baseline 6.04 H.
  - Если IEEE_UNDERFLOW повторяется — `feedback_fem_2d_nonlinear_
    instability` уже фиксирует known limit; consider Picard
    relaxation, smaller ΔI floor, или 3D-specific tuning.

  Scope ~3-5 дней. Triggers: real client case requiring
  saturation-aware 3D FEM inductance (e.g., flyback choke с
  high DC bias).

### Tech Debt (отложено)

<!-- Задачи признанные нужными, но без активного владельца / времени.
     Не идут в Doing до явного решения Разработчика «берём». -->


- **T162** — [2026-05-30, found during T021 Phase A]
  `tests/integration/application/__init__.py` создаёт коллизию
  namespace с `src/application/` при `--import-mode=importlib`
  + `pythonpath=["src"]`. Симптом: при изолированном запуске
  `pytest tests/integration/application/...` все тесты падают
  `ModuleNotFoundError: No module named 'application.X'`, хотя в
  полном `pytest` (когда unit tests прогружают src.application.*
  первыми) проходят зелёные. T021 обошёл — расположил unit-style
  use-case-test в `tests/unit/application/` (там `__init__.py` нет).
  **Фикс:** удалить `tests/integration/application/__init__.py`,
  проверить что `test_analyze_distortion_spectrum.py` и
  `test_mag_verify_field.py` все ещё прогоняются. Возможно надо
  удалить `__init__.py` из всех `tests/**/` для consistency.
  Acceptance: `uv run pytest tests/integration/application/` 
  собирает и проходит зелёным в изолированном run; `uv run pytest`
  полным проходом тоже зелёный.
- **T003** — [2026-05-15, parked 2026-05-19 до Phase Cross-platform]
  bootstrap.ps1 для Windows: то же самое через winget/chocolatey +
  pip. **Parked:** efactory переходит на Docker-distribution (Linux
  only в текущей фазе). Windows-поддержка — через Docker Desktop /
  WSLg в отдельной Phase Cross-platform (см. ниже).
- **T011** — [2026-05-15, parked 2026-05-19] `kicad-sim-chat`:
  терминальный UI на Rich (история, ввод, рендер ответов).
  Acceptance: интерактивный чат работает в любом современном
  терминале, поддерживает прокрутку и подсветку. **Parked:**
  решено использовать Claude Code как frontend (см. T108 OpenCode
  pilot и будущий ADR «Frontend = готовый AI-терминал, а не свой
  клиент»). Возвращать к T011 — только если оба готовых решения
  не подойдут после пилота.
- **T108** — [2026-05-19] **Spike: пилотное знакомство с OpenCode**
  как альтернативным frontend'ом efactory (MIT, Go-based TUI,
  multi-provider через Models.dev, MCP local+remote, mid-session
  model switch). Цель — оценить, закрывает ли OpenCode дух
  T012-T019 «бесплатно» и стоит ли менять Claude Code → OpenCode
  как основной фронтенд.
  Acceptance: за одну вечернюю сессию проверены и зафиксированы
  выводы в `specs/T108-opencode-pilot/notes.md`:
  (a) установка и запуск на dev-машине Владимира (Linux);
  (b) подключение хотя бы одного efactory MCP-сервера через
  `opencode.json`, вызов тула из чата;
  (c) переключение моделей mid-session (Anthropic ↔ OpenAI-compat
  ↔ локальный Ollama, что доступно);
  (d) есть ли аналог `CLAUDE.md` (project-level system prompt) и
  слэш-команд;
  (e) рендер markdown / code / таблиц в TUI на качественном
  уровне;
  (f) поддержка side-by-side `/compare`-сценария (T020) — есть /
  нет / можно ли добавить плагином.
  По итогам — ADR «Frontend для efactory: Claude Code vs OpenCode»
  в `DECISIONS.md` и решение по судьбе T011-T019.
- **T120** — [2026-05-19, parked 2026-05-21] **Cleanup: удалить
  AppImage-detection из `platform_layer`.** После Phase 0.9
  KiCad/FreeCAD внутри контейнера всегда через apt (в PATH);
  AppImage-fallback в `src/adapters/outbound/platform_native/
  platform_layer.py` становится dead code. Удалить
  `_scan_appimage_locations`, `_detect_kicad_cli_via_kicad_appimage`,
  multi-call AppImage logic; почистить glob-патрены и known
  locations (`~/Загрузки/`, `~/AppImages/`, `~/<app>/`). Подправить
  тесты в `tests/integration/adapters/platform_native/`: убрать
  AppImage reality-tests, оставить PATH-detection через apt.
  Пройтись по `pytest.mark.skipif` в integration/e2e — оставить
  только условие «kicad in PATH». Spec T009 пометить как
  partially-replaced. Acceptance: 0 строк кода специфичных для
  AppImage; все тесты зелёные при KiCad из apt; PR ловится
  pre-push gate как обычно. **Parked:** dead code не блокирует
  ничего; при взятии расширить scope до «упростить `platform_layer`
  до PATH-only lookup» — FreeCAD AppImage внутри образа,
  симлинк `/usr/local/bin/freecadcmd` (T112), весь native-AppImage
  discovery становится мёртвым, не только KiCad-AppImage путь.
- **T124** — [2026-05-20, parked 2026-05-21] **freecad-mcp wrapper
  + integration.** Acceptance T112 изначально включал «freecad-mcp
  подключается, базовые tool-calls работают»; вынесено в отдельную
  задачу (Vladimir 2026-05-20 clarify-1). Содержание: Python
  wrapper поверх `freecadcmd` в `src/adapters/outbound/freecad/`,
  MCP-сервер с минимальным set'ом tool-calls (open document, create
  sheet metal base wall, add bend, unfold, export STEP/DXF),
  регистрация в общем MCP-реестре efactory. После выбора решения
  T108 (Claude Code как frontend) — wrapper должен отвечать на
  tool_use из агента. Acceptance: запуск MCP-сервера внутри
  efactory:linux, smoke tool-call «open empty document и create
  base wall» возвращает path к сохранённому `.FCStd`. Не
  блокировано: T112 (FreeCAD CLI / GUI) уже даёт `freecadcmd`,
  на котором wrapper может работать сразу. **Parked:** FreeCAD
  сейчас драйвится Bash-вызовом `freecadcmd <macro.FCMacro>`
  (см. `scripts/gen-bracket-demo.FCMacro`), что покрывает
  агент-driven workflow без отдельного MCP-уровня. Возвращать
  после T108 ADR и появления конкретного use case, где
  stateless subprocess не годится (например, открыть документ
  → ряд правок → save с сохранением состояния между
  tool-call'ами).

<!-- T141 переехала в BOARD.md → Doing 2026-05-27 (триггер — текущий
     build T024+T134 идёт ~40-60 мин; Vladimir захотел инфраструктуру
     для ускорения параллельно). Реализован напрямую без spec'и:
     ≤2 ч, 2 bash-wrapper'а + README note. -->
<!-- ORIGINAL T141 ENTRY (full text moved to BOARD + CHANGELOG):

- **T141** — [2026-05-24, заведено по дороге в T013] **Dev-only
  build acceleration: `efactory-build-dev` wrapper с
  `docker buildx --cache-from/-to type=local`.**

  **Контекст.** Build `efactory:linux` в T013 на медленном канале
  занял ~1.5 ч (apt-download KiCad/FreeCAD-deps + Python deps через
  uv sync + npm install Claude Code). Docker layer cache работает,
  но только при идентичном Dockerfile + контексте; bump'ы apt-deps
  или ARG в начале stages инвалидируют большие куски (как было с
  ARG до перемещения).

  Vladimir 2026-05-24: **«пользователь должен честно тянуть»** — то
  есть Dockerfile **не должен** содержать BuildKit-specific syntax
  (`--mount=type=cache,target=...`), чтобы остаться портативным для
  обычного `docker build` без buildx. Ускорение — на уровне
  *команды сборки*, не Dockerfile.

  **Acceptance.**
  - `scripts/efactory-build-dev` (или Makefile-target) — wrapper:
    ```
    docker buildx build \
      --cache-from type=local,src=$HOME/efactory-buildcache \
      --cache-to   type=local,dest=$HOME/efactory-buildcache,mode=max \
      -t efactory:linux .
    ```
  - Документация: short note в `README.md` § Development про
    предустановку `docker-buildx-plugin` (`sudo apt install
    docker-buildx-plugin`) и использование dev-wrapper'а.
  - Acceptance: после первого «прогревочного» build (длинный, как
    обычный) **повторный** build без изменений Dockerfile + контекста
    проходит за **секунды** (только final layers).
  - Dockerfile остаётся portable — `docker build` без buildx
    работает как сейчас (T013 acceptance).

  Опционально (если будет полезно):
  - `--cache-from type=registry,ref=ghcr.io/vlakir/efactory:cache`
    для распределённого cache между dev-машинами и CI; параллель к
    T115 publish workflow.
  - Аналогичный wrapper `efactory-build-libs-dev` для
    `Dockerfile.libs`.

  Scope ~1-2 часа: установка buildx, написание wrapper, smoke,
  README-note.

  Не блокирует: текущий `docker build` работает (T013 closed).
  Триггер: следующий долгий build, когда захочется выиграть
  20+ минут.
-->


<!-- T142 переехал в BOARD.md → Done 2026-05-27 одной сессией
     (compact, ~140 LOC + 17 tests, без spec'и). См. BOARD.md →
     Done. -->

- **T143** — [2026-05-25, заведено по дороге в T016] **`PostToolUse`
  hook для real-time sim-results refresh в Claude Code.** Сейчас
  `SessionStart` hook (T016) показывает sim-results только при старте
  сессии. Если агент в той же сессии запустил `sim_run` через `Bash`,
  новый JSON в `.efactory/sim-results/` появился, но контекст не
  обновится до `/clear` / `/compact` / нового стартапа. Решение —
  `PostToolUse` hook (Claude Code docs §Hooks), реагирующий на
  `Bash` tool, и при изменении `.efactory/sim-results/` инжектирующий
  diff в следующее сообщение.
  Acceptance: после `sim_run` запуска агент в той же сессии видит
  новый sim-результат без manual `Read`. Hook latency < 100 ms
  (срабатывает на каждый tool call — не должен замедлить агента).
  Out of scope T016 потому что: (а) увеличивает scope; (б) `PostToolUse`
  тонкое решение, требует продуманного UX (не каждый Bash-tool call
  читает sim-results, нужен smart change-detection); (в) для пилотного
  использования T016 hook'а достаточно: пользователь может явно
  `/clear` после симуляции и получит свежий контекст. Триггер —
  когда захочется доп. seamless.

<!-- T144 absorbed by T022 (2026-05-27): sweep tabular numerical output
     + CSV/JSON gap входит в Phase A scope T022 (Tabular output via
     metrics or raw signals + --output csv|json + --output-file). См.
     BOARD.md → Doing → T022 + specs/T022-bridge-sweep/spec.md. -->

<!-- T145 переехал в BOARD.md → Done 2026-05-30 одной сессией
     (compact ~75 LOC + 10 tests, без spec'и). Реализован как opt-in
     flag `--with-op-fallback` (не auto-retry на exception, а явный
     opt-in для tube circuits, deterministic). См. BOARD.md → Done. -->

<!-- T146 переехал в BOARD.md → Done 2026-05-27 одной сессией
     (compact, ~190 LOC + 17 tests + CLI без spec'и). См. BOARD.md
     → Done. -->

- **T158** — [2026-05-27, заведено proactive по итогам T146 validator
  на real `data/models/transformers/generic/OPT_PP_6K6_8.lib`]
  **Fix OPT_PP_6K6_8.lib floating nodes (PC1, PC2, S3).** Push-pull
  OPT subckt имеет тот же класс bug что pre-T147 SE-OPT —
  3 floating internal nodes:
  ```
  PC1: occurs 1 time (expected ≥ 2)
  PC2: occurs 1 time (expected ≥ 2)
  S3:  occurs 1 time (expected ≥ 2)
  ```
  Использование этой фикстуры в реальных проектах → singular matrix
  при `.op` (тот же sympom что T147 на se-amp-demo).
  Acceptance:
  - Аналогичный T147 паттерн: ввести internal nodes для
    последовательного включения DCR-резисторов с обмотками primary
    half-coils (PC1/PC2 — center-tap leads) и secondary (S3 — third
    secondary winding или ошибочная нода).
  - `efactory lib validate OPT_PP_6K6_8.lib` → `result: OK`.
  - Опционально: regenerate template'ы если этот OPT используется
    в каких-то template'ах.
  - Smoke на минимальном PP testbench с `.op` → convergence.
  Hot-fix, без spec'и (≤ 2 ч). Триггер — first PP project в
  efactory.

<!-- T155 переехал в BOARD.md → Done 2026-05-27 одной сессией (3 LOC
     Dockerfile + 2 regression tests, без spec'и). curl --http1.1 +
     --retry 3 для FreeCAD AppImage (HTTP/2 BuildKit flakiness). -->

<!-- T147 переехал в BOARD.md → Doing 2026-05-26. По дороге выяснилось,
     что гипотеза «опечатка P3 вместо P, 1 строка» не работает: оба DCR
     (Rp_dcr, Rs_dcr) подключены к floating узлам (P3, S3); корректный
     фикс — ввести internal nodes (Pint/Sint) для последовательного
     включения DCR с обмоткой (4 правки в .lib, +regenerate-templates). -->

<!-- T149 переехал в BOARD.md → Done 2026-05-27 одной сессией
     (compact, без spec'и; project CLAUDE.md разрешает skip ритуала
     для small fix). См. BOARD.md → Done. -->

- **T148** — [2026-05-26, заведено по итогам прогона 5 сценариев T016]
  **Inplace-проект: `efactory bridge edit/sweep/sim-run` без
  `project create`.** Сейчас все bridge-команды требуют PROJECT-имя,
  и `project create` создаёт `/workspace/<NAME>/` под именем проекта,
  игнорируя cwd. Для quick exploration overkill — хочется работать с
  существующим `.kicad_sch` по cwd без регистрации в DB.
  Acceptance:
  - `efactory bridge sim-run --schematic <path>` без позиционного
    PROJECT — стартует через временный/inplace проект на основе cwd.
  - Auto-инференс PROJECT-имени из cwd basename, если позиционный
    аргумент опущен.
  - DB-регистрация — опциональная (lazy, при первом decision /
    artefact, который должен куда-то persist'иться).

- **T150** — [2026-05-26, вынесено из T014] **`/export-production` +
  use case + CLI: production-package для проекта.** Полный пакет
  документации per CONCEPT §7.1.
  Состав минимально-достаточного пакета (Phase A):
  - **BOM** (Bill of Materials) — CSV + markdown: designator,
    тип, value, qty, manufacturer-пометки если есть.
  - **PDF schematic** — `kicad-cli sch export pdf` для каждого
    `.kicad_sch` проекта.
  - **Sim results summary** — последняя запись из
    `.efactory/sim-results/` каждого `analysis_type`, краткая
    таблица метрик.
  - **`README-production.md`** — sanity-context (имя проекта,
    revision, дата сборки, список артефактов).
  - **ZIP-упаковка** — `<PROJECT>-<TIMESTAMP>.zip` в
    `<PROJECT>/exports/`.
  Опционально (Phase B): Gerber/drill для PCB-проектов
  (`kicad-cli pcb export gerbers/drill`), assembly drawing, BOM
  для JLCPCB-формата.
  Acceptance:
  - `efactory export production <PROJECT>` создаёт `<PROJECT>/
    exports/<PROJECT>-<TIMESTAMP>.zip` с BOM + PDF + summary +
    README.
  - `/export-production` в Claude Code TUI — тонкий wrapper.
  - Тест: пилотный прогон на `se-amp-demo`, ZIP открывается,
    содержит ≥ 4 файла.
  Не блокирует Phase 1b завершение (T014 без `/export-production`
  закрывает Phase 1b полностью).

<!-- T151 переехал в BOARD.md → Done 2026-05-27 одной сессией
     (compact ~70 lines YAML + 8 tests, без spec'и). См. BOARD.md →
     Done. -->

<!-- T152 не заведён: при имплементации T014 обнаружил, что
     pyproject.toml уже содержит `[tool.hatch.build.targets.wheel.
     force-include] "data/models" = "data/models"` — общего gap нет,
     Analyze A3 был ошибкой. T014 добавляет рядом
     `"data/templates" = "data/templates"`. -->


### Фаза 1a — MVP-ядро (3–4 недели)

<!-- T004b + T005 перенесены в BOARD.md → Done (2026-05-19, common PR). -->

<!-- T004b/T005 Phase 1 перенесены в BOARD.md → Done (2026-05-19). -->
<!-- T101 перенесена в BOARD.md → Done (2026-05-19). -->
<!-- T102 перенесена в BOARD.md → Doing (2026-05-18). -->

<!-- T103 перенесена в BOARD.md → Done (2026-05-19). -->

<!-- T105 Phase 0 перенесена в BOARD.md → Done (2026-05-19). -->

<!-- T105 Phase 1 (a)+(c) перенесены в BOARD.md → Done (2026-05-19):
     ECC83 self-contained (без extends), multi-unit dual-triode
     instancing (Valve:ECC81B / ECC83B / ECC88B registry entries). -->

<!-- T107 Phase 0 закрыт 2026-05-19 (BOARD.md → Done), Phase 1
     deferred перенесён в Фазу 3 перед T106 (Vladimir 2026-05-19) —
     связан с T032 SVG-render + T106 LLM-vision beautifier. -->

<!-- T106 (scheme layout beautifier) перенесён в Фазу 3 после T032
     (Vladimir 2026-05-19) — связан с SVG render + LLM-vision. -->


### Phase 0.9 — Containerization (новая фаза, 2026-05-19)

<!-- Введена решением 2026-05-19 (DECISIONS.md «Distribution:
     Linux Docker image с полным стеком»). Ставится между Phase
     1a и Phase 1b: до того, как развивать chat-client / runtime-
     агента, упаковать весь инструментарий в один воспроизводимый
     образ. После завершения Phase 0.9 все дальнейшие фазы
     исполняются внутри контейнера. Linux-only; Mac/Windows —
     Phase Cross-platform (см. конец файла). -->

<!-- T110 (Phase 0 базовый Dockerfile) перенесён в BOARD.md → Doing
     2026-05-19. Spec — `specs/T110-containerization/spec.md`
     (Analyzed, Phase 0). -->
<!-- T111 перенесена в BOARD.md → Done (2026-05-19, PR #53). Маркер
     пропущен в PR #53, восстановлен по дороге в PR T113. -->
<!-- T112 перенесена в BOARD.md → Doing (2026-05-20). Acceptance
     уточнено: FreeCAD 1.0+ через AppImage (variant C), Sheet Metal
     через git clone в Mod/, freecad-mcp вынесен в T124. См. ADR
     2026-05-20 в DECISIONS.md и Phase 2 implementation note. -->
<!-- T066 absorbed by T112: bootstrap FreeCAD больше не нужен —
     поставка через AppImage внутри efactory:linux. -->
<!-- T113 перенесена в BOARD.md → Doing (2026-05-20). Pilot scope
     сужен до одной фикстуры (OPT 6П14П SE, Vladimir clarify-3); 50Hz
     и flyback вынесены в BACKLOG как cross-validation follow-up'ы.
     Pilot+integration в одном PR с phase-коммитами (clarify-1). Spec —
     specs/T113-fem-solver/spec.md. -->
<!-- T058 absorbed by T113: FEMM bootstrap не нужен — Linux-native
     FEM-solver внутри efactory:linux. -->
<!-- T114 перенесена в BOARD.md → Doing (2026-05-20) — объединена
     с T121 в один PR (variant C). См. BOARD.md → T114 + T121. -->
<!-- T120 перенесена в Tech Debt (parked 2026-05-21) — dead code, не
     блокирует ничего, при взятии расширить scope. -->
<!-- T121 перенесена в BOARD.md → Doing (2026-05-20) — объединена
     с T114 в один PR (variant C). См. BOARD.md → T114 + T121. -->

<!-- T122/T123 закрыты 2026-05-21 как outdated, перенесены в
     CHANGELOG.md → ## Closed without implementation. -->
<!-- T128 split на T129/T130 в investigation phase 2026-05-20;
     T130 затем absorbed by T129. Оба перенесены в CHANGELOG.md
     → ## Closed without implementation. -->

<!-- T129 переехала в BOARD.md → Doing 2026-05-20 после Clarify+Analyze.
     Спека: specs/T129-nonlinear-fem-dc-bias/spec.md. -->

<!-- T131 переехала в BOARD.md → Doing 2026-05-21 после Vladimir выбрал
     "T131 SPICE saturable + THD" следующей content-задачей. Spec —
     specs/T131-saturable-thd/spec.md (Draft, в Clarify-фазе). -->

<!-- T132 переведена в BOARD.md → Doing 2026-05-21 после T131 closure.
     Spec — specs/T132-interleaved-leakage/spec.md (Draft, в Clarify-
     фазе). -->

<!-- T133 переведена в BOARD.md → Doing 2026-05-21 после T132 closure.
     Spec — specs/T133-elmer-fem-pivot/spec.md (Clarified, готова к
     Analyze). Топология — single-coil + Kelvin shell; acceptance
     ±25% (target ±10%) к PyOM ZHANG; phasing Phase 0 pilot →
     Phase 1 adapter linear → Phase 2 nonlinear → Phase 3 closing. -->

<!-- T127 закрыта 2026-05-21 как outdated by T133, перенесена в
     CHANGELOG.md → ## Closed without implementation. -->
<!-- T124 перенесена в Tech Debt (parked 2026-05-21) — FreeCAD
     драйвится Bash + `.FCMacro` без отдельного MCP-уровня;
     возвращать после T108 ADR и появления stateful use case. -->

### Phase 1b — Claude Code integration (+~1 неделя efactory-specific glue, исполняется внутри контейнера после Phase 0.9)

<!-- T011 перенесён в Tech Debt 2026-05-19: решено использовать
     Claude Code как frontend (ADR 2026-05-19 «Distribution: Linux
     Docker image»). T108 OpenCode pilot — due-diligence, в Tech
     Debt; не блокирует.

     Phase 1b reformulated 2026-05-22 (см. CHANGELOG ## Closed
     without implementation): T012/T015 closed (custom backend +
     token-budget compaction → Claude Code built-in); T017/T018/T019
     закрыты (multi-backend инфраструктура не нужна); T020
     переформулирован в research MCP-tool, перенесён в Фазу 8.
     Оставшиеся T013/T014/T016 — узкий scope efactory-specific glue
     поверх Claude Code (регистрация MCP-серверов, slash-команды,
     project context). Frontend живёт внутри Docker-образа
     (см. Phase 0.9). -->

<!-- T013 переехала в BOARD.md → Doing 2026-05-24 после второй
     переформулировки. Старая формулировка «Регистрация efactory
     MCP-серверов» закрыта (MCP не используем — ADR 2026-05-24 в
     DECISIONS.md «Tool surface = Bash + efactory CLI + filesystem,
     не MCP»); новая — «Claude Code runtime в контейнере: install +
     auth + entrypoint». Spec — specs/T013-claude-code-runtime/spec.md
     (Analyzed). -->

<!-- T014 переехала в BOARD.md → Doing 2026-05-26 после clarify+analyze
     прохода. Реальный синтаксис slash-команд — hyphenated flat
     (`/project-create`, `/project-use`, `/sim-run`); `/project-use`
     — display-only (Bash cwd persistence нестабильна между tool
     calls); `/export-production` вынесен в T150. Spec —
     specs/T014-claude-code-slash/spec.md (Analyzed). -->
<!-- T016 переехала в BOARD.md → Doing 2026-05-25 после clarify-прохода.
     Механизм выбран — SessionStart hook + cwd-based project detection
     (vs `/project use NAME` остаётся за T014). Spec —
     specs/T016-project-context/spec.md (Analyzed). -->


### Фаза 2 (+2 недели)

<!-- T017/T018/T019 закрыты 2026-05-22 как outdated by ADR 2026-05-19
     (multi-backend инфраструктура не нужна — Claude Code as frontend);
     перенесены в CHANGELOG → ## Closed without implementation. -->
<!-- T020 переформулирован 2026-05-22 как research MCP-tool, перенесён
     в Фазу 8 (nice-to-have, не Phase 2). -->

<!-- T021 переехала в BOARD.md → Doing 2026-05-30. Spec —
     specs/T021-edit-and-resim-delta/spec.md (Draft → готова к Clarify). -->

<!-- T022 переехала в BOARD.md → Doing 2026-05-27. Top-level scope
     подтверждён в чате (B → c orthogonal `--analysis` + `--metric`;
     A/C/D/E/F/G/H/I — по рекомендации). T144 absorbed. Spec —
     specs/T022-bridge-sweep/spec.md (Draft, готов к Clarify). -->
<!-- T144 absorbed by T022 (2026-05-27): sweep tabular output + CSV
     gap входит в Phase A scope T022. См. запись T022 в BOARD.md. -->
<!-- T023 переехала в BOARD.md → Doing 2026-05-26 после clarify
     прохода (10 вопросов, все «по рекомендации»). Phase margin
     вынесен в T153 (Q-B → c) — отдельный спек, когда появится
     feedback-фикстура. Spec — specs/T023-measurements/spec.md
     (Clarified, готова к Analyze). -->
<!-- T024 переехала в BOARD.md → Doing 2026-05-26 (analysis-first
     ordering Фазы 2, шаг 2 после T023). Реализован напрямую без
     spec'и: ≤1 день, plotext + 2 CLI sub-команды + 2 slash-команды. -->

<!-- T025 переехала в BOARD.md → Doing 2026-06-02 после Round 1
     clarify (6 ответов). Исходный acceptance (Sixel/Kitty + xdg-open
     + Windows `start`) переформулирован в свете Phase 0.9
     containerization: UX = Claude Code chat inline по absolute path к
     PNG; Sixel/xdg-open/Windows откладываются в follow-up / Phase 8.
     Spec — specs/T025-schematic-visualization/spec.md (Draft, Round 2
     открыт). -->

<!-- T026 переехала в BOARD.md → Doing 2026-06-03 после Round 1
     clarify (10 ответов) + Analyze pass (1 Critical, 5 Warnings, 7
     Notes; W1 force-split semantic — resolved (c) разделение
     --force/--accept-overwrite). Acceptance переформулирован:
     убран «apply через IPC reload» (нет Schematic API в kicad-python
     0.7.1, горизонт KiCad 11/12), заменён на staged-файл + явный
     apply command. Spec — specs/T026-staged-modifications/spec.md
     (Analyzed). -->

<!-- T027 переехала в BOARD.md → Doing 2026-06-02. Scope расширен
     по запросу Vladimir: 4 новых шаблона (PP amp, line preamp,
     phono RIAA preamp, active LPF) — SE amp уже закрыт ранее в
     рамках первой фазы template-системы. Spec —
     specs/T027-project-templates/spec.md (Draft, Round 2 clarify
     готов к ответам). -->
<!-- T153 переехала в BOARD.md → Doing 2026-05-31. Phase A scope
     включает создание первой feedback-фикстуры (триггер закрывается
     внутри задачи). Spec — specs/T153-phase-margin/spec.md (Draft,
     готов к Clarify). -->


### Фаза 3 (+2 недели)

- **T029** — [2026-05-15, reformulated 2026-06-03] ERC quality gate
  через `kicad-cli sch erc` в `/sim-run` / новой `/design-check`.
  `kicad-mcp-pro` отвергнут (ADR 2026-05-19: no MCP, CLI + filesystem).
  DRC отложен в Фазу 4 (PCB) — до неё DRC-чекать нечего. Частично
  уже подготовлено: `facade.py` ставит PWR_FLAG и NoConnect маркеры
  для прохождения ERC.
  Acceptance: pipeline блокирует sim-run, если ERC возвращает
  errors (warnings — допустимы, рендерятся в человеко-читаемый отчёт);
  есть slash `/design-check <project>` для standalone-запуска.
- **T030** — [2026-05-15, reformulated 2026-06-03] Импорт SPICE-моделей
  по URL: slash `/spice-import-url <url>` (primary) и/или CLI
  `efactory spice import-url <url>`. Pipeline: download → классификация
  (BJT/MOSFET/op-amp/tube/diode/...) → `convert_pwrs_to_ngspice` (T168)
  → раскладка по `spice-models/<class>/` → метаданные в KB topic
  `spice.<vendor>.<part>` (T134 namespace).
  Acceptance: URL TI/Vishay/ON Semi → модель добавлена в библиотеку
  и проходит smoke-симуляцию; KB-entry создан и находится через
  `/kb-search`.
<!-- T031 (Tube-curve-fitting) — taken into BOARD → Doing 2026-06-03,
     spec в specs/T031-tube-curve-fitting/spec.md. -->

<!-- T032 (Рендер схемы в SVG + LLM-vision проверка) — removed
     2026-06-03 as fully superseded:
     - Render-часть (SVG/PNG через `kicad-cli sch export svg` +
       `rsvg-convert`) реализована в T025 (`adapters/outbound/
       kicad_cli/schematic_renderer.py`); auto-show после `/sim-run`
       и `/project-create` работает.
     - LLM-vision как отдельный pipeline потерял смысл — Claude Code
       как frontend (ADR 2026-05-19) видит картинку в чате напрямую,
       ad-hoc visual review работает out-of-box.
     - Узкая ниша `/schematic-review` (regression baseline + structured
       отчёт) имеет смысл только под CI visual-regression, которой нет
       и в обозримых планах не предвидится. Если потребуется — заведём
       новой задачей под конкретный triggering use case.
     - Снятие блокировки: T106 Phase 3 и T107 Phase 1 больше не
       зависят от T032 (см. их обновлённые формулировки). -->

- **T107 Phase 1 (deferred)** — datasheet-accurate symbol drawing для
  советских ламп. Phase 0 (закрыт 2026-05-19, PR #46) реализован
  через copy-rename базовых EL84/ECC81 форм (visually одинаковы,
  отличается lib_id и Value). Phase 1 — нарисовать оригинальные
  shapes: GU50 (octal base с top-cap anode), 6П45С (specific beam
  tetrode shape), 6Н6П (octal dual triode layout). Drawing-heavy
  vector polyline work. **Снятие блокировки 2026-06-03:** SVG-render
  больше не блокер (T032 superseded by T025) — фоновый workflow
  «datasheet image через чат → vector polylines через Claude vision»
  можно начинать в любой момент.
- **T106** — [2026-05-19] **Scheme layout beautifier.** Post-process
  валидного `.kicad_sch` (после ERC) для «textbook look»: убрать
  collisions подписей/компонентов/проводников, выровнять reference/
  value текст, сделать layout читаемым.

  **Edge:** Altium / KiCad auto-place были разработаны до multimodal
  LLM эры — их алгоритмы чисто deterministic-rule-based. У нас есть
  **iterative LLM-vision refinement** (SVG/PNG-render через T025 →
  Claude vision в чате → diff), которого pre-LLM tools физически не
  имели. Это потенциально даёт нам качество выше commercial EDA для
  нишевых схем (audio amps в нашем случае).

  **Phase 0 (rule-based, ~1 сессия):** детект label/value/reference
  text-on-component-body или text-on-wire overlap'ов через bbox
  intersection. Если есть — nudge text на свободную сторону компонента
  (4-direction polling). Acceptance: на наших фикстурах (RC, rectifier,
  CE, SE-amp, triode_amp) — ноль текстовых overlap'ов.

  **Phase 1 (rule-based, ~2 сессии):** wire-through-body detection
  (wire visually passes через symbol bbox без electrical pin contact)
  → reroute через «channel corridors» (горизонтальные/вертикальные
  free-from-bodies lanes между рядами компонентов). По T100 §Analyze
  W2 — это ≤50 LOC при правильной геометрии. Acceptance: SE-amp
  wires не идут визуально через тело лампы или OPT.

  **Phase 2 (rule-based, ~3 сессии):** component placement
  optimization — детект unaligned components (off-grid pin positions,
  asymmetric Y-spread), apply nudges и rotations для balanced layout
  (schematic-style symmetry: power вверху, GND внизу, signal flow
  слева-направо). Acceptance: auto-built ≈ mentor-style reference
  fixture.

  **Phase 3 (LLM-vision driven, наш main edge):** slash
  `/schematic-beautify <project>` рендерит схему через T025, отдаёт
  PNG в Claude в чате с промптом «оптимизируй визуал как audio
  textbook»; vision-ответ парсится в список patches (nudge label /
  rotate component / reroute wire), фасад применяет diff к
  `.kicad_sch`, итеративно до convergence. Reformulated 2026-06-03:
  без отдельного MCP/vision-pipeline в коде — переиспользуем
  существующий чат (ADR 2026-05-19 «Claude Code as frontend»).
  Acceptance: blind test — Phase 0+1+2 (rule-based only) output vs
  Phase 0+1+2+3 (rule-based + LLM-vision) output, выбираем «красивее»;
  Phase 3 выигрывает на ≥80% test cases.

  **Зависимости 2026-06-03:** SVG-render — T025 (готов).
  T032 (как блокер) снят. Не блокирует production-workflow — chat
  работает с функционально верными схемами независимо от визуала.
<!-- T033 (`/cost` команда) — removed 2026-06-03 as obsolete after
     ADR 2026-05-19 «Claude Code as frontend»: Claude Code сам даёт
     `/cost`, `/usage-credits` плюс `ccusage`. Своего TUI нет —
     некуда встраивать. -->
<!-- T034 (Rich TUI autocomplete) — removed 2026-06-03 as obsolete
     after ADR 2026-05-19 «Claude Code as frontend»: Rich TUI
     отказались. Slash-command autocomplete уже в Claude Code.
     Component-name completion (имена из текущей схемы) — задача
     prompts/KB, не нашего TUI. -->

- **T035** — [2026-05-15, reformulated 2026-06-03] Публикационный
  workflow как slash-команды: `/export-schematic-publication
  <project>` (схема → SVG/PDF для статьи, использует T025 render)
  и `/export-sim-report <project>` (результаты симуляции →
  Markdown-отчёт с графиками, использует существующие
  `cli/*_renderer.py` + `/plot-*` адаптеры).
  Acceptance: для тестового проекта обе команды генерируют
  публикационно-готовые артефакты в `out/publications/<ts>/`;
  README с описанием включения в статью.
- **T036** — [2026-05-15, re-evaluate 2026-05-19 после Phase 0.9]
  Стратегия обновлений: флаги `--update`, `--update-models`,
  `--doctor` в bootstrap + CLI.
  **Re-evaluate:** после Phase 0.9 Containerization большая часть
  заменяется на `docker pull efactory:linux-latest`. Что
  остаётся актуальным — `--doctor` внутри образа (диагностика
  тулчейна, проверка GPU/X11 passthrough) и `--update-models`
  для пользовательских SPICE-моделей вне образа. Acceptance
  переоценить при взятии в работу.

### Фаза 4 — PCB-модуль (+3–4 недели)

- **T037** — [2026-05-15] `pcb_from_schematic`: создание `.kicad_pcb`
  из `.kicad_sch` (импорт нетлиста, контур платы, правила
  проектирования).
  Acceptance: схема → пустая плата с импортированным нетлистом и
  установленными правилами.
- **T038** — [2026-05-15] `pcb_place_components`: программное
  размещение через pcbnew API по стратегиям (`tube_amp`, `digital`,
  `smps`, `audio_analog`).
  Acceptance: компоненты разнесены по функциональным группам и
  тепловым зонам, soft-constraints выполнены.
- **T039** — [2026-05-15] `pcb_autoroute`: запуск FreeRouting CLI
  (DSN → SES → импорт), статистика completion rate.
  Acceptance: некритические цепи разведены автоматически, силовые
  и ВЧ исключаются.
- **T040** — [2026-05-15] `pcb_manual_route`: ручная трассировка
  критических цепей (силовые, ВЧ, дифф. пары) через pcbnew API.
  Acceptance: указанные сети разводятся по заданным маршрутам и
  ширинам.
- **T041** — [2026-05-15] `pcb_validate`: DRC + DFM + визуальная
  инспекция через рендер всех слоёв в SVG.
  Acceptance: возвращает структурированный отчёт по нарушениям
  и DFM-предупреждениям.
- **T042** — [2026-05-15] `pcb_export_manufacturing`: Gerber + drill
  + BOM + pick-and-place + STEP. Профили: `jlcpcb`, `generic`.
  Acceptance: для тестового проекта файлы валидны (Gerber viewer
  + JLCPCB upload OK).
- **T043** — [2026-05-15] `pcb_render`: SVG-рендер слоёв (top,
  bottom, all) для визуального контроля в чате.
  Acceptance: PNG/SVG показывается в чате (Sixel/Kitty) или
  открывается внешне.
- **T044** — [2026-05-15] `pcb_jlcpcb_check`: поиск компонентов в
  каталоге LCSC, оценка стоимости платы и монтажа.
  Acceptance: BOM → артикулы LCSC + смета (плата + компоненты +
  монтаж).
- **T045** — [2026-05-15] P2P bridge (навесной монтаж): инструменты
  `p2p_layout`, `p2p_wiring_table`, `p2p_wiring_diagram`,
  `p2p_assembly_order`.
  Acceptance: `--assembly p2p` при создании проекта → инструменты
  доступны; для тестового SE-amp генерируются раскладка + таблица
  + порядок монтажа.
- **T046** — [2026-05-15] Многоплатные проекты: поддержка нескольких
  `.kicad_sch`/`.kicad_pcb` в одном проекте, межплатные соединения,
  спецификация кабелей и жгутов.
  Acceptance: проект с 2+ платами собирается в общую 3D-сборку,
  общий BOM, таблица разъёмов.
- **T047** — [2026-05-15] `pcb_emi_check`: автоматический аудит
  помехозащиты (заземление, экранировка, полигоны, развязка
  питания, накальные цепи).
  Acceptance: возвращает список нарушений с приоритетами и
  рекомендациями.
- **T048** — [2026-05-15] `safety_checklist`: автоматический чеклист
  электробезопасности (разрядные R, предохранители, заземление,
  зазоры ВН).
  Acceptance: схема → Markdown/PDF-чеклист + карта зазоров.
- **T049** — [2026-05-15] `psu_wizard`: wizard блоков питания
  (линейные топологии: CLC, CLCRC, стабилизаторы; SMPS: Buck, Boost,
  Buck-Boost, Flyback, Forward, Half-Bridge).
  Acceptance: ТЗ → схема БП + рассчитанные номиналы + моделирование
  пульсаций.

### Фаза 5 — Намоточные изделия (+3 недели)

- **T051** — [2026-05-15] `mag_select_core`: подбор сердечника по
  ТЗ (мощность, частота, габариты, материал) из базы OpenMagnetics
  (10 000+ сердечников).
  Acceptance: ТЗ → список топ-N сердечников с обоснованием выбора;
  поддержаны кремнистая сталь (аудио) и ферриты (ИИП).
- **T052** — [2026-05-15] `mag_design_transformer`: полный расчёт
  трансформатора — число витков, сечение провода (с AC-эффектами:
  скин, proximity), конфигурация слоёв и секционирование, изоляция,
  заполнение окна.
  Acceptance: для тестовых ТЗ (SE-OPT 6П14П, силовой 50 Гц,
  flyback SMPS) выводится полная спецификация обмоток, проходит
  проверка заполнения окна.
- **T053** — [2026-05-15] `mag_design_choke`: расчёт дросселя —
  индуктивность, ток подмагничивания, зазор; для SMPS — ripple
  current и core loss; синфазные дроссели для EMI-фильтров.
  Acceptance: ТЗ дросселя → конструктивный расчёт + проверка
  отсутствия насыщения.
- **T054** — [2026-05-15] `mag_calc_parasitics`: расчёт паразитов
  (Llk, Cw, Rp, Rs, Rc) → генерация SPICE-модели `.subckt`,
  совместимой со SPICEBridge.
  Acceptance: расчётный `.subckt` загружается в pipeline моделирования,
  АЧХ трансформатора совпадает с расчётной в пределах допуска.
- **T055** — [2026-05-15, renamed/refactored 2026-05-19]
  `mag_verify_field` (solver-agnostic, бывш. `mag_verify_femm`):
  верификация магнитного поля через Linux-native FEM-solver
  (Elmer FEM primary, GetDP fallback — выбор по T113).
  Экспорт solver input, запуск, парсинг. ADR — `DECISIONS.md`
  2026-05-19 «Magnetic field verification: Linux-native
  FEM-solver». Acceptance: распределение поля и значения
  индуктивности возвращаются в чат; рассогласование с
  PyOpenMagnetics-расчётом подсвечивается; solver-agnostic
  port в `adapters/outbound/fem_solver/` позволяет подменить
  backend без слома domain.
- **T056** — [2026-05-15] `mag_build_3d`: 3D-модель магнитного
  компонента через MVB → FreeCAD (сердечник + каркас + обмотки) +
  экспорт STEP.
  Acceptance: STEP-файл импортируется в сборку корпуса (Фаза 6)
  без коллизий.
- **T057** — [2026-05-15] `mag_export_winding_spec`: спецификация
  для намотчика (PDF/Markdown) — сердечник, каркас, таблица обмоток,
  порядок намотки, изоляция, пропитка, параметры приёмки.
  Acceptance: спецификация валидируется на тестовом OPT — все поля
  заполнены, диаграмма послойной намотки читается.

### Фаза 6 — Проектирование корпуса (+3–4 недели)

- **T059** — [2026-05-15] Подключение `freecad-mcp` как 5-го
  MCP-сервера в `kicad-sim-chat` (профиль конфигурации + проверка
  доступности FreeCAD).
  Acceptance: после `bootstrap` инструменты `freecad-mcp` доступны
  в чате по полному имени.
- **T060** — [2026-05-15] `enclosure_from_pcb`: импорт STEP платы
  (из `kicad-cli pcb export step`) в FreeCAD, создание базовой
  формы шасси по габаритам платы с отступами.
  Acceptance: для тестовой платы 200×150 мм генерируется корпус
  с правильными отступами и крепёжными отверстиями, совмещёнными
  с платой.
- **T061** — [2026-05-15] `enclosure_add_cutout`: добавление вырезов
  — круглый (под панельку/потенциометр), прямоугольный (под разъём),
  произвольный по контуру.
  Acceptance: для тестового корпуса добавляются вырезы под октальную
  панельку, IEC-ввод, потенциометр; интерференций нет.
- **T062** — [2026-05-15] `enclosure_sheet_metal`: применение
  workbench Sheet Metal — сгибы, фланцы, стойки для крепления
  платы; генерация развёрток.
  Acceptance: для тестового шасси выводится корректная развёртка
  с указанием линий сгиба.
- **T063** — [2026-05-15] `enclosure_assembly`: сборка
  плата + корпус + крепёж + трансформаторы (Assembly workbench),
  проверка зазоров и интерференций.
  Acceptance: для тестовой системы (плата + корпус + 2 трансформатора)
  сборка собирается без интерференций; отчёт о зазорах генерируется.
- **T064** — [2026-05-15] `enclosure_export`: DXF развёртки панелей,
  STEP сборки, STL для 3D-печати прототипа, PDF чертежей TechDraw.
  Acceptance: все четыре формата валидны (DXF открывается лазерным
  раскроем, STL — слайсером, STEP — KiCad/FreeCAD).
- **T065** — [2026-05-15] `enclosure_render`: 3D-рендер сборки для
  визуального контроля (PNG/SVG в чат через freecad-mcp).
  Acceptance: рендер показывается в терминале (Sixel/Kitty) или
  открывается внешне.

### Фаза 7 — Производственная документация (+2 недели)

- **T067** — [2026-05-15] Команда `/export-production <project>
  [--format jlcpcb|generic] [--lang ru|en]`: сборка полного пакета
  документации (schematic / simulation / pcb или p2p / magnetics /
  enclosure / cables / sourcing / safety / specifications) одним
  вызовом.
  Acceptance: для тестового проекта генерируется полный
  `production-package/` по §7.1 концепта.
- **T068** — [2026-05-15] Sourcing: интеграция Mouser API — поиск
  по part number, цены, наличие, артикулы.
  Acceptance: BOM → `sourcing_mouser.csv` с актуальными ценами и
  доступностью.
- **T069** — [2026-05-15] Sourcing: интеграция DigiKey API —
  аналогично T068.
  Acceptance: BOM → `sourcing_digikey.csv` с актуальными ценами и
  доступностью.
- **T070** — [2026-05-15] Sourcing: интеграция LCSC (JLCPCB) через
  `kicad-mcp-pro` — поиск, артикулы, оценка стоимости монтажа.
  Acceptance: BOM → `sourcing_lcsc.csv` + оценка стоимости платы
  с монтажом.
- **T071** — [2026-05-15] Сводный BOM по всем платам / корпусу /
  намоточным / кабелям (`consolidated_bom.xlsx`).
  Acceptance: для многоплатного тестового проекта формируется
  единый BOM без дублирования.
- **T072** — [2026-05-15] Cost estimate: смета по поставщикам с
  разбивкой и общей стоимостью (`cost_estimate.md`).
  Acceptance: смета содержит детализацию по поставщикам, валютам,
  и итоговую сумму с учётом доставки (оценочно).
- **T073** — [2026-05-15] `bridge_import_measurement`: импорт
  измерений с приборов — CSV (осциллограф, анализатор), Touchstone
  (.s1p/.s2p — NanoVNA), Rigol/Siglent CSV, ручной ввод (мультиметр).
  Acceptance: каждый из четырёх форматов загружается без ошибок,
  данные нормализуются к внутреннему формату.
- **T074** — [2026-05-15] `bridge_compare_sim_vs_measured`:
  наложение измерений на результаты симуляции, отчёт о расхождениях
  (АЧХ, рабочие точки, паразиты трансформаторов).
  Acceptance: для тестового проекта генерируется
  `sim_vs_measured.pdf` с графиками и таблицей расхождений.
- **T075** — [2026-05-15] Шаблоны документов: `device_spec.md` (ТТХ),
  `test_protocol.md` (протокол испытаний с ожидаемыми значениями),
  `emi_report.md` (отчёт по помехозащите).
  Acceptance: для тестового проекта все три документа генерируются
  и наполняются актуальными значениями из результатов фаз 1–6.

### Фаза 8 — Будущее

- **T020** — [2026-05-15, reformulated 2026-05-22, moved Phase 2 → 8]
  **`/compare` MCP-tool для side-by-side model comparison.** После
  ADR 2026-05-19 (Claude Code as frontend) встроенной multi-backend
  infrastructure нет — `/compare` реализуется как research MCP-tool:
  принимает prompt + список моделей, опрашивает Anthropic API /
  openai-compat endpoints параллельно, возвращает агрегированный
  markdown с ответами рядом. Nice-to-have для архитектурных решений
  (eval нескольких LLM на одну efactory-задачу).
  Acceptance: MCP-tool `efactory.compare_models` принимает
  `models: list[str]` + `prompt: str`, возвращает структурированный
  response с ответами и метаданными (latency, токены, cost оценочно).
  Originally T020 в Фазе 2 (2026-05-15) — «своя slash-команда»;
  переформулировано как MCP-tool 2026-05-22.
- **T076** — [2026-05-15] Web-интерфейс для удалённого доступа к
  `kicad-sim-chat` (без замены TUI, дополнительный фронтенд).
  Acceptance: запуск web-server, базовый чат-UI работает поверх той
  же бэкенд-логики.
- **T077** — [2026-05-15] Streaming для API-бэкендов (Anthropic,
  OpenAI-compat) — токен-за-токеном вывод в TUI.
  Acceptance: ответ LLM рендерится с задержкой <100 мс на первый
  токен.
- **T078** — [2026-05-15] Параллельный запрос на несколько моделей
  (расширение `/compare`): одновременная отправка в N бэкендов,
  агрегированный вывод.
  Acceptance: 3 модели опрашиваются параллельно; время = max, а не
  sum.
- **T079** — [2026-05-15] Интеграция официального `kicad-python`
  (IPC API) для редактирования схем — когда появится поддержка
  `.kicad_sch` в upstream. Заместит часть функциональности
  `kicad-sch-api`.
  Acceptance: pipeline работает через kicad-python для базовых
  операций со схемой; ADR в `DECISIONS.md` фиксирует решение.
- **T080** — [2026-05-15] SSE-транспорт для MCP-серверов (доступ
  с телефона / удалённо).
  Acceptance: `kicad-sim-bridge` поднимается по SSE; мобильный
  MCP-клиент подключается и исполняет инструменты.
- **T081** — [2026-05-15] Панелизация: объединение нескольких плат
  в одну производственную панель с отбоиваемыми перемычками.
  Acceptance: на вход — несколько `.kicad_pcb`, на выход — единый
  Gerber-набор панели с tooling-вырезами.
- **T082** — [2026-05-15] Экспорт IPC-2581 (современная альтернатива
  Gerber).
  Acceptance: для тестового PCB выводится валидный IPC-2581 файл,
  проходит проверку viewer-ом.
- **T083** — [2026-05-15] Интеграция с другими производителями PCB:
  PCBWay, OSHPARK, Elecrow — профили экспорта в `pcb_export_manufacturing`.
  Acceptance: для каждого производителя — рабочий профиль,
  загружаемый файл-пакет, оценка стоимости.
- **T084** — [2026-05-15] RF-модуль: S-параметры, Smith chart,
  модели линий передачи, интеграция NanoVNA для измерений.
  Acceptance: для RF-проекта (тестовый антенный согласователь)
  снимаются S-параметры, рендерится Smith chart, сравнение с
  симуляцией.

### Phase Cross-platform — Mac/Windows поддержка (после стабилизации Linux Docker workflow)

<!-- Введена решением 2026-05-19 (DECISIONS.md «Distribution:
     Linux Docker image»). Отдельная фаза с собственным
     acceptance, чтобы не блокировать Linux-only итерацию.
     Берётся в работу после того, как Phase 0.9 + 1a + 1b
     стабильно работают на Linux. -->

- **T116** — [2026-05-19] Docker Desktop на Windows: запуск
  efactory через WSL2 / WSLg для GUI passthrough. Документация
  по установке и known-issues. Acceptance: на чистой Windows 11
  + Docker Desktop + WSLg `./efactory-up.ps1` (или эквивалент)
  запускает KiCad GUI из контейнера; задача создания SE-amp
  проходит end-to-end.
- **T117** — [2026-05-19] Docker Desktop на macOS: запуск
  efactory через Docker Desktop + XQuartz (Intel) или
  Docker Desktop + native macOS XQuartz (Apple Silicon).
  Multi-arch image (linux/amd64 + linux/arm64) для Apple
  Silicon — проверить, что весь стек собирается на arm64
  (KiCad да; FreeCAD да; FEM-solver — проверить Elmer/GetDP
  на arm64). Acceptance: на чистой macOS 14+ задача SE-amp
  проходит end-to-end.
- **T118** — [2026-05-19] **Опционально:** native FEMM fallback
  для пользователей, которым нужна совместимость с
  существующими FEMM-моделями индустрии. Реализуется только
  если возникнет реальный запрос. ADR — `DECISIONS.md`
  2026-05-19 «Magnetic field verification».
  Acceptance: opt-in путь через флаг конфигурации,
  переключающий FEM-backend с Elmer/GetDP на FEMM (native
  на хосте, не в контейнере).
- **T119** — [2026-05-19] Native fallback distribution для
  пользователей без Docker (corporate restrictions и т.п.):
  возрождение T002/T003 как opt-in пути. Acceptance —
  переоценить при реальном запросе.
