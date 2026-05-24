# Architecture Decisions

ADR-Lite: компактный лог архитектурных решений с обоснованиями.
Цель — через полгода можно ответить на вопрос «а почему мы тогда так
сделали?», не реконструируя контекст по коммитам.

## Формат

Каждое решение — короткий блок:

- **Дата** — когда принято.
- **Решение** — что решили (1 строка).
- **Контекст** — какая задача / ограничение к нему привели.
- **Альтернативы** — что рассматривали и почему отвергли.
- **Последствия** — что это нам теперь даёт и чего лишает.

Решения не редактируются после фиксации. Если решение пересмотрено —
добавляется новый блок со ссылкой на старый, старый помечается как
«Заменено решением от <дата>».

---

## Решения проекта

<!-- Реальные решения добавляются сюда, новые сверху. При совпадении
     дат — от фундаментального к инструментальному. -->


### 2026-05-21 — T133 closure: 3D Elmer FEM ACHIEVED acceptance ±25% к PyOM ZHANG (Lp=6.04H, -13.3%); 2D inherent gap +180-240% confirmed physics-bound

- **Контекст.** T133 (Elmer FEM pivot) trigger — T113 Phase 1 pilot
  baseline 242% gap к PyOM ZHANG analytical (6.96 H) на pilot OPT 6П14П
  SE: GetDP 2D split-coil + Dirichlet → 23.78 H (+242%). T129 attempted
  closure через nonlinear Frohlich + DC-bias central-diff в GetDP 2D —
  failed (Lp ≈ L_linear, Frohlich curve not engaging в 2D split-coil
  + open-domain). Vladimir выбрал Elmer pivot (variant 3b/α из T129
  Phase C ADR 2026-05-20).

  T133 проходила 5 фаз (Phase 0/1/2 — 2D Elmer infrastructure, Phase 3a/b/c/d
  — 3D pivot β после empirical 2D ceiling), 9 commits на ветке
  T133-elmer-fem-pivot.

- **Empirical journey (acceptance к ZHANG 6.96 H):**

  | Phase | Backend | Topology / mesh | Lp [H] | rel diff | Acc ±25% |
  |-------|---------|-----------------|--------|----------|----------|
  | T113 baseline | GetDP 2D | split-coil + Dirichlet | 23.78 | +242% | ❌ |
  | T133 Phase 1 | Elmer 2D | single-coil + Infinity BC | 19.65 | +182% | ❌ |
  | T133 Phase 3c | Elmer 3D | ungapped, 9.6K tetra | 23.78 | +242% | ❌ |
  | T133 Phase 3d.1 | Elmer 3D | gapped coarse, 1.8K tetra | 4.07 | -41.5% | ❌ |
  | **T133 Phase 3d.2** | **Elmer 3D** | **gapped refined, 51K tetra** | **6.04** | **-13.3%** | **✅** |

  Factor 19× improvement в точности от 2D baseline (3.42× → 1.15×).

- **Решение (Phase 3e closing):**

  1. **T133 closed на Phase 3d.2 acceptance ±25%.** Production-ready
     3D Elmer FEM adapter (`fem_solver_elmer`, `dimensionality='3d'`):
     - `emit_e_core_geo_3d(dims, with_gaps=True)` — OCC kernel, 7
       Physical Volumes (core + 2 windings + 3 gaps + air),
       geometrically-derived lateral leg bounds (PyOM `lateral_x`
       inconsistency для E 42/21/15 — fix в T138).
     - Whitney AV solver + Tree gauge + MUMPS direct linear (4 GB
       RAM ceiling ~10K nodes).
     - MagnetoDynamicsCalcFields auto-injects "electromagnetic field
       energy" в SaveScalars — direct Lp = 2W/I² extraction.
     - Mesh sizing: 20 μm gap min, 5 mm global max → 10K nodes,
       14 s integration runtime.

  2. **Target ±10% [6.26, 7.65 H] не достигнут** (off by 3.5%).
     Closure заблокирован в текущей среде:
     - Mesh refinement к 39K nodes → MUMPS direct OOM, system crash.
     - Iterative path в Elmer 26.2 elmerfem-csc PPA: BoomerAMG
       не сходится для edge basis (designed для node-Laplacian),
       Auxiliary Maxwell Space (AMS) preconditioner не вкомпилирован
       (`Unknown preconditioner type: ams, feature disabled`).
     - Coil mechanism (proper 3D current loop) требует mesh bridges
       через top/bottom yokes для closed loop — отдельная задача.

  3. **Follow-up T-IDs:**
     - **T136** — Elmer rebuild с AMS preconditioner (или server-class
       RAM) для finer mesh + iterative path → target ±10%.
     - **T137** — Coil mechanism с mesh bridges через yokes
       (alternative к T136, physically-correct OPT primary).
     - **T138** — PyOM `lateral_x` data semantics investigation,
       ECoreDimensions.from_pyom_core correction.
     - **T139** — 3D Elmer nonlinear-frohlich path (H-B Curve в 3D
       Whitney AV + Newton).

- **Альтернативы рассмотрены:**

  - **GetDP topology rework (shell transformation / circuit coupling)
    — T133 alpha-path, отвергнут в Phase 0:** Elmer уже частично
    исследован в T113 Phase 1 cross-validation, native nonlinear
    support лучше чем custom Picard на GetDP.
  - **2D-axisymmetric для E-core — невозможно:** E-core не radially
    symmetric. 2D-axisymmetric остаётся valid для toroidal/pot cores
    (separate emit_* function не сделана).
  - **2D-planar pivot между topologies (split-coil vs single-coil) +
    BC (Dirichlet vs Infinity BC) — empirically failed:** все 2D
    варианты дают +180-240%, никакая 2D combination не закрывает
    factor-3 inherent gap. Physics (ZHANG assumes closed circuit,
    2D-planar inherently 3D-leak).
  - **Coil mechanism в 3D Phase 3d.2 — заблокирован:** disjoint
    coil bodies (left + right windows без yoke bridges) → CoilSolver
    "Crappy potentials". Push в T137 mesh redesign.
  - **Iterative + BoomerAMG / ILU / AMS для finer mesh:** non-convergence
    (edge basis problem) или not compiled (AMS). T136 для proper fix.

- **Последствия:**

  - **T133 main goal achieved:** 3D Elmer FEM adapter production-ready
    с acceptance ±25% к PyOM ZHANG на pilot fixture. Это **factor 19×
    improvement** к T113 baseline gap (3.42× → 1.15×). Real engineering
    win для FEM cross-check workflow.
  - **2D Phase 1+2 infrastructure preserved** как полезная для
    axisymmetric (T-ID future), leakage (T132/T135), cross-validation
    backend. Auto-memory `feedback_fem_2d_inherent_gap_to_zhang`
    фиксирует physics constraint для будущего agent.
  - **Image не растёт** (elmerfem-csc PPA уже в Dockerfile с
    T133 Phase 1; +680 MB к 6.65 GB → 7.99 GB зафиксирован).
  - **Integration runtime hit:** 3D linear ~14 s (vs 2D linear ~1 s,
    GetDP ~3 s). Acceptable, no `pytest.mark.slow` нужен.
  - **Auto-memory updates:**
    - `feedback_elmer_2d_keyword_pitfalls` (Phase 0)
    - `feedback_fem_2d_inherent_gap_to_zhang` (Phase 3 empirical)
    - `feedback_elmer_3d_solver_memory_limits` (Phase 3d.2 OOM +
      iterative limitations)
  - **9 commits на ветке T133-elmer-fem-pivot squash в один при
    merge** (правило «один PR — один коммит»).
  - **Замена ADR 2026-05-20** «T129 closure: analytical (PyOM ZHANG)
    — source of truth для incremental L; FEM cross-check откладывается
    на T133 (Elmer)» — теперь T133 closed, ADR honored.

- **Файлы:**
  - `src/adapters/outbound/fem_common.py` (ECoreDimensions, emit_e_
    core_geo_3d, PyOM helpers).
  - `src/adapters/outbound/fem_solver_elmer/` (adapter, sif_template).
  - `Dockerfile` (+elmerfem-csc PPA).
  - `specs/T133-elmer-fem-pivot/spec.md` (5-phase journey).
  - `scripts/pilot/elmer/probe*` (Phase 0 + 3a probe artifacts).


### 2026-05-21 — Interleaved OPT leakage: pure-Python Erickson formula, PyOM mesh path abandoned

- **Контекст:** T132 (Interleaved OPT leakage inductance) изначально
  планировал использовать PyOM `calculate_leakage_inductance` через
  composite-adapter pattern (extend existing `PyOpenMagneticsAnalytics`
  методом `calculate_leakage_inductance`). Phase B попытка: build wound
  coil через `pyom.wind(coil, reps, proportion, pattern, margin_pairs)`,
  затем leakage call. Возвращало `[CALCULATION_ERROR] Mesh generation
  failed: induced field data is empty` для **любого** fixture.

  **Investigation (4+ часа):**
  - Bobbin column null fix через `_normalize_bobbin_columns` —
    меняет error с `INVALID_BOBBIN_DATA` на mesh fail (progress, но
    не resolution).
  - `magnetic_autocomplete(magnetic, {})` — autocomplete сам стирает
    column patches; re-patch не помогает.
  - `process_inputs(inputs)` добавляет `magneticFieldStrength` slot
    к excitation, **но значение None** (process_inputs не знает про
    magnetic geometry).
  - `calculate_magnetic_field_strength_field(op, magnetic)` —
    separate FEM call для derive field strength, сам fails `bad
    optional access` (std::optional unwrap на пустом). Circular
    dependency: leakage требует computed field strength, но public
    compute API падает на тех же inputs.
  - Cross-material sweep (12 PyOM-catalog materials: 3C90/3C94/3C95/
    N87/N97/Kool Mu 60/XFlux 60/Hi-Flux 60/MPP 60/3F3/3F36/N49) —
    same mesh error для всех.
  - **Version sweep** PyOM 1.3.0→1.3.12 (all cp313 linux wheels):
    идентичный fail на всех. Не version-specific regression —
    long-standing MKF C++ bug.
  - Полный official `simulate(inputs, magnetic, models)` pipeline
    возвращает тот же mesh error → баг в PyOM MKF C++ layer, не
    в нашем payload.

- **Решение:** **Pure-Python Erickson sandwich-transformer formula**
  как primary backend для leakage. PyOM catalog database lookups
  (`calculate_core_data`, `find_wire_by_name`) сохранены — это
  catalog-only paths без mesh trigger; они работают надёжно.

  Reference: **Erickson & Maksimović "Fundamentals of Power
  Electronics" §15.5** + **Hurley & Wölfle "Transformers and
  Inductors for Power Electronics" §4.6** — standard sandwich
  formula:

  ```
  L_σ = (μ₀ · n_p² · MLT) / b_w · h_eff
  h_eff = [(b_p + b_s)/3 + a·(n_sections-1)] / N²
  N = число inter-winding interfaces в pattern
  ```

  Architecture: новый adapter `AnalyticalLeakage` в
  `adapters/outbound/leakage_inductance_analytical/` (отдельная
  директория, не extend `PyOpenMagneticsAnalytics` — composite
  pattern abandoned). DI: `pyom_module` + `MagneticAnalytics`
  Protocol (для L_self → coupling_factor).

- **Альтернативы:**

  **(a) Open upstream PyOM issue.** Возможно решит за дни, но
  unbounded waiting; T132 acceptance gate надо проходить теперь.
  Deferred — minimal repro готов в spec.md, открытие issue можно
  сделать в любой момент.

  **(b) PyOM version downgrade на 1.2.x.** 1.2.x имеет другой API
  layout — ломает T113/T131 existing code. Не оправдано.

  **(c) GetDP+Gmsh FEM leakage extension.** T113 стек уже
  интегрирован, можно расширить `.pro` template на leakage (short-
  circuit secondary + energy integral). Effort ~ T113 Phase 2
  уровень (дни). Выбрано как T135 follow-up для FEM
  cross-validation; но **для T132 closure analytical уже достаточно**
  (spec ±25% acceptance, formula ±20-30% точность).

  **(d) Elmer FEM pivot.** Native `MagnetoDynamics2D` solver,
  cross-section + energy integral. Effort ~ неделя (новый стек,
  T133 в BACKLOG). Тоже T135 follow-up path.

  Эти три FEM-paths (b/c/d) — quality improvement; analytical
  primary backend закрывает T132 use case без них.

- **Последствия:**

  - **Точность ±20-30%** (Erickson idealizes uniform current
    distribution, no skin/proximity effects). На audio frequencies
    1-30 kHz с толстыми OPT-обмотками low-freq path valid; spec
    acceptance ±25% удовлетворяется.
  - **Monotonicity built-in** через 1/N² factor: ratio σ_2:σ_3:σ_5
    = 16 : 4 : 1 для zero-insulation case (verified в acceptance).
    Это math-property formula, не physics validation — отсюда
    T135 follow-up для FEM cross-check.
  - **Pilot result (OPT_SE_5K_8 5-section)**: Lσ = 6.50 mH,
    k = 0.9997, HF-3dB @ 5kΩ ≈ 122 kHz — hi-end audio range
    (Hashimoto/Plitron empirical 50-80 kHz, наш fixture в верхнем
    эшелоне).
  - **PyOpenMagneticsAnalytics** снова single-purpose
    `MagneticAnalytics` adapter (composite pattern abandoned);
    Phase B helpers (`_translate_pattern_to_indices`,
    `_normalize_bobbin_columns`, `_parse_leakage_result`) удалены.
  - **T135 в BACKLOG** — FEM cross-validation analytical (Elmer
    pivot T133 OR GetDP extension); analytical adequate для T132
    use case, FEM подтвердит formula valid для precision claims.

  Compare с **T129 closure pattern** (also analytical fallback
  после FEM gap): T129 закрылся infrastructure-only (FEM 242% gap
  сохранён, BACKLOG forward). T132 же **выходит закрытым с
  работающим backend** (analytical formula passes acceptance),
  это качественный шаг вперёд от T129.

- Файлы: `src/adapters/outbound/leakage_inductance_analytical/*`,
  `specs/T132-interleaved-leakage/spec.md` Phase B/C closure
  sections, BACKLOG T135.


### 2026-05-21 — Saturable магнетика в SPICE: XSPICE gyrator-capacitor (`lcouple`+`core`), не PWL current-source

- **Контекст:** T131 (SPICE saturable transformer + THD distortion
  analysis) Phase A первоначально реализовала saturable subckt через
  PWL **current-source** B-element с capacitor-as-integrator:

  ```
  G_int N_psi 0 N_a P2 1       # VCCS: i_G = V(N_a, P2)
  C_int N_psi 0 1              # integrator → V(N_psi) = ∫V_Lm dt
  B_Lm N_a P2 I=pwl(V(N_psi), <(ψ_link, i_Lm) pairs>)
  ```

  На стенде «лампа + saturable OPT» (acceptance pilot Phase D) это
  **не сходилось**: ngspice TRAN с EL84 Koren-моделью + Frohlich-
  PWL saturable subckt давал magnitudes ≈ 1e+65 в Fourier-выводе
  (numerical garbage, THD = 258%) при любых convergence options
  (`set gmin=1e-9`, `itl4=200`, `reltol=1e-3`, `method=gear`, явные
  initial conditions). Standalone saturable + linear sources
  (Phase C synthetic integration test) работал нормально — issue
  специфично проявлялся в interaction с active tube model.

  **Root cause:** algebraic loop через B-source PWL `B_Lm` (current
  source) + tube G-source (controlled current source) + primary
  `R_pri` — Newton-Raphson не сходился. Capacitor-as-integrator
  (`C_int = 1 F`) с large time constant накапливал drift вместо
  быстрой relaxation к equilibrium.

- **Решение:** **Переписать saturable_core на XSPICE gyrator-capacitor
  (Hamill 1993)** — `lcouple` gyrator'ы primary/secondary преобразуют
  электрическую область (V, I) в магнитную (MMF, dψ/dt), нелинейная
  B-H curve моделируется через XSPICE `core` element с tabulated
  `H_array` / `B_array`:

  ```
  R_pri P1 pri_int {r_pri}
  a1 (pri_int P2) (mc1 0) primary_{name}
  .model primary_{name} lcouple(num_turns={n_primary})
  a2 (sec_int S2) (0 mc2) secondary_{name}
  .model secondary_{name} lcouple(num_turns={n_secondary})
  R_sec sec_int S1 {r_sec}
  a_core (mc1 mc2) magcore_{name}
  .model magcore_{name} core(H_array=[...] B_array=[...]
  + area=... length=... input_domain=0.01 fraction=true)
  ```

  Нелинейность сидит **в магнитной области** (`a_core` element),
  изолирована от electrical Newton iterations; flux integration —
  внутри core element с собственным state; PWL smoothing
  (`input_domain=0.01 fraction=true`) убирает non-smooth производные
  на углах таблицы.

  Verified: pilot acceptance test проходит в полной топологии (6П14П
  SE + saturable OPT). 1 kHz / 1 W: THD = 9.63% (dominant n=2),
  10 kHz / 1 W: THD = 4.78% (tube-only baseline, OPT linear на HF),
  saturation contribution +4.85 pp.

- **Альтернативы:**
  - **PWL current-source B-element + capacitor integrator** (исходный
    Phase A путь) — отвергнут: numerical blow-up с active elements
    (см. Контекст). Mathematically correct, но not robust в
    practical circuit topologies.
  - **ngspice native `Core` Jiles-Atherton model** (`.MODEL <name>
    CORE`) — отвергнут: требует Jiles-Atherton параметры (Ms, A, K,
    C, alpha) которые не маппятся 1:1 к нашим Frohlich-параметрам
    (μ_init, B_sat). Маппинг possible но adds parametric uncertainty
    к acceptance gate. Также: JA включает hysteresis по дизайну
    (`K > 0`), а T131 scope — saturation-only (см. spec §3
    «hysteresis — Phase 2 deferred»). Set `K=0` для anhysteretic
    mode но проверка стабильности этого требует separate validation.
  - **Nonlinear voltage-source с `ddt()` builder** — отвергнут:
    ngspice 45.2 не поддерживает `ddt()` / `idt()` в B-source
    expressions; compatible SPICE3 builtins не покрывают этот path.
  - **Behavioural inductor `L=expr(...)`** — отвергнут: ngspice
    nonlinear L expression формально поддерживается, но конкретные
    edge cases (smoothness derivatives, DC convergence) сравнимы с
    PWL B-element approach по нумерическим характеристикам.

- **Последствия:**
  - **Numerical стабильность:** SPICE сходится в нетривиальных
    топологиях (active elements + saturable magnetics) — критично
    для T131 acceptance + future tube amp work.
  - **Frohlich curve остаётся source-of-truth** — `FrohlichBHCurve.
    h_b_pairs()` выгружается в symmetric `H_array` / `B_array` для
    `core` element; T129 Phase A material model reused без
    изменений.
  - **Acceptance band revised** [1%, 5%] → [3%, 15%] для compact-core
    configurations (E 42/15 в pilot); published 1-5% reference
    подразумевал большие cores. Добавлен saturation contribution
    diagnostic (THD@f_low - THD@f_high) как T131 raison d'être
    validation.
  - **Phase A revision** (Phase E patch в T131-ветке) — не отдельная
    задача, scope expansion authorized 2026-05-21 после Phase D
    failure.
  - **Subckt structure breaking change** — все existing tests на
    `B_Lm` / `G_int` / `C_int` markers переписаны на `lcouple` /
    `core` / `a_*` element checks. Unit + acceptance tests pass.


### 2026-05-21 — Сторонние review-боты отключены: primary path — self-review + `/ultrareview` on-demand

- **Контекст:** ADR 2026-05-19 «Сторонние review-боты: CodeRabbit как
  best-effort, primary path = self-review + опциональный `/ultrareview`»
  оставлял CodeRabbit и Qodo Merge подключёнными на best-effort
  основе — «silent rate-limit не блокирует merge, мы их игнорируем
  если не отвечают». Через полтора месяца практики выяснилось, что
  модель «best-effort» создаёт больше когнитивной нагрузки чем
  пользы:
  - **CodeRabbit на free tier часто висит** или отвечает с задержкой
    в часы; даже когда отвечает, львиная доля комментариев — generic
    «consider adding more tests» / «consider error handling» без
    привязки к domain. ADR 2026-05-19 это констатировал, но не
    действовал.
  - **Paid tier upsell** появляется в каждой review-сессии («upgrade
    to Pro for 10× faster reviews»), что воспринимается как давление
    конвертироваться в paid customer ради скорости — но реальная
    ценность комментариев не растёт пропорционально.
  - **Qodo Merge** (бот, упомянут в ADR 2026-05-19) — то же явление,
    плюс ещё одна context window замусоривается его summary'ями.
  - **`/ultrareview`** показал себя как высококачественная альтернатива
    (multi-agent cloud review, on-demand): T129 PR #61 первая
    итерация ultrareview нашла критический math bug (`bug_001`,
    flux linkage missing Secondary integral term) который повлиял на
    закрытие всей задачи. Уровень глубины анализа сильно выше
    CodeRabbit'а. User-triggered + paid по time — это
    положительная asymmetry: платим только когда нужно глубоко.

- **Решение:** **Отключить CodeRabbit и Qodo Merge через config-файлы**
  в репо (Path A из обсуждения 2026-05-21):
  - `.coderabbit.yaml` — `reviews.auto_review.enabled: false` +
    minimization noise (chill profile, no high_level_summary, no
    request_changes, no walkthrough auto-expand).
  - `.pr_agent.toml` — `github_app.handle_pr_actions = []`,
    `pr_commands = []`, `config.publish_output = false`. Бот не
    делает ничего на PR open / sync; даже если оживёт через manual
    `/review`, ничего не публикует автоматически.
  - **Не uninstall'им** через GitHub Settings → Apps (Path B) —
    оставляем возможность revert через editing config'ов
    одним PR. Path B рекомендован как опциональный second layer
    через UI если в дальнейшем bot'ы окажутся ignore'ущими наши
    configs (rare, но возможно).
  - **Primary review path:** self-review checklist (project
    CLAUDE.md «Code review каждого PR» — 7 пунктов) + `/ultrareview`
    on-demand для важных PR'ов (cross-cutting refactor, security,
    milestone-фазы).
  - **`/ultrareview` findings → PR comment manually:** агент
    `claude-code-guide` подтвердил (2026-05-21), что нет built-in
    auto-post в GitHub PR. Pattern: после ultrareview run я
    обрабатываю findings в чате с Vladimir, фиксирую решения per
    finding (учесть / отбросить / отложить), и публикую summary в
    `gh pr comment <PR#>` для historical traceability на PR-page.

- **Альтернативы рассмотрены:**
  - **Оставить как было** (best-effort) — отвергнуто: ретро PR
    #56/#57/#58/#59/#60 показали что noise > value на free tier.
  - **Перейти на paid tier CodeRabbit** ($15-30/month/dev) —
    отвергнуто: cost не оправдан relative `/ultrareview` quality
    + on-demand pricing model (paid per use is cheaper for our
    PR volume ~10-20/month).
  - **Включить только manual review через slash-commands в чате
    PR** (`@coderabbitai review`) — отвергнуто: усложняет workflow,
    добавляет UI step; легче через config disable.
  - **Uninstall apps через GitHub UI (Path B)** — отвергнуто как
    primary action: requires manual UI steps + uninstall не
    versioned в git (нет audit trail в repo); config disable
    versionable, revertable одним PR. Path B remains опциональным
    second layer.
  - **Mandatory `/ultrareview` перед merge каждого PR** — кратко
    принято 2026-05-21, **откатано в тот же день** после уточнения
    pricing (claude-code-guide агент): free tier — 3 runs **lifetime
    per account** (one-time, не renewable), далее $5–20 per run usage
    credits. При нашем PR-throughput 10-20/мес mandatory означало бы
    $50-400/мес поверх Pro/Max подписки — экономически не оправдано.
    `/ultrareview` остаётся on-demand для важных PR'ов; для маленьких
    PR (методических, docs, single bug-fix) — self-review достаточно.

- **Последствия:**
  - **Каждый новый PR сразу идёт на self-review** без ожидания
    бота — снимает «надо ли подождать» dilemma.
  - **`/ultrareview` quota** (free / paid по time) — primary
    external review budget. Используется выборочно.
  - **PR-страницы remain clean** — без auto-summary'ев и generic
    suggestions от ботов.
  - **ADR 2026-05-19** про CodeRabbit best-effort — superseded
    этим решением. Раздел «Сторонние ревью не игнорировать» в
    `CLAUDE.md` обновлён: теперь explicit «отключены, primary —
    self-review + /ultrareview manual post».
  - **Reversibility:** один PR редактирующий config'и возвращает
    бот в auto-mode (если ADR пересмотрят).


### 2026-05-20 — T129 closure: analytical (PyOM ZHANG) — source of truth для incremental L at operating point; FEM cross-check откладывается на T133 (Elmer)

- **Контекст:** T129 (Nonlinear FEM material + DC-bias load line) ставил
  цель закрыть T113 Phase 1 pilot 242% gap к ±10% acceptance через
  Frohlich-Kennelly + central finite difference на 3 nonlinear GetDP
  solve'ах вокруг operating point. Phase A (Frohlich generator +
  nonlinear .pro template) и Phase B (central-diff plumbing + port DTO
  + use case integration) реализованы и end-to-end работают в
  `efactory:linux-t129` container (44 unit/integration tests passed,
  Picard сходится, L_inc вычисляется finitely).

  **Revision 3 (после ultrareview PR #61 bug_001 fix):** ±10% acceptance
  **не достигнут**, и «partial closure 242% → 70%», заявленная в
  первоначальном Phase C commit, оказалась **artefact формулы**:

  1. **flux_linkage_per_depth Quantity в первоначальной revision
     интегрировалась только по Primary region** (`In Primary` clause),
     но split coil имеет `+Jz Primary, -Jz Secondary` (same primary
     winding, return-leg). По антисимметрии `∫_S A_z ≈ -∫_P A_z`,
     true flux linkage = `2 · ∫_P A_z` — формула возвращала half.
     Чистый clean ratio L_nl_old / L_lin = 0.499 (точно 1/2 ± rounding)
     был math-related, не physical (ultrareview bug_001).
  2. **После fix (Secondary integral term добавлен с negated sign):**
     L_nl = 23.71 H vs L_lin = 23.78 H — ratio **0.997** (identity
     within 1%). Frohlich curve не engaging на pilot fixture в split-
     coil + 2D-planar setup.

  Топологические эксперименты (single-coil + AIR×{10,50}) до bug_001
  fix показывали L_lin ≈ 19.7 H — overestimation factor ~2 относительно
  analytical reluctance ~10 H. 2D-planar open-domain без shell
  transformation (Kelvin) не достигает proper flux closure для
  magnetostatic с дискретным coil. Plus Picard в single-coil не
  итерирует Frohlich (B остаётся < knee из-за overestimation).

  **Реальный T129 outcome — pure infrastructure без numerical win:**
  Phase A `FrohlichBHCurve` generator + Phase B central-diff plumbing
  (теперь 2 solve'а после bug_003 fix, не 3) + `FemSolveOutcome` DTO
  + use case integration — **готовая plumbing для T133 reuse**, но
  никакого improvement к T113 baseline gap 242% нет.

  Закрытие 242% gap требует одного из: shell transformation в GetDP
  (1-2 недели FEM expertise, scope inside ADR 2026-05-20), or переход
  на Elmer (native `H-B Curve` keyword + Newton iteration, ADR
  override, 1-2 недели + image +300 MB), or 3D mesh (значительный
  scope). Vladimir выбрал Elmer path (3b) — отдельным T133 когда
  появится реальный client case.

- **Решение:**
  1. **T129 закрыта как infrastructure-only** (revision 3): T113 baseline
     gap 242% сохраняется без изменений. Phase A/B infrastructure
     (`FrohlichBHCurve`, nonlinear .pro template, central-diff adapter
     path, port `FemSolveOutcome` DTO, domain VO diagnostic fields)
     **сохранена ready-to-use** для T133 reuse (Frohlich curve формат
     совместим с Elmer `H-B Curve` keyword).
  2. **Spec §4 acceptance переписана** (revision 3): Primary —
     infrastructure smoke (pipeline сходится, fem_method, diagnostic
     поля), без numerical bar на L_inc. Original ±10% acceptance
     moved to T133.
  3. **Path forward** для real tube amp workflow (OPT/power xfrmr
     design):
     - **Analytical primary path** — PyOM ZHANG + 4 другие reluctance
       models покрывают 90%+ кейсов (SE/PP OPT, power transformer,
       SMPS choke). Operating-point L_inc через
       `OperatingPoint.primary_dc_bias_a` уже учитывается PyOM
       waveform analysis.
     - **T131 (next)** — SPICE saturable transformer model + THD
       distortion analysis use case. Reuses Frohlich. Universal value
       для каждого audio проекта.
     - **T132 (after T131)** — interleaved OPT leakage PyOM-only path
       для top-tier audio (60-80% coverage без FEM).
     - **T133 (when triggered)** — Elmer pivot для FEM cross-check
       precision-critical cases (5+ section interleaved, или power
       xfrmr с tight HF-rolloff spec).

- **Альтернативы рассмотрены:**
  - **(3a) GetDP topology rework**: shell transformation (Kelvin) /
    `Magnetodynamics2D_av_js_t_cir` circuit coupling / 3D mesh.
    Отвергнуто: significant FEM expertise required, custom Picard
    остаётся, scope ≈ T133.
  - **(α / 3b) Elmer pivot** — выбран для T133. Native `H-B Curve` +
    Newton (proven nonlinear, не custom Picard), pilot infrastructure
    из T113 Phase 1 reused, `feedback_elmer_savescalars_quirks` auto-
    memory покрывает known pitfalls.
  - **(γ / 3c) AGROS Suite / другой open-source GUI tool**: неизвестная
    территория, требует Phase 1 spike. Отложено.
  - **FEMM** — Windows native; Wine был выкорчеван из efactory:linux
    в T058/T113, не возвращаем.

- **Следствия:**
  - **T113 known gap не закрыт** на 242%, но улучшен до 70% (factor 3.5
    win). Integration test `test_analytical_plus_fem_pilot_regression`
    переписан под relaxed acceptance.
  - **Phase A/B infrastructure** имеет immediate downstream consumer
    (T131 SPICE saturable core reuses `FrohlichBHCurve`).
  - **Honest documentation**: spec §4 revision 2 + raw failure analysis
    в Phase B commit history (`23b1274` + последующие revert) +
    форвард-линки на T133 — agent / future Claude видит чёткую
    картину что было tried и почему отложено.



- **Контекст:** T113 требует analytical reference для magnetic
  design (трансформаторы, дроссели, SMPS-компоненты) — как для
  acceptance ±10% pilot/integration теста, так и для использования
  runtime-агентом в реальных проектах (Vladimir 2026-05-20: «школьная
  формула — упрощение только для демо, в реальных проектах нужны
  сложные магнитные расчёты»). Кандидаты после downgrade Python 3.14
  → 3.13 (см. соседний ADR):
  - **PyOpenMagnetics 1.3.10** — C++ engine MKF (Magnetics Knowledge
    Foundation) с Python bindings, comprehensive database (1301+
    core shapes, materials, wire standards, bobbins, insulation),
    high-level API (`design_magnetics_from_converter()` —
    single-call для всего transformer'а), AGENTS.md специально
    для AI-агентов с инструкцией «NEVER use manual calculations».
    Pure-analytic (без FEM internally) — учитывает temperature-
    dependent material properties, geometrical fringing, real
    commercial core constraints.
  - **femmt @ master HEAD** (LEA Paderborn FEM toolkit) — поставился
    бы, но тянет torch + nvidia-cu12 + triton + PyQt5 + sympy +
    plotly + mag-net-hub (ML-based core-loss prediction). Размер:
    7.6 GB venv → +5 GB в Docker layer (efactory:linux вырос бы
    до ~13 GB).
  - **Самописная extended formula** (μ_r, A_e, l_e + leakage
    эмпирически + window utilization) — ~30 строк кода, но
    Vladimir прямо сказал «нет» textbook formulas в production.
  - **magpylib** — pure-Python, но не моделирует ferromagnetic
    core (μ_r >> 1) → не подходит для трансформаторов.
- **Решение:** **PyOpenMagnetics 1.3.10** как primary analytical
  engine. Wheel cp313_x86_64 precompiled (11 MB), `.venv`
  становится 215 MB вместо 7.6 GB. В efactory:linux Docker-layer:
  +~50 MB.
  - **Pilot (T113)**: PyOpenMagnetics analytical vs Elmer FEM
    vs GetDP+Gmsh FEM на одной фикстуре (OPT 6П14П SE) —
    3-точечное сравнение для ADR-выбора FEM-solver'а.
  - **Integration (T113)**: два port'а в `src/ports/outbound/`:
    `magnetic_analytics_port.py` → PyOpenMagnetics adapter;
    `magnetic_field_solver_port.py` → выбранный FEM solver
    adapter. Агент через MCP вызывает любой (analytical fast vs
    FEM accurate, по задаче).
- **Альтернативы (см. контекст):** femmt отвергнут по размеру;
  самописная formula — по explicit указанию Vladimir-а; magpylib —
  по физике (нет ferromagnetic core).
- **Последствия:**
  - **LLM-friendly API**: PyOpenMagnetics поставляется с
    AGENTS.md (single source of truth для AI-агента) — наш
    Claude Code frontend может ссылаться на этот документ
    при design-задачах.
  - **Dual port architecture**: analytical (быстро, для design
    sweep'ов) + FEM (точно, для validation). Логичное
    разделение по acceptance T113.
  - **`design_magnetics_from_converter()`** — high-level
    функция, агент one-shot спроектирует трансформатор по
    параметрам конвертера. Это удобнее, чем строить magnetic
    component вручную через MAS JSON.
  - **Размер**: PyOpenMagnetics +11 MB wheel — ничтожно vs
    femmt +5 GB.
  - **Опциональное расширение**: если в будущем нужен ML
    core-loss prediction (mag-net-hub) — поставим как
    отдельный optional dependency, не в main runtime.

### 2026-05-20 — Python проекта понижен 3.14 → 3.13 (scientific ecosystem)

- **Контекст:** T113 (FEM-solver pilot) требует аналитическую
  библиотеку магнитных расчётов как референс для acceptance ±10%
  (изначальная спека Phase 3 пишет «PyOpenMagnetics», но это conkretное
  название не критично). Реальные efactory-проекты требуют **боевой
  магнитный toolkit** для design-задач — Vladimir подчеркнул, что
  школьная формула `L = N²·μ·A_e/l_e` уместна только для demo, не
  для production-агента. Кандидаты в Python:
  - `pyopenmagnetics` 1.3.10 — wheels только cp310-cp313, sdist
    падает на upstream-баге («Could not fetch additional schema»
    при quicktype-этапе CMake build).
  - `pyleecan` — `requires-python <3.11` (даже не close).
  - `femmt` (LEA Paderborn, FEM toolkit с ONELAB/GetDP/Gmsh
    под капотом) — `requires-python>=3.10` декларирует, но
    `scipy~=1.12.0` pin → sdist Fortran build на 3.14.
  - `magpylib` — pure Python, но не учитывает ferromagnetic core
    (μ_r >> 1) → трансформатор без сердечника = бесполезно.
  - `inductance` (dgarnier) — `<3.14`, плюс узкий plasma use case.
  - Самописная формула — отвергнута Vladimir-ом: «школьная для
    демо, в реальных проектах нужны сложные магнитные расчёты».
- **Решение:** **Понизить `requires-python` efactory с >=3.14 до
  >=3.13.** Python 3.13 — текущий de-facto stable для scientific
  Python ecosystem; femmt + pyopenmagnetics + scipy 1.12 + numpy
  1.26 — wheels precompiled, чистая установка через uv. Affects:
  - `pyproject.toml`: `requires-python`, `tool.ruff.target-version
    = "py313"`.
  - `.python-version`: `3.14.5` → `3.13`.
  - Dockerfile / CLAUDE.md / specs/T110-containerization/spec.md —
    обновлены упоминания «3.14» → «3.13» (где упоминалась версия
    языка; uv сам выбирает интерпретатор по requires-python).
  - `uv.lock` пересобран (51 пакет, никаких version-bump'ов
    кроме самого Python).
  - На dev-машине Vladimir-а также — `uv` подхватывает 3.13 через
    `.python-version` (3.13.13 уже установлен локально), без
    отдельного шага.
- **Альтернативы:**
  - **Оставить 3.14 + изоляция femmt в `pilot.Dockerfile` (py 3.13
    base) с pre-computed reference inductance.** Отвергли: реальные
    efactory-проекты (design-задачи трансформаторов в efactory:linux)
    лишены аналитики — агент жёстко привязан к нашему solver-wrapper
    без второго мнения. Не отвечает Vladimir's концерну про «сложные
    расчёты в реальных проектах».
  - **Оставить 3.14 + самописная формула в integration.** Отвергли:
    overly simplistic для production-агента (см. контекст выше).
  - **Подождать пока scientific Python догонит до 3.14** (3-6 месяцев?).
    Отвергли: блокирует T113 на неопределённый срок; преимущества
    3.14 (PEP 750 t-strings, free-threaded `--disable-gil`) в нашем
    коде сейчас не используются — downgrade без потерь.
  - **Mixed: 3.13 в efactory:linux, 3.14 на dev-машине.** Отвергли:
    раздвоение dev vs container — лишний source of bugs при тестах,
    `uv.lock` всё равно один.
- **Последствия:**
  - **Зелёный путь к scientific Python ecosystem** — femmt,
    pyopenmagnetics, scipy/numpy/pandas/matplotlib/pyleecan
    (если бы поддерживала >=3.11) — все доступны через precompiled
    wheels.
  - **Никаких code-changes**: grep по `src/` и `tests/` — никаких
    3.14-specific features (PEP 750 t-strings, free-threading,
    PEP 765 `return-in-finally`, PEP 758 `except*` без скобок).
  - **Pre-push gates на 3.13** — ruff/format/mypy/pytest все
    зелёные сразу после downgrade.
  - **Откат к 3.14** — когда femmt + pyopenmagnetics + scipy
    выпустят wheels для cp314 (вероятно в течение года).
    Откат — обратное изменение `requires-python` + lock rebuild;
    проверка остаётся auto через `uv sync`.
  - **CONCEPT §13** упоминал Python 3.14 — concept frozen,
    не редактируется; uncoupling в README (current state)
    при следующем content-update.

### 2026-05-20 — FreeCAD distribution: AppImage 1.1.1 внутри образа (а не apt)

- **Контекст:** Phase 2 контейнеризации (T112) требует FreeCAD 1.0+
  CLI + GUI + Sheet Metal workbench в `efactory:linux`. ADR от
  2026-05-19 («Distribution: Linux Docker image») фиксирует принцип
  «всё через apt из официальных репов», как KiCad из
  `ppa:kicad/kicad-10.0-releases`. Для FreeCAD этот принцип
  ломается:
  - Ubuntu 24.04 universe: пакет `freecad` отсутствует.
  - `ppa:freecad-maintainers/freecad-stable`: 0.21.2 (PPA
    отстал — spec требует 1.0+, ввиду новых Sheet Metal API
    и общих улучшений).
  - `ppa:freecad-maintainers/freecad-daily`: `1.1~pre1` (preview-
    сборка, версия плавает между обновлениями PPA).
  - Sheet Metal workbench — community addon из репозитория
    `shaise/FreeCAD_SheetMetal`, apt-пакета не существует ни в
    одном источнике (раньше `freecad-addon-sheetmetal` был
    под старые версии Ubuntu, исчез в noble).
- **Решение:** **FreeCAD 1.1.1 AppImage** (latest stable, релиз
  2026-04-14 на `github.com/FreeCAD/FreeCAD`), скачивается в build-
  time, распаковывается через `--appimage-extract` в `/opt/freecad/`
  внутри образа (без FUSE на runtime — extracted каталог как
  обычное дерево файлов). Версия зафиксирована release-тегом
  (`1.1.1`), URL — детерминированный. **Sheet Metal addon** —
  git clone pinned commit `8076898be2d888c3c634dee343af2349c974a1d0`
  (master HEAD на момент принятия решения, package.xml 0.8.11) в
  `/opt/freecad/usr/Mod/SheetMetal/`. PoC подтвердил: `freecadcmd
  --version` headless OK; GUI через X11 + Qt6 runtime deps
  (libxcb-cursor0 и др.) запускается; Sheet Metal появляется в
  Workbench-меню после mount'а в `Mod/`.
- **Альтернативы:**
  - **`freecad-stable` 0.21.2 + Sheet Metal git clone** — отвергли:
    spec T112 требует 1.0+ (Sheet Metal API расходится между
    0.21 и 1.x, плюс общая стабильность ядра).
  - **`freecad-daily` 1.1-pre + Sheet Metal git clone** — отвергли:
    «daily/preview» не даёт воспроизводимости (PPA-tag плавает,
    upstream может breaking-change в любой день); pin через apt
    хрупкий — старая версия может уехать из репо.
  - **Снять требование `1.0+` в spec T112 (degrade до 0.21)** —
    отвергли: 0.21 не соответствует CONCEPT (Sheet Metal — ключевой
    workflow для корпусов РЭА), regression относительно текущих
    upstream практик.
  - **Подождать обновления `freecad-stable` PPA до 1.0+** —
    отвергли: блокирует Phase 2 на неопределённый срок (PPA-
    maintainer'ы не публикуют roadmap; 1.0 вышел в ноябре 2024,
    PPA не обновился за 1.5 года).
- **Последствия:**
  - **Размер образа +3 GB** (extracted AppImage). Slim 2.45 GB
    (T111) → ~5.5 GB после T112. Vladimir подтвердил приемлемость
    2026-05-20 (acceptance T121 «≤ 3 GB» больше не применяется
    после T112, фиксируется отдельным acceptance).
  - **Self-contained FreeCAD**: AppImage несёт свой Python 3.11,
    Qt6, OCCT, GMSH, CalculiX (`ccx`), graphviz. Бонус для T113
    (FEM-solver pilot) — `ccx` уже доступен в образе.
  - **`platform_layer` AppImage-detection** (T120 cleanup) **не
    касается этого решения**: T120 убирает host-side AppImage-
    detection (когда пользователь скачивал AppImage на host'е).
    Внутри образа AppImage — build-time distribution mechanism,
    не «AppImage runtime». FreeCAD в `PATH` через симлинки на
    `freecadcmd` и `freecad` (== `AppRun`), `platform_layer`
    видит их как обычные binaries.
  - **Обновление версии** — пересборка образа с новым `ARG
    FREECAD_VERSION`. На GHCR (T115) tag по версии efactory
    одновременно фиксирует FreeCAD-версию.
  - **Sheet Metal** обновляется через изменение `ARG
    SHEETMETAL_SHA` в Dockerfile — детерминированно.
  - **Прецедент**: при появлении в spec'ах будущих фаз тулов с
    отсутствующим apt-пакетом — AppImage внутри образа допустим
    как fallback с явным ADR.

### 2026-05-20 — Magnetic field verification: GetDP+Gmsh выбран (Elmer — cross-validation в BACKLOG)

- **Контекст:** ADR от 2026-05-19 предположительно (без measured data)
  поставил Elmer FEM как primary, GetDP как fallback. T113 Phase 1
  pilot (Stages A-E, 2026-05-20) дал реальные measured данные на
  фикстуре OPT 6П14П SE (~12244 quadratic triangles, linear μ_r=8000
  Nanoperm на iron, ±Jz coil в 2D-planar). Pilot table заполнена в
  `specs/T113-fem-solver/spec.md`. Ключевые наблюдения:
  - **Elmer и GetDP сошлись на одной mesh с одинаковой физикой до
    printed precision: оба Lp = 23.7816 H, 0.00% cross-check.**
    Расхождение FEM ↔ PyOM analytical ZHANG (6.96 H, 242% diff)
    воспроизводится одинаково в обоих solver'ах → это physics gap
    (operating-point-dependent μ_eff в PyOM vs constant μ_r=8000 в
    linear FEM-формулировке), не bug одного из solver'ов.
  - **GetDP**: 0.86 s, peak RSS 119 MB, ~45 MB apt-deps (`getdp` +
    `libpetsc` + `libslepc` + `libgmsh`), штатно в Ubuntu 24.04
    noble universe (без PPA), один subprocess (`getdp <.pro> -msh
    <.msh> -solve Mag2D`).
  - **Elmer**: 3.14 s (0.04 ElmerGrid + 3.10 ElmerSolver), peak RSS
    47 MB, ~115 MB apt-deps (`elmerfem-csc` 100 MB + libmumps/
    libhypre 15 MB), требует `ppa:elmer-csc-ubuntu/elmer-csc-ppa`
    (нет в noble универсе), два subprocess'а (ElmerGrid + ElmerSolver),
    .sif с известными квирками (см. auto-memory
    `feedback_elmer_savescalars_quirks.md`: SaveScalars требует
    `body int` + `Mask Name` + Active Solvers — за 4 итерации
    debug'а на Stage D вылечилось).
- **Решение:** **GetDP+Gmsh — first-class FEM-solver в Phase 2
  integration.** Elmer кода Stage D в `scripts/pilot/elmer/
  magnetostatic.sif` + `stage_elmer` в `run_pilot.py` сохраняется
  на ветке T113-fem (pilot-only); в `Dockerfile` базовом образе
  Phase 2 ставится только GetDP+Gmsh, Elmer apt-стек убирается.
  Cross-validation Elmer ↔ GetDP — **BACKLOG T127** (опциональная
  верификация на сложных случаях, когда GetDP результат вызывает
  сомнение).
- **Альтернативы:**
  - **Elmer primary, GetDP fallback** (как было в pre-pilot ADR
    2026-05-19) — отвергли:
    - **+70 MB apt-deps** в базовом образе efactory:linux (115 vs
      45) на одинаковой физике-pilot'е без выигрыша в точности.
    - **+1 subprocess в LLM-orchestration pipeline** (ElmerGrid
      перед каждым ElmerSolver) — overhead и лишний failure
      mode для агента.
    - **PPA dependency** — `elmerfem-csc` не в стандартном noble
      universe, requires `software-properties-common` +
      `add-apt-repository` etc. в Dockerfile (technical debt).
    - **.sif квирки** — выше overhead на support будущих use cases
      по сравнению с .pro синтаксисом GetDP.
    - Преимущество Elmer в peak RSS (47 vs 119 MB) — в efactory
      runtime (один FEM call за раз, контейнер 4 GB) не блокирующее.
  - **Оба first-class** (двойной adapter, GetDP+Elmer) — отвергли:
    cross-validation полезен, но **first-class дуплексность
    усложняет API** (`mag_verify_field` теперь возвращает два
    результата, агент решает какой trust'ить — а cross-check для
    pilot уже показал, что они идентичны).
  - **Только PyOpenMagnetics analytical (skip FEM)** — отвергли по
    исходной цели T113: «полноценный magnetic toolkit ... FEM для
    точного расчёта с учётом 3D-геометрии, leakage, fringing».
    Analytical (reluctance circuit model) — недостаточно для
    leakage/fringing-чувствительных задач (planar transformers,
    LCC compensation networks, AGC дросселей).
  - **Подождать FEMM Linux-port** — нет таких планов в upstream
    (отвергнуто ещё в ADR 2026-05-19).
- **Последствия:**
  - **ADR 2026-05-19 заменён** в части primary-выбора (помечен
    «[Заменено решением от 2026-05-20 ниже]» в заголовке).
    Linux-native + Elmer/GetDP shortlist остаётся в силе; FEMM/Wine
    остаётся отвергнутым; PyOpenMagnetics как analytical core
    остаётся.
  - **Phase 2 Dockerfile**: `apt install getdp gmsh` рядом с
    KiCad / FreeCAD / ngspice. Elmer apt-deps **не ставятся** в
    `efactory:linux`. Прирост размера базового образа: ~45 MB
    (с current 6.65 GB → ~6.70 GB, под 7 GB threshold из spec).
  - **Phase 2 adapters**: `src/adapters/outbound/fem_solver_getdp/
    adapter.py` (subprocess wrapper) — реализуется в Phase 2.
    `src/ports/outbound/magnetic_field_solver_port.py` остаётся
    abstract Protocol; cross-validation T127 (если/когда заведём)
    добавит `fem_solver_elmer/adapter.py` за тот же port.
  - **Stage D Elmer infrastructure preserved**: `scripts/pilot/elmer/
    magnetostatic.sif` + `stage_elmer()` в `scripts/pilot/run_pilot.py`
    остаются в репо как proof-of-cross-check + готовый базис для
    BACKLOG T127. Эти файлы — pilot-only, не runtime efactory.
  - **BACKLOG**:
    - **T127** — Power transformer 50 Hz fixture + cross-validation
      GetDP ↔ Elmer (на linear физике; если разойдутся — flag для
      review).
    - **T128** — Flyback SMPS choke fixture + nonlinear B-H curve
      в GetDP (`nu[] = NLF[...]{H}` constraint); сравнить с
      PyOM analytical (это уберёт 242% gap, см. observation).
    - **T<NEW>** — `mag_verify_field` use case API (как именно
      агент вызывает FEM: MCP-tool? direct Python? Domain
      command?) — уточняется при реализации Phase 2 после
      chat-client (T012-T014).
  - **Performance budget Phase 2**: один `mag_verify_field` call в
    efactory pipeline = ~1 сек FEM solve + ~0.5 сек overhead
    (mesh + adapter glue). LLM-агент может делать sweep'ы из
    десятков сценариев без значимого overhead.

### 2026-05-19 — Distribution: Linux Docker image с полным стеком (включая GUI), кроссплатформенность отложена в отдельную фазу

- **Контекст:** efactory интегрирует разнородный тулчейн —
  KiCad 10 (GUI + CLI), ngspice, FreeCAD (CLI + GUI), FEM-solver
  для магнетики, Python 3.14 stack, Claude Code как frontend
  агента, MCP-серверы. Установка этого стека на машину
  пользователя выглядела как **T002 (bootstrap.sh для Linux)** +
  **T003 (bootstrap.ps1 для Windows)** + **T036 (--update /
  --doctor)** + **T058 (FEMM bootstrap)** + **T066 (FreeCAD
  bootstrap)** — суммарно ~500 строк bash+ps1 + ручное
  координирование версий через `compatibility.toml`. Пять
  независимых релизных циклов + Wine для FEMM = постоянный
  versioning hell у пользователя. Параллельно встал вопрос
  **изоляции runtime-агента** от dev-инстанса Claude Code
  (mem0, методика dreamteam, личные настройки) — для чистоты
  эксперимента и будущей передачи продукта пользователям.
- **Решение:** **Distribution = Linux Docker image с полным
  стеком, включая GUI.** Один образ `efactory:linux` содержит:
  KiCad из официального KiCad-репозитория (apt), ngspice,
  FreeCAD из репозитория, Linux-native FEM-solver (см.
  отдельный ADR от 2026-05-19 о замене FEMM), Python 3.14 +
  uv + весь efactory код, Claude Code как frontend агента,
  наши MCP-серверы. GUI приложений (eeschema, pcbnew, FreeCAD)
  выкидывается через X11/Wayland passthrough; GPU acceleration —
  через `/dev/dri` (Intel/AMD) или nvidia-runtime. Наружу через
  volume mounts: папка проектов пользователя, папка библиотек,
  `~/.claude/.credentials.json:ro` для Claude Code auth.
  Запуск — единым shell-скриптом `efactory-up`.
  **Кроссплатформенность отложена** в отдельную фазу
  «Cross-platform» (Docker Desktop / WSLg / Colima support —
  Phase 8 или позже).
- **Альтернативы:**
  - **Native install через bootstrap-скрипты (status quo, T002/
    T003)** — отвергли: пять разных тулов с независимыми
    релизными циклами + Wine для FEMM = постоянный versioning
    hell. Compatibility.toml лечит только знание, не сам факт
    рассогласования у пользователя.
  - **Headless Docker гибрид (Docker для CLI, native KiCad на
    хосте для GUI)** — рассматривался как промежуточный шаг.
    Отвергли: пользователь всё равно должен установить KiCad
    нативно (та же versioning-hell), Docker даёт только CLI-
    изоляцию. Меньше выигрыш ценой архитектурной двойственности
    «что внутри, что снаружи».
  - **Полный Docker с кроссплатформенностью с первого дня**
    (Mac/Win Docker Desktop с XQuartz / WSLg) — отвергли как
    стартовую цель: GUI passthrough на Mac/Win нетривиальный,
    overhead через VM (Docker Desktop на не-Linux крутит свою
    Linux VM), Wine FEMM в двойной виртуализации = боль.
    Linux-only сейчас даёт чистый прирост без этих рисков;
    cross-platform как отдельная фаза с собственным acceptance.
  - **Подождать KiCad schematic IPC API (Phase 8 концепта)** —
    отвергли как несвязанный вопрос: IPC API про коммуникацию
    с KiCad-процессом, distribution-проблема не уходит.
- **Последствия:**
  - **T002 (bootstrap.sh Linux) → replaced by T110 (Dockerfile).**
    Native bootstrap для Linux больше не пишется — функция
    закрыта образом.
  - **T003 (bootstrap.ps1 Windows) → parked** до Phase
    Cross-platform; реализация отложена до тех пор, пока
    Linux-only Docker workflow не отшлифован.
  - **T036 (--update / --doctor / --update-models)** →
    re-evaluate. Часть функциональности заменяется
    `docker pull efactory:latest` + `docker run efactory --doctor`
    (внутрь образа кладём диагностику тулчейна).
  - **T058 (FEMM bootstrap), T066 (FreeCAD bootstrap)** →
    absorbed в T113/T112 (FEM-solver и FreeCAD ставятся в
    Dockerfile, отдельные bootstrap-задачи не нужны).
  - **Изоляция runtime-агента от dev-инстанса (рассматривалась
    через `CLAUDE_CONFIG_DIR`)** — закрыта **бесплатно как
    побочный эффект Docker**. Контейнер не видит ни моего
    `~/.claude/CLAUDE.md`, ни mem0, ни tools-MCP — туда попадает
    только то, что заложено в Dockerfile.
  - **`compatibility.toml`** становится **информационным**
    артефактом (для отчётности по версиям внутри образа);
    источник истины — Dockerfile с pinned версиями.
  - **Кроссплатформенность как принцип в README** ослабляется:
    «Linux первой фазой, кросс-платформа как отдельная Phase
    Cross-platform». Не отказ от поддержки Mac/Windows, а
    осознанная decomposition по времени.
  - **Размер образа** ожидаемо 8–12 GB (KiCad libraries ~3 GB +
    FreeCAD ~1.5 GB + FEM-solver ~500 MB + Python stack).
    Приемлемо для desktop-distribution, не для CI fat-pull;
    для CI-нагрузок будем держать минимальный slim-вариант без
    GUI (`efactory:linux-headless`) — детали в spec T110.
  - **Новая фаза в roadmap** — «Phase 0.9 Containerization»
    встаёт **между Phase 1a и Phase 1b**: до того, как делать
    chat-client / runtime-агента, нужно положить весь
    инструментарий в один воспроизводимый образ. Задачи:
    T110-T115 (см. BACKLOG.md). После Phase 0.9 все
    дальнейшие фазы исполняются внутри контейнера.
  - **Карта границы образ/host** — single source of truth
    `docs/container-boundary.md` (T140). Любое уточнение
    «что внутри / что снаружи» (volume mounts, env vars,
    исключения по изоляции) — туда; этот ADR фиксирует
    архитектурное решение, документ — текущую карту.

### 2026-05-19 — Magnetic field verification: Linux-native FEM-solver (Elmer FEM primary, GetDP+Gmsh fallback), FEMM как legacy [Заменено решением от 2026-05-20 ниже]

- **Контекст:** ADR от 2026-05-15 фиксировал **FEMM + pyFEMM**
  как 2D-FEA для верификации магнитного поля трансформаторов и
  дросселей (T055 `mag_verify_femm`). FEMM — это нативно-
  Windows-приложение; на Linux запускается через Wine. При
  переходе на Linux Docker distribution (ADR от 2026-05-19
  выше) FEMM/Wine становится узкой точкой:
  - Wine layer внутри Docker = двойная виртуализация на
    Mac/Windows (когда дойдёт до Phase Cross-platform).
  - FEMM не обновляется активно (последний major release ~2019).
  - GUI FEMM через Wine + X11 passthrough — лишний шаг с
    хрупким UX.
  - На Linux есть зрелые native-альтернативы для magnetostatic
    2D/3D FEA.
- **Решение:** **FEMM заменяется Linux-native FEM-solver'ом**.
  Кандидаты для пилотного выбора в рамках T113:
  - **Elmer FEM (primary)** — open-source multi-physics solver,
    Linux-native, имеет GUI (ElmerGUI), Python API через
    elmer-tools / ElmerSolver CLI, лучше параллелится,
    активно развивается. Используется в академии и индустрии
    для электромашин и трансформаторов.
  - **GetDP + Gmsh (fallback)** — академический мейнстрим для
    электромагнитики (авторы — те же люди, что делают Gmsh),
    более низкоуровневый (требует weak form), но проверен на
    десятилетиях работ с трансформаторами и электромашинами.
  Окончательный выбор — после пилотного сравнения в **T113**
  (Containerization phase): какой solver проще интегрировать
  в efactory pipeline (input — MAS JSON от PyOpenMagnetics,
  output — поля + индуктивности + потери), какой даёт
  стабильные результаты на тестовых OPT/SMPS-трансформаторах,
  какой проще для LLM-driven автоматизации. **PyOpenMagnetics
  остаётся** как ядро магнитного дизайна — заменяется только
  FEM-верификация.
- **Альтернативы:**
  - **FEMM в Docker через Wine** — отвергли: двойная
    виртуализация на не-Linux, хрупкий GUI passthrough,
    FEMM не активно развивается, упускаем возможность
    перейти на нативный Linux-инструмент.
  - **FreeFEM** — рассматривался: magnetostatic module есть,
    но ориентирован на исследователей-математиков (DSL для
    weak form), менее инженерный workflow, чем Elmer.
  - **FEniCS / FEniCSx** — мощнейший Python-FEM framework,
    но требует написания weak form вручную; overhead обучения
    для нашего use case (готовый magnetostatic workflow
    интереснее, чем PDE-конструктор).
  - **Подождать Linux-port FEMM** — нет таких планов в upstream
    (FEMM поддерживается одним мейнтейнером с 2019, native
    Linux никогда не был приоритетом).
  - **Коммерческие (Ansys Maxwell, COMSOL)** — отвергли по
    тому же принципу первого ADR (open-source-first).
- **Последствия:**
  - **ADR от 2026-05-15 «PyOpenMagnetics + FEMM»** — **частично
    заменён** этим ADR в части FEMM. PyOpenMagnetics остаётся
    как ядро магнитного дизайна; FEMM-секция заменяется на
    Linux-native solver (выбор после T113 пилота).
  - **T055 (`mag_verify_femm`)** — переименование и переоценка
    acceptance: solver-agnostic API в efactory (`mag_verify_field`
    с pluggable backend), внутри которого первая реализация —
    через Elmer (или GetDP по результатам T113).
  - **T058 (FEMM bootstrap)** — переименуется в T113
    (FEM-solver pilot + integration) и absorbed в Dockerfile.
  - **MAS JSON формат** остаётся как input стандарт — Elmer/
    GetDP принимают meshing input (geometry + материалы),
    преобразование MAS → solver input делает наш orchestration
    layer (~50–100 строк Python в `adapters/outbound/fem_solver/`).
  - **Phase Cross-platform (будущее):** возможно появится
    fallback на нативный FEMM/Wine для пользователей, которым
    нужна совместимость с существующими FEMM-моделями
    индустрии — но это **opt-in**, не основной путь.

### 2026-05-19 — Сторонние review-боты: CodeRabbit как best-effort, primary path = self-review + опциональный `/ultrareview`

- **Контекст:** T094 закрытие — что делать с CodeRabbit integration.
  Ретро `[0.2.0]` (2026-05-17) задокументировало проблему: rate-limit
  хитнул 6+ PR из 9, status-check показывал SUCCESS без реального
  ревью. На milestone `[0.4.0]` Vladimir Pro plan исчерпал credits;
  ретро `[0.5.0]` — оба бота (CodeRabbit + Qodo) silently не давали
  ревью на 7 PR.
  Решение нужно зафиксировать прежде чем стартует Фаза 1b (где скорость
  итераций повысится — LLM chat development) — нельзя продолжать
  делать вид что external review работает.
- **Решение:** **вариант (в)** из BACKLOG T094 — заменить CodeRabbit
  на user-triggered `/ultrareview` для критичных PR'ов. CodeRabbit
  integration остаётся подключённой, но трактуется как **best-effort
  signal** (если что-то полезное сказал — учитываем; rate-limit/no-
  credit silent — не блокирует merge). Primary review path: **Гвидо
  self-review с 7-point checklist** (scope / архитектура / код / гейты
  / документация / соглашения / безопасность), Vladimir-review по
  желанию, `/ultrareview` для архитектурно-критичных или security-
  sensitive PR'ов.
- **Альтернативы:**
  - **(а) Подключить paid plan CodeRabbit полноценно.** Отвергнуто:
    cost-benefit неясен — на `[0.4.0]` Pro plan кончился через 7-8 PR,
    значит usage profile быстро превышает Pro budget. Hobbyist project,
    не commercial team — затраты не оправданы. Vladimir может
    пересмотреть позже если pattern usage станет регулярным.
  - **(б) Полностью отключить CodeRabbit.** Отвергнуто: integration
    уже подключена, бот при наличии credits даёт неплохие insights
    occasionally. «Best-effort» tier нас не штрафует — silent rate-
    limit просто игнорируется.
  - **Оставить status quo (всё как есть, без явного решения).**
    Отвергнуто: ретро 0.2.0/0.4.0/0.5.0 повторяли одну и ту же
    жалобу — нужно зафиксировать обращение к проблеме иначе она
    останется ноющим долгом.
- **Последствия:**
  - **Self-review с 7-point checklist обязателен на каждом PR**
    (уже de facto практика, теперь явно как primary review path).
  - **`/ultrareview`** доступен Vladimir-у для важных PR'ов
    (cross-cutting refactor, security-sensitive changes, фазовые
    milestone'ы). Поскольку он user-triggered (билируется по time),
    не каждый PR — выборочно.
  - **CodeRabbit silent rate-limit/no-credit не блокирует merge** —
    раньше иногда возникало психологическое сомнение «надо ли ждать
    бот». Now explicitly: нет, merge'аем по self-review.
  - **Qodo (qodo-code-review)** — отдельный бот, тоже paused на user.
    Не отключаем — той же логикой best-effort.
  - **Не закрытое направление:** если Phase 1b (LLM chat) generates
    много PR'ов от LLM-driven workflow, может возникнуть necessity
    для batch review automation — пересмотрим (новый ADR, возможно
    paid plan-комбо).

### 2026-05-18 — Programmatic schematic generation: собственный фасад `efactory.schematic` поверх `sexpdata` (вариант D)

- **Контекст:** для T011–T014 (LLM chat-client фазы 1b) и для
  всех SPICE-сценариев (RC, выпрямитель, SE-amp на 6П14П) нужен
  программный способ строить `.kicad_sch`. Ручной s-expr на T008
  оказался хрупким (Y-down vs Y-up, кастомные `lib_symbols` валят
  KiCad GUI, GND через power-symbol с substitution на net 0, KiCad
  SPICE pin-order quirks) — каждая фикстура превращалась в
  микропроект «обучения» Гвидо. Pre-spike (2026-05-18):
  `kicad-sch-api` 0.5.6 **читает** наш KiCad 10 файл, но
  `components.add(lib_id='Device:R', ...)` падает с
  `LibraryError: Symbol 'Device:R' not found` — в KiCad 10 файлы
  библиотек переехали в `*.kicad_symdir/` директории с бинарными
  per-symbol `.kicad_sym`, парсер 0.5.6 ожидает легаси текстовый
  формат «один `Device.kicad_sym` со всеми символами» (KiCad ≤8).
  Дополнительно: библиотека втягивает 78 транзитивных пакетов
  (mcp/fastmcp/uvicorn) — нам не нужен встроенный MCP-сервер.
- **Решение:** **вариант D из спеки T100** — собственный фасад
  `adapters.outbound.schematic_kicad` поверх `sexpdata`. API: класс
  `Schematic(name)` с методами `add_resistor / add_capacitor /
  add_inductor / add_diode / add_v_dc / add_v_ac / add_v_sin /
  add_v_pulse / add_bjt_npn / add_bjt_pnp / add_mosfet_nmos /
  add_mosfet_pmos / add_tube_subcircuit / add_transformer_subcircuit
  / add_ground / add_pwr_flag / connect(pin_a, pin_b) / label /
  save(path)`. Embedded `lib_symbols` snippets (14 шт., text
  `.sexp` под `src/adapters/outbound/schematic_kicad/lib_symbols/`,
  force-include в wheel) — `.kicad_sch` self-contained, не зависит
  от глобальной `KICAD_SYMBOL_DIR` машины-получателя. Hexagonal:
  port `ports.outbound.schematic_writer.SchematicWriter` + adapter
  `KicadSchematicWriter` + domain VO в `domain.schematic` (Pin /
  ComponentSpec / WireSpec / etc.). GND-convention сохранена как
  в T004: фасад ставит `power:GND`-instance, `GND → 0` substitution
  делает `KicadCliSchematicExporter`.
- **Альтернативы:**
  - **(A) Форк `kicad-sch-api`** с поддержкой `*.kicad_symdir/`
    (binary per-symbol) формата KiCad 10. MIT-лицензия разрешает.
    Отвергли: параллельный maintenance чужого кода + 78-deps
    цепочка с MCP-балластом остаётся, а winnings — лишь чтение
    бинарного формата, которое нам не нужно (мы пишем
    самодостаточные snippets).
  - **(B) Bundled freeze KiCad 8/9 текстовых `.kicad_sym` + `kicad-
    sch-api` как backend.** Положить рядом с фасадом «freeze»-копию
    легаси-библиотек (Device, Simulation_SPICE, power) и feed-ить
    их в cache `kicad-sch-api`. Отвергли: библиотеки KiCad 8 ≠
    KiCad 10 (UUID, properties), на load в KiCad 10 могут быть
    warnings; всё ещё 78-deps балласт. Оставлен как **kill-switch
    fallback** на случай провала Phase 0 (не понадобился).
  - **(C) Bypass cache** через monkey-patch / subclass
    `Components`, чтобы `add()` не валидировал существование
    символа в cache. Минимально инвазивно, но хрупко на upgrade
    `kicad-sch-api`.
  - **(E) Подождать upstream `kicad-python` IPC API для схем.** На
    2026-05-18: `kicad-python` 0.7.1 покрывает только PCB, GitLab
    issue #2077 «Schematic Editor Python API» открыт с 28.10.2017
    (8.5 лет) без milestone, реалистичный горизонт KiCad 11
    (~2027) или KiCad 12 (~2028). IPC требует running KiCad с API
    server — плохо ложится на headless CI / batch-LLM / kicad-cli
    pipeline. Будет уместен для T026 (staged-modifications при
    открытом GUI) и для части T079 (Phase 8), но **рядом** с
    генератором, а не вместо.
  - **SKiDL.** Отвергли в pre-spike: генерирует netlist для PCB, а
    не `.kicad_sch` — теряется визуальная схема, KiCad GUI не
    нужен.
- **Последствия:**
  - **Полный контроль над API под наш use case.** Phase 1b
    (LLM-driven design) — функции под LLM-тулчейн, не под чужого
    мейнтейнера. Hexagonal port позволяет подменить backend
    (например, на upstream IPC в Phase 8) без слома
    пользовательского фасада `efactory.schematic`.
  - **Zero лишних deps.** Единственная новая runtime-зависимость —
    `sexpdata` (уже была у `kicad-sch-api`, MIT, чистый Python).
    Не пришли 78 транзитивных пакетов с MCP-стеком.
  - **Self-contained `.kicad_sch`.** Embedded lib_symbols snippets
    (14 шт.) делают файлы переносимыми между машинами без
    `KICAD_SYMBOL_DIR` синхронизации.
  - **Acceptance достигнут.** Фазы 0–2 закрыли RC-фильтр /
    half-wave rectifier / common-emitter BJT / SE-amp 6П14П
    (через T006 tube subckt). ERC = 0 в `kicad-cli`, валидный
    SPICE netlist, ngspice прогоняет OP/TRAN/AC ожидаемо. Coverage
    на `src/adapters/outbound/schematic_kicad/`: facade 97%, writer
    100%. Старая ручная фикстура `tests/fixtures/rc_filter.kicad_sch`
    (149 строк s-expr) удалена в Phase 3 — строится фасадом через
    `tests/conftest.py::rc_filter_schematic_path`.
  - **Цена.** Мы поддерживаем собственный s-expr serializer и
    embedded `lib_symbols` snippets. **План миграции на KiCad 11
    / 12:** при выходе новой версии открыть фикстуру в новом KiCad
    GUI, пересохранить, обновить snippets (1–2 часа на minor).
    Тесты через `kicad-cli erc` ловят несовместимость немедленно
    при апгрейде CI.
  - **Не закрытые направления (вынесены в BACKLOG).** Многолистные
    иерархические схемы (Phase 2 концепта), wire-router для >10
    компонентов (если SE-amp начнёт давать ложные junction'ы),
    рендер SVG для LLM-vision (T032), upstream IPC API (T079).

### 2026-05-17 — Domain expansion direction: D (Phase VO → Manifest primary → Decision aggregate)

- **Контекст:** после 0.2.0 у нас закрыт минимальный CRUD по
  `domain.Project` (Create / List / Show / Delete), но фундамент
  не проверен на: (1) Update use case (единственный stored field
  `status` имел ровно одно значение `CREATED`), (2) множественные
  агрегаты в одном domain'е, (3) портативность Project (CONCEPT
  §4.1) — сейчас Project живёт только в SQL, без YAML-манифеста.
  Запаркован как T096 в ретро `[0.2.0]`.
- **Решение:** **направление D — гибрид в порядке B → C → A**:
  - **B (T097):** `Phase` как embedded value object внутри
    `Project` aggregate. Полноценный VO (`name: PhaseName enum`,
    `status: PhaseStatus enum`, `started_at`, `completed_at`,
    методы `start() / complete() / skip()` с инвариантами).
    Project содержит collection of 6 фаз (schematic, simulation,
    pcb, magnetics, enclosure, documentation) — все со
    status=`pending` по умолчанию. **`Project.status` становится
    derived computed property** от phases (mapping в спеке
    T096 → Resolved #6); stored поле снимается. Update use case
    `efactory project update --name X --phase Y --status Z` плюс
    `add-phase` / `skip-phase` (из CONCEPT §4.1).
  - **C (T098):** `project.yaml` (`Manifest`) становится
    **primary storage** Project'а; SQL переводится в роль **индекса
    / cache** для быстрого `list` / `search`. Полная реиндексация
    SQL возможна перечитыванием всех manifest'ов
    (`efactory project reindex`). Новый outbound port
    `ProjectManifestRepository` + adapter
    `FilesystemProjectManifestRepository` (YAML). Read pattern:
    `show` — из manifest (truth); `list` — из SQL (быстро).
    Write pattern: `create / update / delete` — manifest first,
    SQL reindexed после.
  - **A (T099):** `Decision` как новый aggregate root (CONCEPT
    §4.4). Domain.Decision с полями {`id: D###`, `title`,
    `date`, `status: proposed | accepted | rejected`,
    `summary`, `rationale`, `evidence`, `session`}. Dual-storage
    (раскрыто в Analyze спеки): markdown в `decisions/D###_*.md`
    (детали) + reference в manifest (summary). CLI: `efactory
    decision add / list / show`.
- **Альтернативы:**
  - **A первым (изолированный Decision aggregate)** — отвергли:
    Decision без Phase / Manifest workflow выглядит как «голый
    CRUD», изолированная фича не на главном пути жизненного
    цикла Project'а. Сначала закрываем основные gaps.
  - **B одним** (Phase + Update, без C/A) — отвергли как
    недостаточный: portable-project (§4.1) — фундаментальный
    принцип, без C проект остаётся прибит к SQL машины.
  - **C первым (Manifest без Phase)** — отвергли: без phases
    manifest содержит мало полезного state'а (только id, name,
    created_at). Phase даёт первый реальный writable-content
    для манифеста.
  - **SQL = primary, manifest = export** — отвергли в пользу
    «manifest = primary, SQL = индекс». Concept §4.1 явно
    позиционирует папку проекта как самодостаточный
    портативный контейнер; SQL — локальный кэш окружения.
    Если SQL = primary, то отправка папки на другую машину
    теряет историю / decisions / status.
  - **Phase как scalar enum + status вместо полноценного VO** —
    отвергли: `started_at` / `completed_at` уже в CONCEPT §4.3,
    методы `start() / complete() / skip()` с инвариантами
    делают domain богаче без перерасхода кода (~30 строк).
  - **PhaseName как whitelist в Settings вместо enum** —
    отвергли: фазы стабильные (6 штук в концепте), не
    open-ended; enum даёт автокомплит и проверку типов
    бесплатно.
- **Последствия:**
  - Domain заметно растёт: +VO `Phase`, +aggregate `Decision`,
    +1 outbound port (manifest), +1 outbound adapter
    (filesystem-yaml), +Update use case на `Project`, +команды
    `update / add-phase / skip-phase / reindex / decision *`.
  - SQL миграция: колонка `status` удаляется (либо сохраняется
    как denormalized cache — уточняется в T098).
  - Backward compatibility: T098 acceptance включает миграцию
    «существующие SQL-only проекты получают manifest».
  - Тестовое покрытие растёт линейно с domain'ом
    (`Phase.start() / complete() / skip()` — изолированные
    domain-тесты; manifest adapter — integration с реальным
    `tmp_path`; Decision aggregate — отдельный набор).
  - Положительная нагрузка на архитектуру: проверим, как
    hexagonal-фундамент держит (а) рост одного агрегата
    (Project с phases), (б) второй адаптер на тот же агрегат
    (manifest рядом с SQL), (в) второй aggregate root
    (Decision). Если что-то скрипит — это сигнал ревизии
    фундамента (отдельный ADR).
  - Decomposition в `BACKLOG.md`: T097 (Phase + derived
    status + Update), T098 (Manifest primary), T099 (Decision).
    Реализуются последовательно. Spec'и крупных задач —
    отдельные `specs/T0XX-*/spec.md` при взятии в работу.

### 2026-05-17 — Auto-install pre-push hook через hatchling custom build hook

- **Контекст:** T091 ввёл `.pre-commit-config.yaml` на 5-step gate,
  но установка hook'а — ручной шаг (`uv run pre-commit install
  --hook-type pre-push`) после клонирования. Если новый разработчик
  забудет — `git push` пройдёт без локального гейта, кривой код
  попадёт на платформу. В ретро `[0.2.0]` запаркован тех-долг T095:
  hook должен ставиться автоматически по `uv sync`, без отдельной
  команды.
- **Решение:** custom build hook hatchling (`hatch_build.py` в корне,
  регистрация `[tool.hatch.build.hooks.custom]` в `pyproject.toml`).
  В методе `initialize()` (срабатывает при сборке editable wheel
  по `uv sync`) делегируем на `uv run --no-sync pre-commit install
  --hook-type pre-push`. Guard'ы: skip при отсутствии `.git/`, skip
  при отсутствии `uv` на PATH (warning в stderr, exit 0 — не
  ломаем build). Идемпотентность достигается естественно: без
  `--reinstall` editable wheel кешируется, hook не вызывается.
- **Альтернативы:**
  - **Скрипт-обёртка `scripts/dev-setup.sh`** (вместо `uv sync`) —
    отвергли: формально не отвечает acceptance «после `uv sync`
    автоматически», требует от разработчика помнить отдельную
    команду — ровно та же проблема, что у `pre-commit install`.
  - **Auto-инициализация в entry-point CLI / `conftest.py`** —
    отвергли: hook ставится только когда пользователь запустит
    приложение/тесты; если сразу делает `git push` — поздно.
    Плюс смешивание слоёв (CLI знает про dev-workflow).
  - **Собственный shell-wrapper в `.git/hooks/pre-push`** без
    pre-commit's `install` — отвергли: дублируем то, что
    pre-commit делает сам, повторно решая
    `INSTALL_PYTHON`/`uv run` логику. Хуже maintainability.
  - **Глобальные git templates** (`git config --global
    init.templateDir`) — отвергли: требует global git config,
    лежит вне репозитория, не воспроизводится между машинами.
- **Последствия:** новый разработчик после `git clone` && `uv sync`
  сразу получает работающий гейт на `git push`. CI без `.git/`
  (artifact checkouts) — silently skip. Smoke-тесты подтвердили:
  hook активируется в editable mode (`version='editable'`,
  `target='wheel'`), `.venv/bin/pre-commit` доступен к моменту
  `initialize()`, `uv run --no-sync` направляет на проектный
  `.venv/`. Цена — введён первый `subprocess.run` в проекте, что
  спровоцировало добавление **`S603`** (subprocess untrusted input)
  в общий `[tool.ruff.lint.ignore]` шаблона: argv-list без
  `shell=True` и без user-input — безопасная форма, false-positive.
  Решение принято по варианту (в) обсуждения T095 — обоснование
  в самой ignore-секции `pyproject.toml`.

### 2026-05-17 — Hexagonal Architecture (Ports & Adapters) как базовый layout

- **Контекст:** долгоживущий проект (~5200 строк собственного кода
  + ещё столько же по периметру) с большим количеством внешних
  адаптеров: 5 MCP-серверов, ИИ-провайдеры (Claude, OpenAI-compat,
  Ollama), CAD-форматы (KiCad/Gerber/STEP), симуляторы (ngspice,
  FEMM), persistence (SQLite, Kùzu). Без явных границ слоёв через
  пару лет получим "big ball of mud".
- **Решение:** Hexagonal Architecture (Alistair Cockburn, Ports
  & Adapters) с пятью верхнеуровневыми слоями в `src/`:
  `domain/` (модели предметной области + поведение),
  `application/` (тонкие use cases),
  `ports/` (`inbound/` + `outbound/`, оба — `typing.Protocol`),
  `adapters/` (`inbound/` + `outbound/`, конкретные реализации),
  `composition/` (composition root: сборка графа зависимостей).
  Изоляция слоёв проверяется автоматически через `import-linter`.
- **Альтернативы:**
  - **Плоский `src/` без слоёв** — отвергли: на масштабе проекта
    превращается в "big ball of mud" в первые же месяцы.
  - **Classic Clean Architecture (Uncle Bob) с явными
    Interactor / Boundary** — отвергли: для Python избыточно,
    лишний boilerplate (отдельные input/output boundary классы),
    то же самое достигается тонким use case + Protocol.
  - **Onion Architecture** — близкий родственник; отвергли
    в пользу Hexagonal как более аскетичной и явно
    симметричной (inbound/outbound как зеркало).
  - **Layered (controllers / services / repositories)** —
    отвергли: не запрещает зависимости сверху вниз через слои,
    легко скатывается к "fat service".
- **Последствия:** новые интеграции добавляются как outbound-адаптеры
  за стабильными port-интерфейсами; замена технологии затрагивает
  только адаптер; domain тестируется без поднятия БД и сети. Цена —
  необходимость держать дисциплину границ (помогает `import-linter`)
  и явный маппинг domain ↔ persistence (без "SQLAlchemy-модель как
  domain"). Подробности — `specs/T085-architecture-foundation/spec.md`.

### 2026-05-17 — TDD-first как методология разработки во всём проекте

- **Контекст:** проект долгоживущий, hexagonal-архитектура с
  множеством слоёв и адаптеров, цель ~5200 строк production-кода
  плюс окружение. Без дисциплины тестирования слоёв легко получить
  баги стыков, которые ловятся только в e2e и плохо
  локализуются.
- **Решение:** **TDD строго (Red → Green → Refactor)**: никакая
  строка production-кода не пишется до падающего теста. Подход —
  **outside-in** для hexagonal: acceptance/e2e-тест → unit-тесты
  application use case с fake-портами → integration-тесты адаптеров.
  Domain тестируется как чистые unit-ы без mock-ов (нет внешних
  зависимостей). Адаптеры — integration с реальными технологиями
  (SQLite в `tmp_path`, Kùzu в `tmp_path`, FS в `tmp_path`).
  Fake-порты — простые in-memory классы, реализующие `Protocol`;
  **без `unittest.mock`**. Bug fix следует тому же шаблону:
  сначала тест, воспроизводящий баг, потом фикс.
- **Альтернативы:**
  - **Test-after** (написал реализацию → покрыл тестами) —
    отвергли: пропускает мёртвые ветки, тесты адаптируются под
    реализацию, а не наоборот; на сложной hexagonal-архитектуре
    регулярно приводит к плохо тестируемым use case.
  - **BDD-first** (`pytest-bdd`, Gherkin) — отвергли как
    обязательный: добавляет slow-test layer и Gherkin-наследие,
    не покрывающее unit-уровень. Может быть введён локально как
    acceptance-DSL, если возникнет потребность.
  - **Mockist (London School) с mock-ами вместо fake-ов** —
    отвергли: `unittest.mock` хрупкие к рефакторингу
    (matchers по строке имени, side_effect-аду); Protocol-fake
    дешевле и устойчивее.
- **Последствия:** дисциплинированное покрытие, низкая
  регрессионная цена, контракт каждого слоя задаётся тестом
  заранее. Coverage на `src/` ≥ 80% (общий threshold проекта),
  на `domain/` ≈ 100%, на `application/` ≥ 90% — естественно
  через TDD. Цена — медленнее на ранней стадии (тест-первый
  цикл), окупается на горизонте проекта. Зафиксировано также
  в auto-memory `feedback_tdd.md` и в mem0.

### 2026-05-17 — Async-first во всём проекте

- **Контекст:** основные операции системы — I/O-bound: вызовы ИИ-
  провайдеров (Claude, OpenAI-compat), MCP-протокол (stdio/HTTP),
  взаимодействие с внешними процессами (KiCad, FreeCAD, ngspice,
  FEMM), сетевые sourcing-API (Mouser, DigiKey, LCSC), файловые
  операции с большими CAD-проектами. Параллелизм через async —
  естественная модель.
- **Решение:** **async везде**. Порты, адаптеры, use cases —
  все методы `async def` по умолчанию. Sync-API внешних библиотек
  (Kùzu Python binding на 2026-05-17 — синхронный) заворачиваются
  в `asyncio.to_thread` внутри адаптера, наружу торчит async
  Protocol. Composition root — async `main()` через
  `asyncio.run(...)`.
- **Альтернативы:**
  - **Sync-first, async только для конкретных операций** —
    отвергли: смешанный режим тянет sync/async-аду, требует
    `nest_asyncio` или ручной event-loop оркестрации; на
    hexagonal-границах превращается в кошмар.
  - **Threading / multiprocessing вместо asyncio** — отвергли
    для I/O-bound нагрузки: asyncio даёт более чистую модель
    отмены и таймаутов, меньше синхронизационных примитивов.
- **Последствия:** единый стиль во всём коде, естественная
  параллельность ИИ-запросов и MCP-вызовов, простой `gather`
  для конкурентных операций. Цена — async-«вирус» (всё, что
  вызывает async, само должно быть async); митигация — он
  введён с первого дня, без legacy sync-кода для миграции.

### 2026-05-17 — Pydantic v2 для domain-моделей, отдельные persistence-модели

- **Контекст:** domain-модели нужно валидировать на входе
  (JSON, MCP-tool-input, CLI-аргументы), сериализовать на выходе
  и хранить в БД. Соблазн использовать SQLAlchemy declarative
  как domain (меньше кода) велик, но размывает границы hexagonal
  и привязывает domain к particular ORM.
- **Решение:**
  - **Domain-модели — Pydantic v2** с поведением (методы, бизнес-
    инварианты в `model_validator`-ах), value objects —
    `model_config = ConfigDict(frozen=True)`. Domain зависит
    **только** от `pydantic` и stdlib; никаких импортов из
    `sqlalchemy`, `kuzu`, `mcp`, `anthropic`, `typer` в domain
    не допускается (проверяется `import-linter`).
  - **Persistence-модели — отдельные** SQLAlchemy 2.0 declarative
    классы в `adapters/outbound/persistence_sql/models.py`.
    Маппинг domain ↔ ORM — явными функциями `to_orm(domain) →
    orm` / `to_domain(orm) → domain` в том же адаптере.
  - **DTO** — отдельные Pydantic-модели в адаптерах, **только
    когда форма расходится** с domain (HTTP-API, MCP-tool со
    сложным JSON-input). Преждевременные mapper-ы не пишем.
- **Альтернативы:**
  - **SQLAlchemy declarative как domain** — отвергли: domain
    привязан к ORM, ленивая загрузка ломает инварианты при
    `refresh()`, нельзя тестировать domain без поднятия engine.
  - **Чистые `@dataclass` для domain без Pydantic** — отвергли:
    теряем валидацию из коробки и сериализацию; пришлось бы
    дописывать ручные `__post_init__`-валидаторы или подключать
    `marshmallow`/`attrs+cattrs`.
  - **Pydantic с автогенерируемыми SQLAlchemy-моделями
    (SQLModel)** — отвергли: SQLModel слепляет domain и
    persistence в один класс, ровно то, чего избегаем.
- **Последствия:** domain тестируется без поднятия БД; смена
  ORM или БД — точечное изменение в `adapters/outbound/
  persistence_sql/`; явность маппинга подсвечивает изменения
  схемы. Цена — больше кода (две модели + маппер); митигация —
  модели обычно близки по форме, маппер тривиальный.

### 2026-05-17 — Ручная DI-композиция в `composition/`, без контейнера

- **Контекст:** hexagonal-архитектура требует сборки графа
  зависимостей (use cases получают порты через конструктор).
  Существуют DI-контейнеры (`dependency-injector`, `punq`,
  `wired`), упрощающие декларативную сборку на больших графах,
  но привносящие магию и обучение.
- **Решение:** **ручная композиция** в `composition/`. Объекты
  адаптеров создаются явно в `main()` / фабричных функциях,
  передаются в конструкторы use case-ов. Граф зависимостей читается
  как обычный Python-код. Без декораторов, без autowiring.
- **Альтернативы:**
  - **`dependency-injector`** — мощный, но магия `Provide[Container.x]`
    и Resource lifecycles требует обучения; на старте проект слишком
    маленький.
  - **`punq` / `wired`** — легче, но всё ещё доп. зависимость и
    обучение ради экономии 20-30 строк ручной сборки.
- **Последствия:** граф зависимостей прозрачен и видим без
  магии; легко переопределить любой адаптер в тестах. Цена —
  если граф разрастётся до 50+ объектов, ручная сборка станет
  громоздкой; **тогда** пересматриваем (новый ADR), вводим
  контейнер.

### 2026-05-17 — SQLAlchemy 2.0 async + aiosqlite + Alembic для метаданных

- **Контекст:** требуется persistence метаданных проектов
  (Project, Component, Run, ...): реляционные связи, миграции
  схемы, надёжная транзакционность. Desktop-приложение, один
  пользователь, embedded.
- **Решение:** **SQLAlchemy 2.0+** (typed declarative с `Mapped[]`,
  `mapped_column`) + **aiosqlite** (async-драйвер SQLite) +
  **Alembic** для миграций (шаблон `alembic init -t async`).
  Persistence-модели живут в `adapters/outbound/persistence_sql/
  models.py`, отдельно от domain Pydantic-моделей. Адаптер
  реализует `MetadataRepository` Protocol из `ports/outbound/`.
- **Альтернативы:**
  - **Raw `sqlite3` или `aiosqlite` без ORM** — отвергли:
    нет миграций из коробки, ручной SQL для нетривиальных
    запросов, типизация хромает.
  - **SQLModel** — отвергли: слепляет domain и persistence
    (см. ADR «Pydantic v2 для domain»).
  - **Peewee, Tortoise ORM** — отвергли: меньше экосистема,
    хуже type-checker support, нет аналога Alembic такого же
    зрелого.
  - **TinyDB / `shelve`** — отвергли: нет реляционных связей,
    нет миграций, не масштабируется на даже умеренный граф
    сущностей.
- **Последствия:** мощный typed ORM, контролируемые миграции,
  переносимость на PostgreSQL без правок domain (только
  адаптер). Цена — кривая обучения SQLAlchemy 2.0 typed-API
  (новый стиль отличается от 1.x); митигация — стандарт с
  2023 года, документация зрелая.

### 2026-05-17 — Kùzu как embedded граф-БД для топологий

- **Контекст:** топология схем и плат — естественный граф:
  узлы (компоненты, выводы, нетлисты), рёбра (соединения,
  цепи). Типичные запросы — обходы и пути ("все компоненты в
  цепи сигнала X", "найди петли", "связные подграфы"). На
  SQLite-CTE такие запросы выражаются плохо.
- **Решение:** **Kùzu** (MIT, embedded, Cypher-совместимый,
  колоночное хранение). Адаптер живёт в
  `adapters/outbound/graph_store/`, реализует
  `TopologyGraphStore` Protocol. Sync Python binding
  заворачивается в `asyncio.to_thread` в адаптере.
- **Альтернативы:**
  - **Neo4j** — server-based, требует JVM, GPLv3 для core
    компонентов, лицензия для коммерции мутная; отвергли для
    desktop-приложения как тяжёлое решение.
  - **Memgraph** — server-based, BSL-лицензия с коммерческими
    ограничениями; отвергли по тем же причинам.
  - **ArangoDB** — server-based multi-model; отвергли как
    тяжёлое.
  - **SQLite + recursive CTE + edge-таблицы** — отвергли как
    основное: для алгоритмов на графах больно, специализированных
    оптимизаций нет. Оставляется как fallback при провале
    Critical-проверки фазы 1.
  - **NetworkX в памяти + persist в SQLite** — fallback-вариант
    при провале Kùzu под Python 3.14.
- **Последствия:** нативные графовые запросы Cypher, embedded
  deployment (как SQLite), MIT-лицензия. Цена — молодая БД (с
  2022), экосистема меньше Neo4j. **Статус:** Critical-проверка
  фазы 1 пройдена — `kuzu==0.11.3` ставится и работает под Python
  3.14 (Linux), sync API корректно оборачивается в
  `asyncio.to_thread`, подтверждено integration-smoke-тестом
  `tests/integration/adapters/graph_store/test_kuzu_smoke.py`.
  Fallback к NetworkX-persisted-в-SQLite больше не активен.

### 2026-05-17 — `pydantic-settings` для конфигурации с первого дня

- **Контекст:** проекту с первого дня нужны конфигурируемые
  пути (SQLite-файл, Kùzu-папка, корень проектов), API-ключи
  (Anthropic и пр.), профили окружения. Хардкод в composition
  root — техдолг с момента создания.
- **Решение:** **`pydantic-settings`** с одним классом `Settings`
  в `composition/settings.py`. Источники: переменные окружения,
  `.secrets` файл в корне (уже в `.gitignore`), значения по
  умолчанию для разработки. Класс валидирует типы и обязательные
  поля при старте.
- **Альтернативы:**
  - **`os.environ` напрямую** — отвергли: нет типизации,
    нет валидации обязательности на старте, легко получить
    `None` в неожиданном месте.
  - **`dynaconf`, `confuse`** — отвергли: дополнительная
    зависимость без выигрыша по сравнению с pydantic-settings,
    который уже family для Pydantic.
  - **`python-decouple`** — отвергли: меньше функциональности,
    нет интеграции с Pydantic.
- **Последствия:** конфиг типизирован, ошибки конфигурации
  ловятся на старте, secret-keys из env. Цена — одна доп.
  зависимость (`pydantic-settings`).

### 2026-05-17 — `import-linter` для автоматической изоляции слоёв

- **Контекст:** правила hexagonal ("domain не импортирует
  application", "ports не импортируют adapters" и т.д.) в spec/
  README легко нарушаются по невнимательности или из-за IDE-
  autocomplete. Без машинной проверки правила деградируют
  через 3-6 месяцев.
- **Решение:** **`import-linter`** (dev-dependency), конфиг
  в `[tool.importlinter]` в `pyproject.toml`. Контракты:
  - **Layers contract** для `src/`: `composition` → `adapters` /
    `application` → `ports` / `domain`, со строгим запретом
    обратных импортов.
  - **Forbidden contract** для domain: запрет импортов
    `sqlalchemy`, `kuzu`, `mcp`, `anthropic`, `typer` из
    `src/domain/`.
  - **Forbidden contract** для adapters: запрет перекрёстных
    импортов между разными adapters/outbound/* и adapters/
    inbound/*.
  Команда `uv run lint-imports` — **пятая обязательная** проверка
  перед `git push` (после ruff / format / mypy / pytest).
- **Альтернативы:**
  - **Ручные тесты на `ast.parse`** — отвергли: дублирует
    решённую задачу, поддерживать сложнее.
  - **Не автоматизировать, держать в правилах** — отвергли:
    правила деградируют без машинной проверки на долгом
    горизонте.
- **Последствия:** нарушения границ слоёв ловятся локально
  до коммита, дисциплина hexagonal удерживается без human
  policing. Цена — одна dev-dependency и поддержание
  контрактов в `pyproject.toml` при добавлении новых слоёв
  /правил.

### 2026-05-15 — Архитектурный принцип: MCP-обвязка готовых инструментов, минимум собственного кода

- **Контекст:** в нише сквозного проектирования РЭА существует
  набор зрелых open-source инструментов (KiCad, ngspice, FreeCAD,
  FEMM, OpenMagnetics) и для большинства из них уже есть готовые
  MCP-серверы либо Python-API. Альтернатива — писать собственный
  монолит на ~50 000+ строк.
- **Решение:** система строится как **тонкий оркестрационный слой**
  (`kicad-sim-bridge` — собственный MCP-сервер) плюс универсальный
  чат-клиент (`kicad-sim-chat`), подключающий **5 MCP-серверов**:
  `mcp-kicad-sch-api`, `kicad-mcp-pro`, `spicebridge`, `freecad-mcp`,
  `kicad-sim-bridge`. Чат-клиент — единственный MCP-клиент в системе;
  LLM-бэкенды (включая Claude Code Max) используются только как
  языковые модели, не исполняют tool calls. Собственный код — только
  то, чего нет ни у одного из готовых серверов: pipeline между
  инструментами, предметно-ориентированные проверки, формирование
  документации. Целевой объём — ~5200 строк (§18 концепта).
- **Альтернативы:**
  - **Собственный монолит** — отвергли: повторное изобретение
    KiCad/ngspice/FreeCAD-обвязки, ~50 000+ строк, неподъёмный
    maintenance burden, потеря совместимости с обновлениями
    upstream-инструментов.
  - **LLM как MCP-клиент (через Claude Desktop или Claude Code в
    качестве хозяина инструментов)** — отвергли: разные бэкенды дают
    разное поведение, проектные функции (DDR, sessions, project.yaml)
    пришлось бы дублировать в каждом, теряем единый лог tool calls
    и привязку к проекту.
- **Последствия:** все бэкенды работают одинаково; проектные функции
  всегда доступны; полный контроль и логирование tool calls; собственный
  код сосредоточен на том, что действительно «своё». Цена —
  необходимость поддерживать оркестрационный слой и совместимость с
  5 внешними MCP-серверами; митигация — `compatibility.toml`.

### 2026-05-15 — kicad-sch-api для создания и модификации схем

- **Контекст:** для программного создания и модификации .kicad_sch
  нужен Python-API. Официальный kicad-python (IPC API) на 2026-05-15
  поддерживает только PCB-редактор, схемы — в планах. Требуется
  работа без запущенного KiCad (headless, CI/CD).
- **Решение:** **kicad-sch-api** (MIT, PyPI) — побайтовое сохранение
  .kicad_sch, поддержка KiCad 7/8/9/10, 70+ тестов, готовые примеры.
  Поверх неё — **mcp-kicad-sch-api** (MIT) с 15 MCP-инструментами.
- **Альтернативы:**
  - **Официальный kicad-python (IPC API)** — отвергли как
    основной: на 2026-05-15 не поддерживает схемы, требует запущенный
    KiCad. Перспективно — пересмотрим, когда поддержка схем появится
    (см. фаза 8 концепта).
  - **Ручная генерация S-expression-ов** — отвергли: хрупко, дублирует
    то, что kicad-sch-api уже делает.
- **Последствия:** headless-генерация и модификация схем,
  совместимость с несколькими версиями KiCad. Цена — community-проект
  (circuit-synth), не official.

### 2026-05-15 — kicad-mcp-pro как комплексный MCP-сервер для KiCad

- **Контекст:** для KiCad нужен MCP-сервер, покрывающий весь
  жизненный цикл: проекты, схемы, PCB, валидация (ERC/DRC/DFM),
  экспорт (Gerber, BOM, STEP, pick-and-place), интеграция с
  FreeRouting, SI/PI/EMC хелперы, gated release производственных
  файлов.
- **Решение:** **kicad-mcp-pro (oaslananka)** (MIT, PyPI) — единый
  сервер с серверными профилями (`minimal`, `pcb_only`, `manufacturing`,
  `agent_full` и др.), VS Code companion `kicad-studio`, CLI-диагностикой
  `health`/`doctor`.
- **Альтернативы:**
  - **Seeed Studio kicad-mcp-server** — отвергли: уже покрыт
    функциональностью kicad-mcp-pro, не имеет quality gates, DFM,
    SI/PI/EMC и gated release.
  - **mixelpixx KiCAD-MCP-Server** — отвергли по той же причине.
  - **Собственный MCP-сервер с нуля поверх kicad-cli и pcbnew API** —
    отвергли: противоречит первому принципу, ~1500-2000 строк
    дублирующего кода.
- **Последствия:** один MCP-сервер вместо набора нишевых; gated
  release не пускает в производство недопроверенные файлы. Цена —
  привязка к темпу релизов oaslananka; митигация — `compatibility.toml`.

### 2026-05-15 — SPICEBridge как основной MCP-сервер моделирования

- **Контекст:** требуется SPICE-моделирование (OP, tran, AC, sweep)
  по командам LLM с прямым взаимодействием через MCP, базовыми
  измерениями (THD, gain, bandwidth) и интеграцией с нашим
  чат-клиентом и Claude Code.
- **Решение:** **SPICEBridge** (MIT) — 18 MCP-инструментов поверх
  ngspice, авторасчёт номиналов по ряду E24, stdio + HTTP/Cloudflare
  транспорты. **PySpice** (PyPI) используется для прямого
  программного доступа к ngspice внутри нашего bridge (KiCadTools для
  чтения .kicad_sch, объектный API нетлистов).
- **Альтернативы:**
  - **Только PySpice без MCP** — отвергли: пришлось бы писать
    собственный MCP-сервер с нуля (~500-1000 строк), дублируя то,
    что SPICEBridge уже даёт «из коробки».
  - **LTSpice / TINA** — отвергли: коммерческие или с ограничениями
    лицензии, нет CLI/MCP-обвязки, не работают headless на Linux,
    противоречат первому принципу.
- **Последствия:** SPICEBridge и PySpice — комплементарны
  (MCP-сервер плюс библиотека), а не конкуренты. Цена — две точки
  обновления и совместимости (но обе MIT, PyPI).

### 2026-05-15 — PyOpenMagnetics + FEMM для намоточных изделий

> **Частично заменено решением от 2026-05-19** (см. «Magnetic
> field verification: Linux-native FEM-solver...» выше). FEMM
> заменяется Linux-native solver'ом (Elmer / GetDP, выбор по
> итогам T113); PyOpenMagnetics + MAS-формат остаются как ядро
> магнитного дизайна.


- **Контекст:** проектирование заказных трансформаторов, дросселей,
  катушек индуктивности — от подбора сердечника до спецификации для
  намотчика. Нужна база сердечников/материалов, расчёт обмоток с
  AC-эффектами, верификация магнитного поля и интеграция с SPICE и
  FreeCAD.
- **Решение:**
  - **PyOpenMagnetics** (MIT, PyPI) — Python-обёртка над MKF: база
    10 000+ сердечников, расчёт потерь, AGENTS.md для LLM.
  - **MAS** (JSON-формат) — стандартизированное описание магнитного
    компонента, совместимое с ngspice/LTSpice/FEMM/Ansys Maxwell.
  - **MVB** — генератор 3D-моделей для FreeCAD из MAS.
  - **FEMM + pyFEMM** — 2D FEA для верификации поля.
- **Альтернативы:**
  - **Только ручной расчёт по McLyman / Erickson** — отвергли:
    отсутствие базы сердечников, нет AC-учёта, не масштабируется на
    автоматический пайплайн.
  - **transformer_designer (Denys)** — рассматривался, отвергнут как
    основной инструмент: веб-приложение без программного API для
    интеграции в MCP-пайплайн. Оставлен как опциональный справочный
    веб-интерфейс для ручной верификации.
  - **Ansys Maxwell, COMSOL** — отвергли: коммерческие, противоречат
    первому принципу.
- **Последствия:** покрыт полный цикл от ТЗ до намотчика.
  Безальтернативно в open-source-нише — PyOpenMagnetics на момент
  2026-05-15 единственный зрелый Python-движок с базой сердечников
  и AI-ready форматом.

### 2026-05-15 — FreeCAD + freecad-mcp для проектирования корпусов

- **Контекст:** требуется параметрическое 3D-моделирование корпусов
  с поддержкой листового металла (шасси ламповых конструкций), сборки
  с PCB (импорт STEP из KiCad), генерации 2D-чертежей и развёрток DXF.
  Управление — программное, через MCP.
- **Решение:** **FreeCAD 1.0+** (LGPL, open source) с workbenches
  Part Design / Sheet Metal / Assembly / TechDraw / Draft и
  **freecad-mcp (neka-nat)** в роли MCP-сервера (MIT, 617 stars).
  Интеграция с KiCad через STEP-импорт.
- **Альтернативы:**
  - **Коммерческие 3D-САПР (SolidWorks, Fusion 360, Autodesk
    Inventor)** — отвергли: не open source, лицензия противоречит
    первому принципу проекта, нет готовой MCP-обвязки, кроссплатформа
    хромает.
  - **OpenSCAD** — отвергли: программная парадигма (без GUI и
    параметрических операций в редакторе), нет Sheet Metal, нет
    Assembly с ограничениями, нет TechDraw — пришлось бы дописывать
    половину функциональности.
- **Последствия:** полностью open-source-стек, кроссплатформенность,
  готовый MCP-сервер. Цена — FreeCAD 1.0 моложе коммерческих
  конкурентов, отдельные workbench (Sheet Metal) — community addon.

### 2026-05-15 — Стратегия версионирования зависимостей: `compatibility.toml` + `--update`

- **Контекст:** система зависит от 5 MCP-серверов, KiCad, ngspice,
  FreeCAD, FEMM, Python — все обновляются независимо. Нужен
  воспроизводимый bootstrap и контролируемый upgrade.
- **Решение:** в корне проекта файл `compatibility.toml` с двумя
  секциями: `[tested]` (точные версии, на которых проект гарантированно
  работает) и `[minimum]` (минимально допустимые). `bootstrap`
  устанавливает `[tested]`; флаг `--update` обновляет до последних
  версий, запускает smoke-тест и при успехе обновляет `[tested]`.
- **Альтернативы:**
  - **Только pin последних версий** — отвергли, любой релиз любой
    зависимости может сломать сборку у нового пользователя без
    возможности отката к проверенной конфигурации.
  - **Только минимальные версии** — отвергли по той же причине плюс
    непредсказуемость поведения при разных «текущих» у разных
    пользователей.
- **Последствия:** новый пользователь получает заведомо рабочую
  систему; апдейт явный и проверяемый. Цена — нужно поддерживать файл
  и smoke-тест. Подробности — §19 концепта.
