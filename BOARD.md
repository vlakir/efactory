# Board

Лёгкая Kanban-альтернатива на одном markdown-файле: три колонки
(To Do / Doing / Done) под git, без внешних сервисов и инструментов.

## Соотношение с другими файлами

- `BACKLOG.md` — длинная очередь идей и побочных находок. Сюда падает
  «потом подумаем», «не сейчас». Парковка scope.
- `BOARD.md` (этот файл) — активный рабочий поток. Задачи, которые мы
  уже взяли или собираемся брать в ближайшее время.
- `specs/T<NNN>-*/spec.md` — куда вырастает крупная задача из BOARD, если
  она оказывается фичей >1 дня работы.

Жизненный цикл задачи: идея в `BACKLOG.md` → созрела → переезжает в
`To Do` здесь → берётся в работу (`Doing`) → закрывается (`Done`) →
после релиза переходит в `CHANGELOG.md` (запись обязательно содержит
T-ID), отсюда удаляется. **`CHANGELOG.md` — единственное persistent-
хранилище T-ID завершённых задач**, без него правило «ID не
переиспользуется» сломается.

## Формат задачи

Каждая задача — `- **T<NNN>** — <короткое описание>`. ID присваивается
при создании: новый = `max(существующих T-ID в BOARD.md, BACKLOG.md и
CHANGELOG.md) + 1`. ID никогда не переиспользуется. ID общий для
`BOARD.md` и `BACKLOG.md` — при перетекании задачи между ними
сохраняется; после релиза задача попадает в `CHANGELOG.md` с тем же
T-ID, что гарантирует уникальность номеров между релизами.

Имя ветки: `T<NNN>-<slug>` (без namespace типа `fixes/` / `feature/` —
ID уже даёт идентификацию). Имя PR: `T<NNN>: <title>`. Спецификация
крупной фичи: `specs/T<NNN>-<slug>/spec.md`.

По вкусу можно добавлять:

- метку даты взятия,
- ссылку на спеку,
- имя ветки.

Пример:

```
- **T<NNN>** — Превью постов в Telegram
  (`specs/T<NNN>-telegram-preview/`, ветка `T<NNN>-telegram-preview`).
```

---

## To Do

<!-- Готово к взятию. Очередь FIFO по умолчанию, можно поднимать
     приоритетное наверх. -->

<!-- Записи задач в формате `- **T<NNN>** — описание`. См. раздел
     «Формат задачи» выше. -->

## Doing

<!-- В работе прямо сейчас. Держим короткой: максимум 1-2 задачи на
     разработчика, иначе теряется фокус (классическое WIP-limit
     правило из Kanban). -->

(пусто)

## Done

- **T169** — [closed 2026-06-02, PR #110] **Env-sanitize git
  subprocess в тестах** (`tests/integration/adapters/git_subprocess/
  test_git_repository.py`). Helper `_git_capture` pop'ит
  `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` из env перед
  verification `subprocess.run(['git', '-C', cwd, ...])` —
  соответствует production `_build_env()` в
  `SubprocessGitRepository`. Иначе под `git push` из worktree
  (Claude Code worktree-isolated subagent) raw subprocess.run
  наследует `GIT_DIR=<worktree-gitdir>` из pre-push hook и читает
  parent repo вместо tmp_path init → assertion fail. 3 verification
  вызова переведены на helper + regression test
  `test_init_works_when_caller_has_git_dir_set` (simulate'нет
  leakage через monkeypatch). Обнаружено T168 subagent (workaround
  push из main repo). Pre-push 5/5 ✓ (1744 passed @ 86.19%, +1 vs
  T168 baseline).

- **T168** — [closed 2026-06-02, PR #109] **Wire
  `convert_pwrs_to_ngspice` в production pipeline
  `spice_library.read_subckt`.** Универсальное применение PWRS-конвертера
  (для любого source, idempotent) — defense-in-depth для transparent
  loading 3rd-party tube models с HSPICE PWRS-syntax без manual data
  file patches. AYUMI `^ → **` остаётся conditional. Module docstring
  обновлён. +1 unit test (`test_read_subckt_pwrs_converted_universally`)
  для CUSTOM-source модели с PWRS. Pre-push 5/5 ✓ (1743 passed @ 86.19%,
  +1 vs T167 baseline).

- **T167** — [closed 2026-06-02, PR #108] **Patch 8 Ayumi tube model
  files к ngspice syntax** (`211`, `2A3`, `300B`, `6080`, `6C33C`,
  `6V6_AYUMI`, `845`, `GENERIC_PENTODE`). Conversion `^` → `**` +
  `PWRS(x,y)` → `sgn(x)*pwr(abs(x), y)` через существующие
  `convert_ayumi_to_ngspice` + `convert_pwrs_to_ngspice` (same pattern
  что T166 для 6DJ8/6922). Unified ngspice-syntax marker в docstrings
  всех 10 ayumi/*.inc файлов (idempotent — без `^` / `PWRS(` в
  комментариях). Sanity `ngspice -b` на 2A3 SE-amp passed (V_plate
  274V, I_a 5mA). Regression test `test_ayumi_models_patched.py` (20
  cases × 10 files): pre-conversion + idempotency. Pre-push 5/5 ✓
  (1742 passed @ 86.15%, +20 vs T027 baseline).

- **T027** — [closed 2026-06-02, PRs #102/103/104/106/107] **Расширение
  каталога project templates: PP amp, line preamp, phono RIAA preamp,
  active LPF + slash+CLI extension.** 4 новых template (`tube-pp-amp`,
  `tube-line-preamp`, `tube-phono-riaa`, `active-lpf-sallen-key`) +
  `/project-create <NAME> [TEMPLATE]` slash command extension
  (default `se-amp` для back-compat) + `efactory project list-templates`
  CLI subcommand (human-readable table + `--json` flag, data-driven из
  `data/templates/*/template.yaml`). 4 ADRs (T027a LTP splitter,
  T027-pptrf custom Transformer_2P_1S symbol, T027c Koren models PWRS
  patch, T027d Sallen-Key equal-R unequal-C). KB sync L1+L2 каждой
  фазы (4 new spice.* topics + agent.command-routing extensions + 8
  L2 regression cases). Single-day sprint 2026-06-02. L3 smoke
  отложена на отдельной session после Phase E merge per Q13.

- **T166** — [closed 2026-06-02, PR #105] **SPICE models для EH 6922
  и 6Н30П-EB + sanity-check fixtures.** Vladimir-requested tubes
  added: `ayumi/6922.inc` (brand alias for 6DJ8 family) + `custom/
  6N30P_EB.lib` (Sovtek/EH low-µ high-current). 2 facade fixtures (6
  acceptance tests). Uses existing efactory `convert_pwrs_to_ngspice`
  + `convert_ayumi_to_ngspice` для Ayumi 6DJ8.inc patch.

- **T165** — [closed 2026-06-01, PR #101] **Cleanup ngspice temp
  `.tmp_*.{cir,raw,wrapper.cir}` files после measurement use cases.**
  4 use cases (`measure_phase_margin`, `measure_gain`, `measure_bandwidth`,
  `measure_thd`) + CLI helper `_prepare_ac_netlist` переведены на
  `tempfile.TemporaryDirectory(prefix='efactory-<usecase>-')` —
  единообразный паттерн с `bridge_sweep` / `edit_and_resim_with_delta`.
  CLI helper стал `@contextlib.contextmanager`; caller — `contextlib.
  ExitStack` для preservation узкого scope `ValueError` catching при
  сохранении lifetime tmp dir на всё время use case'а. TDD:
  параметризованный leak test (5 cases) — failing pre, passing post.
  `.gitignore` safety-net `**/*.tmp_*.{cir,raw,wrapper.cir}` —
  защита от регрессии. Pre-push 4/4 ✓ (1679 passed @ 86.10%
  coverage, +5 vs T163 baseline).

- **T163** — [closed 2026-06-01, PR #100] **BJT CE shunt-shunt NFB
  fixture для full 4-method cross-validation matrix.** Single-stage CE
  с voltage-divider bias + AC-only shunt-shunt feedback (R_F=47k +
  C_F=1µ DC-block, collector→base) на Q2N3904. Closes ADR-T153g BJT
  CE row (`?` → empirical): V + Tian strict @ canonical break `(vout,
  C_F)` (PM=126.28° ± 2°, fc=299 Hz; Tian within 1.89° of V), I +
  Rosenstark documented degenerate с physical reasoning. Pattern
  идентичен op-amp C.1 (V+Tian strict, I+Rosenstark degenerate).
  +9 tests (3 fixture + 5 calibration + 1 KB regression); coverage
  86.08% (+0.03% vs T164 baseline). Spec —
  `specs/T163-bjt-ce-nfb/spec.md`. ADR — `DECISIONS.md` (ADR-T163 +
  ADR-T153g matrix row population). KB — `docker/runtime-agent-
  knowledge-base/spice.feedback-break-point.md` extended с BJT CE
  shunt-shunt section. Bundle T164 Level 3 smoke (8 scenarios) —
  отдельный PR после, TODO 0ea5f0ef.

- **T164** — [closed 2026-06-01, PR #99] **Auto-detect heuristic
  refinement для multi-loop tube NFB + KiCad-export element ordering.**
  Stimulus-distance BFS ranking в `_pick_break_edge` (walk-direction
  invariant — op-amp KiCad-export ordering picks `(vout, R_fb)` как и
  inline) + multi-active boost в `score_break_candidates` (NFB SE
  3-active cycle с canonical `(sec_a, C_fb)` ranked above local chord)
  + chord-compound penalty (compound cycle [active, passive] chord +
  sub-cycle демоутируется на multi-active circuits). ADR-T164 в
  `DECISIONS.md`. Coverage: 1665 passed @ 86.05% (+6 vs T153 Phase D
  baseline 1659: 5 T164 integration + 1 KB control).

- **T153** — [closed 2026-06-01, PR #98] **`bridge measure phase-margin
  <NETLIST> --loop-break-node <node>`** для feedback-схем.
  Multi-phase: A (NFB SE tube fixture nfb-se-amp) + B (use case +
  CLI + slash + KB + T021 integration + edit-and-resim extension) +
  C (calibration C.1 op-amp + C.3 tube NFB; C.2 BJT skipped, T163
  BACKLOG) + D (Level 3 smoke + AC sanitizer fix ADR-T153h +
  C.3 calibration values revised). Closed PR'ами #94 (B.6), #95
  (B.7), #96 (C.1), #97 (C.3), #98 (D). Final coverage: 1659 passed
  @ 85.98% (+95 vs T153 start baseline). Spec —
  `specs/T153-phase-margin/spec.md`. ADRs: T153a (4-method strategy),
  T153b (NetlistGraphAnalyzer), T153c-d (injection patcher + edge
  contract), T153e (auto-detect callback), T153f (op-amp break
  convention), T153g (per-topology matrix), T153h (Q7=a enforced
  via AC sanitizer). BACKLOG triggers: T163 (BJT CE fixture для
  full 4-method matrix), T164 (auto-detect refinement multi-loop
  tube + KiCad `/`-prefix).

- **T021** — [closed 2026-05-30, PR #93] **`bridge edit-and-resim`
  с автосравнением метрик до/после.** Финальная содержательная задача
  analysis-first ordering Фазы 2 (фундамент T023 метрики + T022 sweep).
  - **Domain** — 3 frozen Pydantic VO `Gain/Bandwidth/ThdDelta`
    (Phase-coherent с T023 без union'а, Q-F → a):
    `before`/`after`/`delta_absolute`/`delta_relative_percent`/
    `failed_reason` + `metric_field` Literal-дискриминатор. Classmethods
    `from_measurements` / `from_failed_after`; validators
    `after==None ⇔ failed_reason set` + NaN-forbid в delta.
  - **Use case** `edit_and_resim_with_delta` (T004b `edit_and_resim`
    оставлен нетронутым, Q-A → b): export baseline → measure × N →
    `SchematicSnapshot` batch edit → export after → measure × N →
    assemble Deltas. **Strict baseline** (failure → `BaselineFailedError`,
    edit'ы не применяются, Q-E → a); **per-metric continue-on-failure**
    после edit'ов; after-export failure → все метрики failed.
    `EditAndResimConfig` (Pydantic frozen) — единый набор флагов
    на все метрики (Q-C → a, T022 паттерн) + per-metric required-
    fields + silent dedupe `metrics`.
  - **CLI** `bridge edit-and-resim <PROJECT> --schematic ... --set
    REF=VALUE [...] --measure {gain,bandwidth,thd} [...] [...]`
    (Q-B → a): 14 флагов + validation chain + soft-warn >10 edits +
    explicit error mapping (BaselineFailedError → exit 1; Component/
    MultipleMatchesError → exit 1 + Rollback message; failed-metric →
    exit 1).
  - **Renderer** text aligned table (Metric/Field/Before/After/Δ/Δ%)
    + json (Q-H → b, полные before/after VO + delta + edits + project).
  - **Slash `/edit-and-resim`** + KB sync Levels 1+2 (mapping table
    в `agent.command-routing` + regression case
    в `test_control_examples.py`) + Level 3 full smoke в
    `efactory:linux` контейнере (3 scenarios — one-edit, multi-
    edit-multi-metric, edge case).
  - **+52 теста** (19 domain + 19 use case + 10 renderer + 4 CLI e2e),
    pytest 1336 passed @ coverage 84.76%.
  - **Out of scope**: sweep по диапазону (T022); multi-sheet; visual
    delta plot; persistence дельты sim-result kind'ом; calibration
    THD (T131); phase margin (T153).
  - **Owner manual smoke (после merge)**: `docker build` +
    `./efactory-up --reset-claude-state`; `/edit-and-resim se-amp-demo
    --schematic schematic/se_amp.kicad_sch --set R5=2k --measure
    gain --measure thd --freq 1k --v-in-peak 0.1 --input-source V2
    --output-signal v(load)`.
  - Spec — `specs/T021-edit-and-resim-delta/spec.md` (Analyzed: 10
    Clarify по рекомендации + Q-J override smoke in container;
    2 Critical разрешены in-spec, 5 Warning, 7 Note).

- **T162** — [closed 2026-05-30, PR #93 (T021)] **Backlog:
  `tests/integration/application/__init__.py` создаёт namespace-
  коллизию с `src/application/`** при `--import-mode=importlib +
  pythonpath=["src"]`. Обнаружено в ходе T021 Phase A. Workaround:
  use-case-test расположен в `tests/unit/application/` (где
  `__init__.py` нет). Уведомлено в Tech Debt; fix — удалить
  `__init__.py` из `tests/**/` пакетов для consistency с importlib mode.

- **T161** — [closed 2026-05-30, PR #92] **Defensive guard для
  пустого / несуществующего NETLIST argument в bridge CLI.**
  `bridge sim-run op ""` падал cryptic `IsADirectoryError: '.'` с
  exit=1; nonexistent path → `FileNotFoundError`. После фикса —
  `Netlist file not found: <path>` в stderr + `typer.Exit(code=2)`.
  Helper `_resolve_netlist_path` применён единообразно в 8 entry
  points: `bridge sim-run {op,tran,ac}` (через общий
  `_run_sim_and_report`), `bridge measure {gain,bandwidth,thd}`,
  `bridge plot {ac,tran}`. Scope расширен с original BACKLOG-записи
  (sim-run + measure) до plot — тот же класс bug'а, тот же helper.
  +16 parametrized e2e-тестов (8 × 2 invalid arguments).

- **T157** — [closed 2026-05-30, PR #90] **De-engineering persistent
  state: filesystem as single source of truth.** Архитектурный
  refactor — убраны SQL-индекс (`MetadataRepository` + SQLAlchemy +
  alembic + aiosqlite) и Kùzu graph-store адаптер. Manifest YAML
  (`project.yaml`) + `decisions/D*.md` теперь единственное persistent
  состояние.
  - **12 use cases переписаны**: параметр `repo: MetadataRepository`
    → `projects_root: Path`; loaders делают `path.is_dir()` +
    `manifest_repo.load(path)`.
  - **`reindex_projects` → `validate_manifests`**: diagnostic-only
    scan; CLI флаг `--remove-orphans` удалён (нет SQL → нет
    orphans). Старое имя — alias для callers.
  - **Удалены файлы**: `src/adapters/outbound/persistence_sql/` (8
    файлов), `tests/integration/adapters/persistence_sql/` (3),
    `tests/integration/adapters/graph_store/`, 3 walking_skeleton-
    теста про reindex/partial-failure, `alembic.ini`.
  - **Deps дропнуты**: `sqlalchemy`, `aiosqlite`, `alembic`, `kuzu`
    из `pyproject.toml` + importlinter contracts.
  - **xfail follow-up T160**: project rename — manifest пишется с
    новым именем но directory остаётся со старым путём.
  - Diff: 66 файлов, +511 / -2869 (net -2358 LOC).
  - Pre-push gates все 5 зелёные: 1265 passed / 9 skipped / 1
    xfailed @ 84.60% coverage.
  - **ADR в `DECISIONS.md` 2026-05-30** «Persistent state: filesystem
    as single source of truth».
  - Spec — `specs/T157-de-engineering-persistent-state/spec.md`.

- **T159** — [closed 2026-05-30, PR #89] **BuildKit cache mounts:
  радикальное ускорение rebuilds (apt + uv + FreeCAD AppImage
  cache).** User feedback после T155: «хочется не качать 820 MB
  снова». Cold full build ~2h → **secondary builds — секунды-
  минуты** через persistent BuildKit cache mounts.
  - **apt cache** (`--mount=type=cache` /var/cache/apt + /var/lib/apt)
    в base + freecad-appimage stages. Disabled docker-clean hook +
    enabled Keep-Downloaded-Packages — debs persist.
  - **uv cache** (`--mount=type=cache` /root/.cache/uv) в
    python-deps + efactory-code stages.
  - **FreeCAD AppImage cache** (`--mount=type=cache` /cache/freecad)
    — 820 MB AppImage скачивается один раз ever per FREECAD_VERSION.
    Conditional skip: cached SHA matches → skip curl entirely.
    Atomic download (fc.AppImage.tmp → SHA verify → mv).
  - **Dockerfile остаётся portable** (CI/GHCR/cold dev-host — full
    первый раз; secondary — cache hit).
  - **Тесты** (+5 regression). Existing T155 curl resilience
    retained.
  - Compact (~20 LOC + 5 tests), без spec'и.
  - Pre-push gates все 5 зелёные (1303 passed, coverage 85.10%).

- **T022** — [closed 2026-05-27, PR #82] **Параметрический sweep
  (`bridge_sweep`) с tabular output + ASCII plot.** Третий шаг
  analysis-first ordering Фазы 2 после T023 (метрики) и T024 (plot).
  **Absorbs T144** (sweep tabular numerical output + CSV/JSON gap +
  ngspice wrapper conflict с KiCad-embedded `.tran` директивой).
  - **Domain VO**: `SweepConfig` (Pydantic frozen, model_validator
    на A1 strict — 5 валидных `(metric, analysis, mode)` пар;
    auto-mapping `--analysis` из `--metric`; required-fields per
    metric). `SweepRun.values: dict | None` опциональное поле
    (A4 backward-compat).
  - **Use case**: metric dispatch (op/gain/bandwidth/thd) через
    `_run_one_combination` + `_measure_values` helpers; reuse
    `measure_*` use cases (T023) через DI; continue-on-failure
    (Q-D → a); soft-warn N>20, hard cap N>100.
  - **CLI**: +14 новых флагов (`--metric|--analysis|--mode|--freq|
    --f-low|--f-high|--v-in-peak|--output-signal|--input-signal|
    --input-source|--output|--output-file|--plot|--plot-y|
    --plot-x-scale|--max-combinations`).
  - **Renderers**: text (aligned plain-text без tabulate) / CSV
    (RFC 4180 stdlib) / JSON (pretty-print indent=2). Plot extension
    `render_sweep_plot` с group_by для 2-param + log/linear
    auto-detect (A8 log-space algorithm, robust к non-sorted input).
  - **Slash `/sweep`** + KB sync Levels 1+2 (`agent.command-routing`
    + regression case в `test_control_examples.py`).
  - **Level 3 smoke** 3/3 scenarios на real agent (docker run
    headless с bind-mount overlay): gain vs Rk multi-V с
    `--input-source V2`, op + CSV → RFC-4180 file, bandwidth +
    plot с правильной physics interpretation.
  - **T144 root-cause** (absorbed): `_strip_analysis_directives`
    в `build_wrapper` стрипит все top-level analysis directives
    (`.op/.tran/.ac/.dc/.four/.noise/.tf/.sens/.disto`) из netlist
    перед вставкой собственной. KiCad-embedded `.tran` больше не
    блокирует appended `.OP`; sweep на `se-amp-demo` теперь печатает
    все 22 v/i traces per combination. +15 regression-тестов.
  - **+91 новых тестов** (29 SweepConfig + 10 bridge_sweep dispatch
    + 17 sweep_table_renderer + 14 plot extension + 15 wrapper +
    6 e2e); pytest 1230 passed, coverage 85.32%.
  - **Out of scope**: parallel SPICE (BACKLOG), sweep по `.options`/
    `temp`/model parameters, adaptive sweep / golden-section. T021
    (delta) — следующая Фаза 2 задача, использует T022 фундамент.
  - **Owner manual smoke (после merge)**: full `docker build` +
    `./efactory-up --reset-claude-state`; `/sweep --metric gain
    --freq 1k --input-source V2 --param R2=270,330,470` на
    `se-amp-demo`.
  - Spec — `specs/T022-bridge-sweep/spec.md` (Analyzed: 10 Clarify
    Q + 14 Analyze issues — 2 Critical разрешены in-spec, 6
    Warning с predeclared resolutions, 6 Note).

- **T155** — [closed 2026-05-27, PR #87] **Dockerfile freecad-appimage
  curl `--http1.1` `--retry 3` (HTTP/2 flakiness).** Past sessions
  reported intermittent failures на FreeCAD AppImage download в cold
  build (BuildKit HTTP/2 + github.com releases — flaky combination:
  TLS resets, connection drops). Defensive flags:
  - `--http1.1` обходит BuildKit HTTP/2 race condition.
  - `--retry 3 --retry-delay 5` против transient network errors.
  - **+2 regression tests** (`test_dockerfile_freecad_resilience.py`)
    — lockdown против silent flag removal при future Dockerfile
    cleanup.
  - Compact (3 LOC Dockerfile + 2 tests), без spec'и.
  - Pre-push gates все 5 зелёные (1142 passed, coverage 85.38%).
  - **Owner manual smoke (опционально)**: cold build retry — но
    проблема probabilistic, не каждый build репродуцирует HTTP/2
    race (т.е. signal только через серии rebuilds).
- **T149** — [closed 2026-05-27, PR #83] **`bootstrap_claude_state`:
  auto-merge `hooks` секции в существующий host settings.json (без
  `--reset-claude-state`).** UX rough из T016 round-trip 2026-05-26:
  pre-T016 settings.json с user-prefs (`theme` /
  `skipDangerousModePermissionPrompt`) → bootstrap no-op'ил → hooks
  не появлялись → SessionStart hook не engaged → agent работал без
  project context. Workaround `--reset-claude-state` затирал
  user-prefs.
  - `scripts/merge_claude_settings.py` — stdlib-only Python helper
    (~80 LOC, без `pyyaml`/`jq` deps): merge `hooks` если у host нет
    своего `hooks` ключа; сохраняет user-keys (incl. nested
    `mcpServers` / `experimental`). Idempotent. RC 0/1/2
    (merged/skipped/error).
  - `efactory-up` функция `try_merge_claude_hooks` вызывается из
    `bootstrap_claude_state` после need_bootstrap=0 check'а. Dev
    path — repo helper + template; production fallback —
    `docker create` + cp helper/template из образа в tmp.
  - **Тесты** (+11 unit): theme-only merge, nested user keys
    preserved, idempotency, invalid JSON / missing files / template
    без `hooks`, CLI subprocess exit-codes.
  - Compact (~80 LOC + 11 tests), без spec'и (проектный CLAUDE.md
    разрешает skip ритуала для small fix).
  - Pre-push gates все 5 зелёные (1151 passed, coverage 85.38%).
  - **Owner manual smoke (после merge)**: `./efactory-up --agent
    se-amp-demo` с pre-existing `$HOME/efactory-state/claude/
    settings.json` (e.g. theme only) → файл содержит и theme, и
    hooks; SessionStart hook engages в TUI без `--reset-claude-state`.
- **T146** — [closed 2026-05-27, PR #84] **`efactory lib validate
  <file>`: SPICE-models static floating-node validator.** Каждая
  нода `.SUBCKT`-блока должна встречаться ≥ 2 раз (external pin +
  internal touch); count==1 → floating (pre-T147 P3/S3 pattern).
  - `application/validate_lib.py` (~190 LOC) — pure heuristic
    parser: regex `.SUBCKT`/`.ENDS`, per-element node-count table
    (R/L/C/V/I/D/E/F/G/H/Q/J/M/S/W/T/O), ground special-case
    (`0`/`GND`), X-subckt → `skipped_subckts`.
  - CLI `efactory lib validate <file>` (new top-level `lib` subapp);
    exit codes 0/1/2 (OK / floating / file error).
  - **Тесты** (+17 unit): valid RC, post/pre-T147 OPT, dangling
    resistor, ground special-case, BJT 3-node, MOSFET 4-node,
    K-coupling refs, X-subckt skip, multi-subckt, comments,
    lowercase, errors.
  - **Immediate ROI**: real `OPT_PP_6K6_8.lib` сразу выдал 3
    floating nodes (PC1/PC2/S3) → spin-off T158 в BACKLOG для
    отдельного hot-fix'а (pre-existing bug аналогичный T147 на PP).
  - Compact (~190 LOC + 17 tests + CLI), без spec'и.
  - Pre-push gates все 5 зелёные (1157 passed, coverage 85.10%).
- **T151** — [closed 2026-05-27, PR #86] **CI workflow
  `template-snapshot-check`: staleness enforcement (follow-up
  T014 A5).** Отдельная GitHub Actions visibility (separate PR
  check entry) поверх existing pytest snapshot test.
  - `.github/workflows/template-snapshot-check.yml` (~70 lines):
    push+main / pull_request+** / workflow_dispatch triggers;
    fast job (≤10 мин, без Docker).
  - **Step 1**: pytest snapshot test (нормализует UUIDs +
    lib_symbols reordering из-за PYTHONHASHSEED).
  - **Step 2**: defensive `regenerate-templates.py` + `git diff
    --exit-code` для non-schematic assets (`models/*.lib`,
    `template.yaml`, `README.md`); `.kicad_sch` exclude'ится
    (его check'ает Step 1).
  - **Actionable fail messages** — `run uv run python scripts/
    regenerate-templates.py` + commit.
  - **+8 unit tests**: YAML parseability, triggers (push/PR/manual),
    step structure, fail-message actionability, Python setup.
  - Compact (~70 YAML + 8 tests), без spec'и.
  - Pre-push gates все 5 зелёные (1148 passed, coverage 85.38%).
  - **Owner manual smoke (после merge)**: первый PR triggers
    workflow → visibility check «template-snapshot-check» в
    GitHub PR checks.
- **T145** — [closed 2026-05-30, PR #88] **`efactory bridge sim-run op
  --with-op-fallback`: OP через TRAN-settled (lечит trivial idle на
  tube circuits).** T022 baked-image smoke 2026-05-30 confirmed: на
  `se-amp-demo` `.OP` solver сходится к trivial idle (V(plate)≈0,
  tube не conducts) — OP-sweep по R2 даёт одинаковые результаты.
  Standard SPICE workaround: `.tran 1us 100ms uic` + extract settled
  samples как OP.
  - `sim_run` use case + `enable_op_fallback: bool = False` flag.
    When True + OpAnalysis: `.OP` подменяется на TranAnalysis(uic=True),
    synthetic operating_points из settled tail.
  - `_extract_op_from_tran_tail` helper — average last 10% samples.
  - CLI `bridge sim-run op --with-op-fallback`. Stdout marker
    `fallback=transient-to-op`.
  - **Тесты** (+10 unit): tail extraction, sim_run paths, non-OP
    rejection, custom t_stop, missing time_series.
  - Compact (~75 LOC + 10 tests), без spec'и.
  - Pre-push gates все 5 зелёные (1150 passed, coverage 85.38%).
  - **Owner manual smoke (после merge + image rebuild)**:
    `efactory bridge sim-run op <netlist> --with-op-fallback` на
    se-amp-demo → должен показать V(cathode)≈12V, V(plate)≈230V
    (real bias) вместо trivial idle.
- **T142** — [closed 2026-05-27, PR #85] **`efactory sim-results
  prune <PROJECT>`: retention policy для `.efactory/sim-results/`.**
  T016 follow-up: append-only sim-results потенциально разрастаются
  до сотен файлов / десятков MB. Compact prune с mutually exclusive
  `--keep-last N` / `--keep-days D`; default `--keep-last 100`.
  - **Use case `application/prune_sim_results.py`** (~80 LOC):
    options validation (mutually exclusive, non-negative,
    positive days), delegation в port.
  - **Port extension** `SimResultsRepository.prune(...) → int`.
  - **Adapter `FileSystemSimResults.prune`**: sorted by filename
    (timestamp prefix); `keep_days` использует filename-timestamp
    parsable → mtime fallback; skip non-`.json`.
  - **CLI** `efactory sim-results prune <PROJECT> [--keep-last N |
    --keep-days D]` (new top-level `sim-results` subapp). Exit
    codes 0/1/2.
  - **build_app** signature расширен `sim_results_repo`; composition
    пробрасывает `FileSystemSimResults()`.
  - **Тесты** (+17): 7 unit use case + 10 integration adapter.
  - Compact (~140 LOC + 17 tests), без spec'и.
  - Pre-push gates все 5 зелёные (1157 passed, coverage 85.38%).
  - **Owner manual smoke (после merge)**: `efactory sim-results
    prune se-amp-demo --keep-last 5` после нескольких sim-run.

- **T141** — [closed 2026-05-27, PR #79] **Dev-only build
  acceleration: `efactory-build-dev` / `efactory-build-libs-dev`
  wrappers с `docker buildx --cache-from/-to type=local`.** Compact
  задача (≤2 ч), без spec'и. Триггер — build T024+T134 идёт
  ~40-60 мин на dev-host; хочется ускорить следующие пересборки.
  - 2 bash wrappers в `scripts/`: pre-flight (docker + buildx),
    auto-create builder instance (idempotent), `--cache-from/-to
    type=local mode=max`, `--load` в local daemon.
  - `efactory-build-dev` для main Dockerfile; args `--no-cache`,
    `--image <TAG>`, env `EFACTORY_BUILD_CACHE_DIR`
    (default `$HOME/efactory-buildcache/`).
  - `efactory-build-libs-dev` для Dockerfile.libs; `--with-3d`
    для `INCLUDE_3DMODELS=1`; cache отдельный
    (`$HOME/efactory-libs-buildcache/`).
  - Без buildx → actionable error с install instruction +
    fallback на обычный docker build.
  - README «Быстрый старт» расширен dev-only ускорением.
  - Dockerfile **остаётся portable** (ADR 2026-05-24
    «пользователь должен честно тянуть»).
  - Pre-push gates все 5 зелёные (1140 passed, без изменений vs
    T134 baseline).
  - **Owner manual smoke (после `sudo apt install docker-buildx-
    plugin`):** прогревочный build как обычный; повторный — секунды.

- **T156** — [closed 2026-05-27, PR #80] **`efactory kb add --body
  "..."` inline body option** — UX fix обнаружен в smoke validation
  T134. Compact для agent autonomous KB writes.
  - Body source priority: `--body` (inline) > `--body-file` > stdin.
  - Mutually exclusive `--body` / `--body-file` (exit 2).
  - `/kb-add` slash-команда обновлена.
  - Validated через retry smoke с rebuilt image (2026-05-27 14:54):
    agent сделал call `--body` одной Bash-командой без stdin.
  - Pre-push gates все 5 зелёные (1140 passed, без regression).

- **T134** — [closed 2026-05-26, PR #78] **Agent Knowledge Base —
  persistent KB для runtime-агента efactory.** 5-phase implementation
  по полному методическому ритуалу (spec → A domain → B store → C
  hook+bind-mount → D CLI+slash+DI → E 10 seed+regression+CHANGELOG).
  - **Архитектура** (без MCP / vector DB): markdown с frontmatter,
    namespaced slug `<ns>.<name>`. Built-in seed в `docker/runtime-
    agent-knowledge-base/` запекается в образ; host-mutated через
    bind-mount `$HOME/efactory-state/knowledge-base/`. Host wins
    при conflict; `--reset-claude-state` расширен. SessionStart hook
    (T016) injection TOC grouped by namespace в `additionalContext`;
    полный body через `Read` / `/kb-search` (никакого RAG).
  - **Domain + adapters** (Phase A+B): `KbEntry` Pydantic strict
    (extra='forbid', namespaced topic pattern, цифра-начало после
    точки разрешена для `3d`/`2d`); `FileSystemKbStore` с host-wins
    merge, `KbConflictError` на add без `--force`, filter `'.' in
    stem` пропускает README.
  - **CLI** (Phase D): `efactory kb {list,show,add,search}` + 2
    slash-команды `/kb-search`, `/kb-add`. `build_app` signature
    +`kb_store`; composition пробрасывает `FileSystemKbStore`.
  - **Hook + efactory-up** (Phase C): `render_kb_section()` stdlib-
    only frontmatter parser (без pyyaml, cold-start ~30-50 ms);
    `bootstrap_kb_state()` + новый bind-mount; Dockerfile COPY seed.
  - **10 seed entries** (Phase E): 3 из T131 + 3 из T132 + 3 из
    T133 + новый `agent.command-routing` (mapping user-request →
    slash-command для защиты от изобретения велосипеда / scan
    собственных исходников).
  - **Тесты** (+66): 19 domain + 16 parser + 19 KbStore integration
    + 9 hook KB + 4 frontmatter + 12 control-example regression.
    Pre-push gates все 5 зелёные (1119 passed, coverage 85.50%).
  - **T154 spin-off** (BACKLOG, Q-F → c): full migration dev-process
    knowledge (DECISIONS/CHANGELOG/auto-memory/mem0) → KB как
    отдельная 4-phased curation-задача.
  - **Out of scope:** vector DB / RAG, multi-agent KB, project-
    specific knowledge (T103), subdirectory layout (>30 entries),
    inverted index (>100 entries).
  - **Owner manual smoke (после merge):** `docker build` +
    `./efactory-up --reset-claude-state`; в TUI запрос
    «построй график АЧХ» — agent должен использовать KB hit
    `agent.command-routing` → выбрать `/plot-ac` без изобретения
    велосипеда.
  - Spec — `specs/T134-agent-knowledge-base/spec.md` (Analyzed:
    11 clarify «по рекомендации» + 8 analyze issues — 0 Critical,
    3 Warning отражены, 5 Note guidance).

- **T024** — [closed 2026-05-26, PR #77] **ASCII-графики через
  plotext (`bridge plot ac|tran`).** Второй шаг analysis-first
  ordering Фазы 2; фундамент для T022 sweep visualization.
  - `plotext==5.3.2` — новая runtime dep.
  - **CLI** `bridge plot <ac|tran>` sub-Typer (гомогенно с
    `sim-run`/`measure`): `plot ac` (АЧХ магнитуда dB vs log-частота),
    `plot tran` (waveform vs time). `--width 80 --height 20` defaults.
  - **Renderer** (`adapters/inbound/cli/plot_renderer.py`):
    `render_ac_sweep` / `render_time_series` возвращают строку через
    `plotext.build()` — testable без захвата stdout. Case-insensitive
    lookup; floor `_DB_FLOOR = -200 dB` (plotext не умеет infinity).
  - **Slash-команды**: `/plot-ac`, `/plot-tran` (hyphenated flat).
  - **Тесты** (+19): 12 unit renderer + 3 e2e на real ngspice (RC
    low-pass: AC plot, TRAN plot, missing signal exit 2) + 4
    frontmatter (2 per slash command). Pre-push gates все 5 зелёные
    (1059 passed, coverage 86.07%).
  - **Out of scope:** `--plot` flag в `measure_bandwidth` (с f_low/
    f_high markers) — follow-up при необходимости; multi-signal
    subplot'ы; schematic-render (T025).
  - Реализован без spec'и: ≤1 день, проектный CLAUDE.md разрешает
    skip ритуала для «мелких задач». Acceptance T024 BACKLOG
    выполнен (default `--width 80`).
  - **Owner manual smoke (после merge):** `docker build` +
    `./efactory-up --reset-claude-state`; `/plot-ac` + `/plot-tran`
    на `se-amp-demo` после `/sim-run`.

- **T023** — [closed 2026-05-26, PR #76] **Измерения как отдельные
  bridge-инструменты (gain / bandwidth / thd).** Первая содержательная
  задача analysis-first ordering Фазы 2; фундамент для T021 (delta)
  и T022 (sweep tabular).
  - **Domain** — три независимых frozen Pydantic VO (Q-A → b: без
    discriminated union'а): `GainMeasurement`, `BandwidthMeasurement`,
    `ThdMeasurement` (валидаторы: large mode требует v_in_peak;
    bandwidth f_high>f_low и bandwidth==diff; dominant_n≥2 для thd).
    `AnalysisType` enum +`GAIN`, `BANDWIDTH` (THD из T016).
  - **Use cases** (`application/measure_{gain,bandwidth,thd}.py`,
    hex-DI Simulator + NetlistEditor):
    - `measure_gain`: small AC (n_points=2 workaround) с auto-injection
      `AC 1` modifier'а; large TRAN + RMS на settle-portion (последние
      2 из 10 периодов).
    - `measure_thd`: независимый use case (Q-D → b), не wrapper T131.
      TRAN + ngspice `fourier` → extraction (dominant = max normalized
      n ≥ 2); calibration loop out of scope.
    - `measure_bandwidth`: AC sweep dec; midpoint auto (max|H|) или
      ref_freq; endpoints через linear interp в log-freq space.
    - Все три: auto-detect single V-source (Q-G → c); optional
      SimResult persistence (T016 pattern).
  - **NetlistEditor port extension** (Phase B mid-decision вариант 1):
    `ensure_ac_modifier` (идемпотентная injection) + `find_top_level_
    v_sources` (depth-counter исключает subckt-internal).
  - **CLI** `bridge measure <gain|bandwidth|thd>` sub-Typer (Q-J → a);
    `--output json|text`; SPICE-нотация частот через
    `parse_spice_number`. `build_app(... netlist_editor=...)`;
    composition root пробрасывает `NgspiceNetlistEditor()`.
  - **Slash-команды** `/measure-gain`, `/measure-bandwidth`,
    `/measure-thd` в `docker/runtime-agent-commands/` (hyphenated
    flat per T014 A1); `runtime-agent-CLAUDE.md` обновлён.
  - **Тесты:** 37 domain + 9 ensure_ac + 6 find_v_sources + 18+14+15
    use cases + 7 e2e (real ngspice на voltage divider 1:2: gain
    -6.02 dB, bandwidth flat → endpoints, thd ≈ 0%) + 6 slash-команд
    frontmatter. Pre-push gates все 5 зелёные (1040 passed, coverage
    86.03%).
  - **T153 spin-off** (BACKLOG, Q-B → c): phase margin отдельной
    задачей когда появится feedback-фикстура.
  - **Out of scope:** target-power calibration loop для thd (T131);
    schematic input → design-to-measure pipeline (только `.cir`);
    phase margin (T153); визуализация (T024/T025); sweep (T022);
    delta (T021).
  - **Owner manual smoke (после merge):** `docker build` +
    `./efactory-up --reset-claude-state`; `/measure-*` на
    `se-amp-demo` после `/sim-run`.
  - Spec — `specs/T023-measurements/spec.md` (Analyzed: 10 clarify
    «по рекомендации» + 12 analyze issues — 1 Critical разрешён
    in-spec, 4 Warning отражены, 7 Note guidance'ы).

- **T147** — [closed 2026-05-26, PR #74] **Fix `OPT_SE_5K_8.lib`:
  floating ноды DCR через internal nodes (`Pint`/`Sint`).** Hot-fix
  демо-фикстуры: `Rp_dcr`/`Rs_dcr` подключались к floating узлам
  `P3`/`S3` → singular matrix при `.op` на `se-amp-demo`. Корректный
  fix — внутренние узлы для последовательного включения DCR с
  обмоткой:
  - `Lp Pint P2 50` (было `Lp P1 P2 50`).
  - `Rp_dcr P1 Pint 200` (было `Rp_dcr P1 P3 200`).
  - `Ls Sint S2 0.08` (было `Ls S1 S2 0.08`).
  - `Rs_dcr S1 Sint 0.3` (было `Rs_dcr S1 S3 0.3`).
  - `K1`, `Cps`, параметры (200 Ω / 0.3 Ω / K=0.9995 / 200 pF) без
    изменений.
  - `data/templates/se-amp/models/OPT_SE_5K_8.lib` пересобрана через
    `scripts/regenerate-templates.py`; `{{PROJECT_NAME}}.kicad_sch`
    не commit'нут (UUID flakiness, snapshot test нормализует).
  - Pre-push gates все 5 зелёные (ruff/format/mypy/lint-imports 3/3
    KEPT/pytest 928 passed, coverage 86.14%).
  - Manual smoke: `ngspice -b` с `.op` на минимальном testbench →
    convergence, `v(plate)=250 V` (DCR ≪ R_plate=100k), physically
    valid.
  - **Owner manual smoke (после merge):** `./efactory-up --agent
    se-amp-demo` → `/sim-run --analysis op` после `docker build`.
  Закрывает 1 из 5 round-trip gap'ов T016 (BACKLOG). Первый шаг
  analysis-first ordering Фазы 2.

- **T014** — [closed 2026-05-26, PR #73] **efactory custom slash-команды
  для Claude Code + template-инфраструктура.** Phase 1b закрыта
  окончательно (T013 + T016 + T014).
  - **Slash-команды** (`docker/runtime-agent-commands/*.md`,
    hyphenated flat naming per Analyze A1 — Claude Code парсит
    `/cmd` как одно слово): `/project-create <NAME>` (wrapper над
    `efactory project create --name <NAME> --template se-amp`),
    `/project-use <NAME>` — **display-only** (Analyze A2: Bash cwd
    persistence нестабильна между tool calls), запускает SessionStart
    hook (T016) с `CLAUDE_PROJECT_DIR=/workspace/<NAME>` и парсит
    JSON-вывод; `/sim-run [SCHEMATIC] [--analysis op|tran|ac]` —
    wrapper над `efactory bridge sim-run`, auto-detect единственного
    `.kicad_sch` в cwd (top-level + 1 subdir, skip dot-directories).
    Frontmatter: `description` + `argument-hint` + `allowed-tools: Bash`.
  - **CLI** `efactory project create --template <name> [--target-dir
    DIR]` (без --template — backward-compat пустой проект);
    `EFACTORY_PROJECTS_ROOT` уже `/workspace` в образе.
  - **TemplateMaterializer** (helper в `adapters/inbound/cli/`,
    Q4 «по рекомендации» — без отдельного outbound port'а):
    filename substitution `{{PROJECT_NAME}}` → sanitized name
    (`spaces → _`, `/ → _`); content substitution в
    `.kicad_sch/.kicad_pro/.md/.yaml/.yml/.txt/.cir`; pre-scan на
    конфликты с existing файлами; `template.yaml`/`README.md` шаблона
    НЕ копируются в проект (метаданные самого шаблона).
  - **Шаблон se-amp** (`data/templates/se-amp/`): запечённый
    artefact `_build_se_amp` (6П14П SE + OPT 5kΩ:8Ω + R_load 8Ω),
    `{{PROJECT_NAME}}.kicad_sch/pro`, `models/{6P14P,OPT_SE_5K_8}.lib`,
    `template.yaml`, `README.md`. Force-included в wheel (pyproject).
  - **`scripts/regenerate-templates.py`** — ручной пересбор при
    изменении builder'а; `_build_se_amp` динамически импортируется
    из integration-теста (аналог `gen-se-amp-demo.py`).
  - **Snapshot test** — нормализация UUID v4 (`(uuid "...")` +
    `(path "/UUID"...)`) + полное удаление `(lib_symbols ...)`
    блока (его order зависит от PYTHONHASHSEED, internal KiCad
    cache, не семантика). Fail-сообщение «run
    `uv run python scripts/regenerate-templates.py`».
  - **`efactory-up` rename:** `--reset-claude-settings` →
    `--reset-claude-state` (Q9 «по рекомендации»); bootstrap'ит и
    settings.json (T016), и commands/*.md (T014). Deprecated alias
    `--reset-claude-settings` с stderr warning; удаление — в
    следующем minor. Backup при reset — единый каталог
    `$STATE_DIR/claude.bak-YYYY-MM-DD/`.
  - **Dockerfile:** новый `COPY docker/runtime-agent-commands/
    /opt/efactory/share/claude-defaults/commands/`.
  - **System prompt** (`docker/runtime-agent-CLAUDE.md`): секция
    «Custom slash-команды efactory» + warning про cwd-instability
    («используй абсолютные пути»).
  - **Тесты:** 13 unit (materializer) + 4 e2e (CLI с/без template,
    unknown template, --target-dir) + 2 integration (snapshot +
    script CLI smoke) + 1 e2e regression-fix (payload signature) +
    8 static (slash-command frontmatter валидация). Pre-push gates
    все 5 зелёные (ruff/format/mypy/lint-imports 3/3 KEPT/pytest):
    928 passed, 9 skipped, coverage 86.14%.
  - **Out of scope:** `/export-production` → T150 (BACKLOG); CI
    snapshot enforcement → T151; доп. шаблоны (pp-amp/preamp/filter)
    — BACKLOG follow-ups.
  - Spec — `specs/T014-claude-code-slash/spec.md` (Analyzed, 10
    clarify resolved, 12 analyze issues — 2 Critical resolved до
    implementation).

- **T016** — [closed 2026-05-26, PR #72] **Dynamic project context в
  Claude Code (SessionStart hook + sim-results infrastructure).**
  Phase 1b завершена: runtime-агент при старте сессии получает
  динамическую project-сводку дополнительно к статическому system
  prompt из T013.
  - **Phase A — SessionStart hook + settings.json bootstrap.**
    `scripts/session_start_hook.py` (Python 3 stdlib через
    `/usr/bin/python3`, cold start ~30-50 ms) сканирует cwd →
    `/workspace/<NAME>/`, формирует markdown-block (KiCad/SPICE/
    FreeCAD/FEM файлы, soft cap 20/категория, последние 3 sim-
    результата без `metrics`) в JSON envelope `additionalContext`.
    `docker/runtime-agent-settings.json` — embedded template
    settings.json (matcher `startup|resume|clear|compact`, timeout
    10 s), bootstrap'ится в host state через `efactory-up --agent`.
  - **`efactory-up --agent [NAME]`** — позиционный аргумент NAME с
    pre-flight валидацией, cwd=`/workspace/$NAME/`. Новый
    `--reset-claude-settings` (backup `*.bak-YYYY-MM-DD`) — escape
    hatch для апгрейда образа (mitigation A1 спеки).
  - **Phase B — sim-results infrastructure (hex архитектура).**
    `domain/sim_results.py` (`SimResult` Pydantic VO + `AnalysisType`
    StrEnum, `schema_version=1`), `ports/outbound/sim_results.py`
    (`SimResultsRepository` Protocol), `adapters/outbound/
    sim_results_filesystem/` (`FileSystemSimResults` с атомарной
    записью `.json.tmp → Path.replace` через `asyncio.to_thread`).
    Канонический путь — `<PROJECT>/.efactory/sim-results/
    <TIMESTAMP-safe>-<analysis>.json`.
  - **Phase C — `sim_run` integration.** Optional `sim_results_writer`
    + `project_root` параметры; `ValueError` при partial DI; полная
    обратная совместимость без них. Summary рендерится по
    `analysis.type` (op/tran/ac/four).
  - **Phase D — docs.** `docs/container-boundary.md` (sim-results +
    hook/template paths), `README.md` (Запуск runtime-агента
    расширен), `CHANGELOG.md` [Unreleased]. Follow-ups в `BACKLOG.md`:
    T142 (sim-results rotation), T143 (`PostToolUse` real-time
    refresh).
  - **52 новых теста**: 27 hook unit + 2 hook subprocess integration +
    11 domain + 8 adapter + 6 sim_run. Pre-push gates зелёные
    (ruff/format/mypy/lint-imports 3/3 KEPT/pytest); 896 passed,
    9 skipped, coverage 86.10%.
  - **Mitigation issues** из Analyze: A1 (`--reset-claude-settings`),
    A2 (async writer body via `asyncio.to_thread`), A3 (SimResult ≠
    SimulationResult, build snapshot extract), A6 (cwd →
    `$CLAUDE_PROJECT_DIR` ⇒ `os.getcwd()` ⇒ `/`).
  - Spec — `specs/T016-project-context/spec.md` (Analyzed, 7 clarify
    resolved «по рекомендации», 7 issues все Warning/Note).

- **T013** — [closed 2026-05-24, PR #71] **Claude Code runtime в
  контейнере: install + auth + entrypoint** (переформулировано
  2026-05-24; старая «Регистрация efactory MCP-серверов» закрыта
  по обсуждению — MCP не используем).
  - **Dockerfile:** `nodejs`+`npm` в base stage + отдельный RUN-слой
    с `ARG CLAUDE_CODE_VERSION=2.1.150` + `npm install -g
    @anthropic-ai/claude-code`. `COPY docker/runtime-agent-CLAUDE.md
    /CLAUDE.md` (system prompt в корне образа).
  - **efactory-up --agent:** новый TUI-режим без X11/libs, `-it +
    -w /workspace`, защита от root, env-passthrough
    `ANTHROPIC_API_KEY`, mutually-exclusive с
    `--demo/--demo-freecad/--headless`. `claude
    --dangerously-skip-permissions`.
  - **docker/runtime-agent-CLAUDE.md:** stub system prompt (роль
    РЭА-проектировщика efactory; реально доступные инструменты:
    `kicad-cli`, `ngspice`, `freecadcmd`, `ElmerSolver`, `getdp`,
    `gmsh`, `uv run python -m efactory.*`, базовые Bash/Read/Write/
    Edit/Glob/Grep). Без `efactory` CLI (T014, не сделан).
  - **DECISIONS.md 2026-05-24:** ADR «Tool surface = Bash + efactory
    CLI + filesystem, не MCP» — Phase 1b: MCP не используем.
  - **docs/container-boundary.md:** убраны MCP overrides + credentials
    overlay (отменены); снят aspirational статус с CLI/ENV; добавлена
    секция про изоляцию credentials через interactive login изнутри.
  - **BACKLOG T141:** «Dev-only build acceleration через `docker
    buildx --cache-from/-to type=local`» (контекст: build T013 на
    медленном канале занял ~1.5 ч; Dockerfile portable per Vladimir
    «пользователь должен честно тянуть»).
  - Smoke внутри `efactory:linux`: `claude --version` → 2.1.150,
    `node --version` → v18.19.1, `/CLAUDE.md` (3343 байт),
    `CLAUDE_CONFIG_DIR=/efactory/.claude`. Pre-push gates зелёные,
    coverage 86.16%. Image size: 7.99 → 8.88 GB (+890 MB).
  - End-to-end TUI smoke (interactive login + tool-use) — Vladimir
    вручную перед merge.
  - Spec — `specs/T013-claude-code-runtime/spec.md` (Analyzed, 8
    clarify resolved, 10 analyze issues).

- **T140** — [closed 2026-05-24, PR #70] **`docs/container-boundary.md`
  как single source of truth для границы образ/host + persist Claude
  Code state наружу.** Новый документ как SSOT (принцип «образ ≈
  инструменты, volumes ≈ данные», полная таблица mounts, env vars,
  явная секция «что НЕ выносим и почему»). `efactory-up` mount'ит
  `$HOME/efactory-state/claude/` → `/efactory/.claude` (rw):
  runtime-агент сохраняет auto-memory / settings / todos между
  `docker rm`. Cross-refs в spec T110 §5, README, DECISIONS
  2026-05-19, BACKLOG T013. Pre-push gates зелёные (ruff / format /
  mypy / pytest 86.16% coverage). Manual smoke (после merge):
  `touch /efactory/.claude/smoke.txt` в контейнере → файл на хосте.

- **T133** — [closed 2026-05-21, PR #66] **Elmer FEM pivot — 3D
  acceptance ±25% к PyOM ZHANG achieved (Lp=6.04H, -13.3%);
  factor 19× improvement от T113 baseline gap (3.42× → 1.15×).**
  10 commits на ветке T133-elmer-fem-pivot squash в один при merge.
  - **Phase 0** — Elmer 2D capability probes (H-B Curve syntax,
    Infinity BC Robin-type, ElmerGrid -autoclean).
  - **Phase 1** — 2D Elmer linear adapter + shared `fem_common.py`
    (C3 refactor: ECoreDimensions / emit_e_core_geo / PyOM helpers
    moved из getdp adapter).
  - **Phase 2** — 2D nonlinear-frohlich + central-diff DC bias
    (known IEEE_UNDERFLOW limitation, infrastructure-only).
  - **Phase 3a** — 3D Whitney AV feasibility probe (tree gauge,
    MUMPS direct).
  - **Phase 3b** — `emit_e_core_geo_3d` OCC mesh generator (ungapped
    smoke + gapped Phase 3d).
  - **Phase 3c** — 3D adapter mode (`dimensionality='3d'`), Whitney
    AV + CalcFields + energy extraction (auto-injects "electromagnetic
    field energy" в SaveScalars → Lp = 2W/I²).
  - **2D findings fixation** — docstring + tightened integration
    test к 19.65 H baseline.
  - **Phase 3d** — 3D gapped E-core с geometrically-derived lateral
    leg bounds, factor 1.7× к ZHANG (4.07 H, -41.5%).
  - **Phase 3d.2** — mesh refinement (20μm/5mm → 51K tetra) →
    **acceptance ±25% achieved** (Lp=6.04 H, -13.3% к ZHANG).
  - **Phase 3e** — ADR + BACKLOG follow-ups (T136-T139) + T134 KB
    control example.
  - **Follow-up T-IDs** (in BACKLOG): T136 Elmer rebuild с AMS
    preconditioner → target ±10%, T137 Coil mechanism с mesh bridges,
    T138 PyOM lateral_x semantics fix, T139 3D nonlinear-frohlich.
  - Auto-memory: `feedback_elmer_2d_keyword_pitfalls`,
    `feedback_fem_2d_inherent_gap_to_zhang`,
    `feedback_elmer_3d_solver_memory_limits`.
  - Spec: `specs/T133-elmer-fem-pivot/spec.md`.

<!-- Закрытые задачи, ждущие переноса в CHANGELOG.md при следующем
     релизе или значимой точке. После переноса — очищаем. -->

- **T132** — [closed 2026-05-21, PR #65] **Interleaved OPT leakage
  inductance — pure-Python analytical backend, acceptance gates
  passing.** Phase A→B→C закрыт; PyOM `calculate_leakage_inductance`
  оказался непригодным (mesh broken across все 1.3.0→1.3.12 versions),
  switched на Erickson sandwich-transformer formula. Pilot acceptance
  на OPT_SE_5K_8 fixture (E 42/15, 3500/140 turns, P-S-P-S-P 5-section):
  Lσ = **6.50 mH** в spec band `[0.1, 10] mH`, k = 0.9997, HF-3dB @
  5kΩ ≈ 122 kHz (hi-end consumer range). Monotonicity 1/N² theorem
  verified exact для zero-insulation case.
  - **Phase A**: `WindingSection` + `InterleavingPattern` +
    `LeakageInductanceResult` + `MagneticComponent.section_layout`
    с cross-field validator (14 unit tests); новый port
    `LeakageInductanceAnalyzer` Protocol + 2 errors (SRP per
    Protocol, separate from `MagneticAnalytics`).
  - **Phase B (abandoned)**: пробовали `PyOpenMagneticsAnalytics`
    composite extension через `pyom.wind` + `calculate_leakage_
    inductance`. 4+ часа investigation: `magnetic_autocomplete` +
    bobbin column patches + `process_inputs` + full `simulate()`
    pipeline + cross-material sweep (12 materials) + version sweep
    (1.3.0→1.3.12, all fail identically) — PyOM MKF C++ mesh layer
    consistently возвращает `Mesh generation failed: induced field
    data is empty`. Circular dependency в public API. Switched
    к Phase C.
  - **Phase C — success**: `AnalyticalLeakage` adapter
    (`adapters/outbound/leakage_inductance_analytical/`): pure-Python
    Erickson formula + PyOM-catalog geometry resolution (только
    lookup-API, без mesh). DI: `pyom_module` + `MagneticAnalytics`
    Protocol (для L_self → coupling_factor). 35 unit tests
    (formula/geometry/adapter); use case `analyze_interleaved_
    leakage` с 3 unit tests; **4 acceptance tests** — monotonicity
    + absolute range + coupling strength + N²-ratio sanity.
  - **Follow-up**: T135 в BACKLOG — "FEM cross-validation of analytical
    leakage" (Elmer pivot T133 ИЛИ GetDP extension); analytical
    ±20-30% точность приемлема per T132 spec, но FEM cross-check
    подтвердит formula valid на pilot fixture'ах.
  - **Investigation reference**: PyOM `calculate_leakage_inductance`
    upstream — long-standing mesh bug (not version-specific); minimal
    reproducer ready, но open GitHub issue deferred (Erickson
    analytical solves T132 use case без upstream dependency).

- **T131** — [closed 2026-05-21, PR #63] **SPICE saturable transformer
  + THD distortion analysis use case — fully working pilot.**
  5 phase-commits (squash в один при merge):
  - **Phase A**: saturable subckt generator + `FrohlichBHCurve.h_b_pairs()`.
  - **Phase B**: `FourierAnalysis` branch + ngspice `.four` parser (через
    interactive `fourier` команду в `.control` блоке, top-level `.four`
    директива не работает с `.control` + `run`).
  - **Phase C**: `ThdSweepSpec/ThdSpectrum` domain VOs + use case
    `analyze_distortion_spectrum` + netlist library substitution helpers.
  - **Phase D**: pilot fixture (PyOM-derived OPT_SE_5K_8 MagneticComponent)
    + acceptance test (6П14П SE + saturable OPT). Изначально
    infrastructure-only closure из-за convergence blocker'а.
  - **Phase E**: **redesign saturable_core с PWL current-source → XSPICE
    gyrator-capacitor (Hamill 1993, `lcouple`+`core`)** — решает algebraic
    loop с EL84 Koren-моделью; pilot acceptance test **проходит**. Scope
    expansion в той же ветке (2026-05-21).
  - **Phase E2**: hexagonal architecture cleanup — FrohlichBHCurve в
    domain, два port'а (`SaturableSubcktGenerator` + `NetlistEditor`),
    use case через ports, lint-imports 3/3 contracts kept.

  **Pilot results** (3×3 sweep): THD @ 1 kHz / 1 W = **9.63%** в band
  [3%, 15%] (revised из [1%, 5%] для compact E 42/15 cores); dominant
  n=2 везде; saturation contribution +4.85 pp (T131 raison d'être
  validated); runtime 0.52 s; PyOM Lp = 50.36 H exact match со static
  lib 50 H. ADR в `DECISIONS.md` 2026-05-21 «Saturable магнетика в SPICE:
  XSPICE gyrator-capacitor».

  **Follow-ups**: T134 в BACKLOG — «Agent Knowledge Base infrastructure»
  с T131 как контрольный пример (3 регрессионных query: lcouple+core
  rule, R_dc_leak requirement, saturation contribution metric).

- **T129** — [closed 2026-05-20, PR #61] **Nonlinear Frohlich-Kennelly
  material model + DC-bias load line — infrastructure-only closure
  (revision 3 после ultrareview).** Phase A (FrohlichBHCurve generator
  + nonlinear `.pro` template) + Phase B (central-diff L_inc 2-solve
  variant + `FemSolveOutcome` DTO + use case integration) + Phase C
  (ADR + relaxed acceptance + BACKLOG forward). T113 Phase 1 pilot
  242% gap **сохраняется** — изначально заявленная «partial closure
  до 70%» оказалась artefact (flux_linkage_per_depth Quantity упускала
  Secondary integral term → возврат half от истинного Ψ, ratio L/L_lin
  ровно 0.499 — math, не physics). После ultrareview bug_001 fix
  ratio L_nl/L_lin = 0.997 (identity within 1%): Frohlich curve не
  engaging в split-coil + 2D-planar setup. Phase A/B остаются как
  **pure infrastructure** для T131 (SPICE saturable transformer,
  reuses Frohlich generator) + T133 (Elmer pivot, native `H-B Curve`,
  полное закрытие 242% gap). End-to-end pipeline сходится без crash
  в `efactory:linux-t129` container; honest failure analysis в
  `DECISIONS.md` 2026-05-20 + ADR revision 3.

- **T125** — [closed 2026-05-20, PR #57] **Fix mypy на main — 64
  ошибки в tests/.** Решение (Vladimir clarify 2026-05-20): не чинить
  по одному, а исключить tests/ из mypy через
  `[[tool.mypy.overrides]] module = "tests.*"; ignore_errors = true`.
  Canonical pre-push gate `uv run mypy src` без изменений; вспомогательный
  `uv run mypy src tests` теперь 0 errors (был exit=2 при path-exclude).
  Pytest runtime валидирует test behavior — runtime-типизация тестов
  не оправдана.

- **T115** — [closed 2026-05-20, PR #58] **CI: build + push efactory:linux
  в GHCR.** GitHub Actions workflow `.github/workflows/build-push-ghcr.yml`:
  на push в main / version tag / workflow_dispatch — cleanup runner disk
  (25 GB toolchains preinstalled на ubuntu-latest), buildx с GHCR registry
  cache (`linux-buildcache` tag), smoke test внутри image (CLI versions +
  `pytest tests/unit`), tag + push c `linux-<sha>` всегда, `linux-latest`
  на main+tags, `linux-<version>` на тагах. Полный ERC/OP/FreeCAD-headless
  smoke — follow-up если pytest не словит regression. Acceptance:
  после первого успешного run `docker pull ghcr.io/vlakir/efactory:
  linux-latest` будет работать с любой машины (репо публичный).

- **T113** — [closed 2026-05-20, PR #56] **FEM-solver: пилот и
  интеграция.** Phase 3 контейнеризации (absorbs T058 FEMM
  bootstrap). Заменяет FEMM (Wine → Linux-native).
  - **Phase 1 pilot** (Stages A→F): сравнительный прогон Elmer FEM
    vs GetDP+Gmsh на OPT 6П14П SE fixture в одноразовом
    `pilot.Dockerfile`. Cross-check Elmer ↔ GetDP **0.00% до
    printed precision** (оба Lp = 23.78 H на linear μ_r=8000),
    расхождение к analytical PyOM ZHANG 6.96 H (242%) — известный
    physics gap (operating-point μ_eff vs constant μ_r), не bug.
    PyOM advisor heavy stress-test через subprocess isolation
    (OOM-safe orchestrator). ADR 2026-05-20 в `DECISIONS.md`
    «Magnetic field verification: GetDP+Gmsh выбран» (заменяет
    pre-pilot ADR 2026-05-19): footprint 45 vs 115 MB, один
    subprocess vs два, штатно в noble universe.
  - **Phase 2 integration** (Stages 2A→2E): hex-архитектура port
    + adapters + use case. `MagneticComponent`/
    `MagneticVerificationResult` domain VO, outbound ports
    `magnetic_analytics` + `magnetic_field_solver` (Protocols),
    `PyOpenMagneticsAnalytics` (analytical), `GetDpFemSolver` (FEM),
    use case `mag_verify_field` (analytical + опциональный FEM
    cross-check). Main `Dockerfile` + apt `getdp` + `gmsh`
    (efactory:linux: 6.65 → 7.31 GB, +310 MB над soft-threshold
    7 GB — отметка для future slimming task).
  - **Spec acceptance ±10% переинтерпретирован:** на pilot fixture
    integration test регрессирует к 242% gap (known physics);
    use case корректно `discrepancy_flagged=True`. Numeric
    closure — BACKLOG T128 (nonlinear B-H curve в GetDP .pro).
    Elmer infrastructure preserved для BACKLOG T127
    (cross-validation на дополнительных fixtures).
  - 12 phase-commits на T113-fem (squash в один при merge).
  - Lessons learned: `feedback_elmer_savescalars_quirks` (4 итерации
    Stage D), `feedback_pyom_advisor_quirks` (5 итераций Stage E).
  Spec: `specs/T113-fem-solver/spec.md`.

- **T112** — [closed 2026-05-20, PR #55] Phase 0.9 Containerization,
  Phase 2 — FreeCAD CLI + GUI + Sheet Metal addon в `efactory:linux`.
  Absorbs T066 (FreeCAD bootstrap).
  - **Variant C — AppImage 1.1.1** (`FREECAD_VERSION=1.1.1`, SHA256
    верифицирован против upstream `*-SHA256.txt`). apt-стек отверг:
    FreeCAD 1.0+ в apt отсутствует (`freecad-stable` PPA на 0.21.2,
    `freecad-daily` — `1.1~pre1` preview-сборка), Sheet Metal apt-
    пакета не существует. ADR — `DECISIONS.md` 2026-05-20.
  - **Dockerfile**: Qt6 runtime deps в base stage (`libxcb-cursor0`,
    `libxkbcommon-x11-0`, `libxcb-icccm4/image0/keysyms1/render-util0/
    shape0/xkb1`, `libegl1`, `libopengl0`, `libnss3`, `libasound2t64`,
    `libxcomposite1`, `libxdamage1`, `libxrandr2`, `libxtst6`); новый
    `freecad-appimage` stage (curl + sha256 + `--appimage-extract` в
    `/opt/freecad/`; `git clone --no-checkout` + `checkout
    8076898be2d8...` Sheet Metal в `/opt/freecad/usr/Mod/SheetMetal/`,
    `.git` удалён); final stage `COPY --from=freecad-appimage` +
    симлинки `freecadcmd` → `/opt/freecad/usr/bin/freecadcmd` и
    `freecad` → `/opt/freecad/AppRun` в `/usr/local/bin/`;
    `COPY scripts/` (для `gen-bracket-demo.FCMacro` внутри образа).
  - **`efactory-up`**: флаг `--demo-freecad` (несовместим с `--demo`,
    проверка); `LAUNCH_BIN` переключается на `freecad` локально;
    bootstrap kicad-libs пропускается в этом режиме (не нужны для
    FreeCAD-only); генератор `bracket.FCStd` запускается через
    `docker run --user $(id -u):$(id -g)` без X11/libs, результат
    через `PROJECTS_DIR` mount попадает на host; usage range
    обновлён `2,48p`.
  - **`scripts/gen-bracket-demo.FCMacro`** — L-bracket через Part API
    (`makeBox` + fuse), сохраняется в `/workspace/sheetmetal-bracket-
    demo/bracket.FCStd`. Расширение `.FCMacro` обязательно:
    `freecadcmd <file.py>` трактует `.py` как document.open (молча
    игнорирует, выходит rc=0 без output). Только `.FCMacro`
    исполняется как Python-макрос.
  - **`scripts/smoke-gui.sh`**: добавлен `freecadcmd --version`
    check (теперь 4 шага: xdpyinfo + kicad-cli + freecadcmd + xeyes).
  - **`tests/integration/test_freecad_runtime_smoke.py`** —
    subprocess smoke: `freecadcmd --version` содержит `FreeCAD
    1.1.1`; Part API через `freecadcmd <macro>` строит `Part.makeBox`
    с volume 1000; `/opt/freecad/usr/Mod/SheetMetal/InitGui.py`
    существует. `skipif` при отсутствии `freecadcmd` в PATH (host-
    окружение Vladimir-а без FreeCAD — тесты skipped, внутри
    образа — 2 passed).
  - **Acceptance**: `docker run efactory:linux freecadcmd --version`
    → `FreeCAD 1.1.1`; полный pytest внутри образа passed (без
    регрессий); `./efactory-up --demo-freecad` открывает FreeCAD
    GUI с L-bracket моделью, **SheetMetal в Workbench-меню**
    (Vladimir подтвердил вручную 2026-05-20).
  - **Размер**: slim 2.45 GB (T111) → 6.65 GB (после T112). +4.2 GB
    (3.1 GB FreeCAD extracted + Docker layer overhead). CONCEPT §13
    «потолок 6 GB» формально превышен, но Vladimir подтвердил
    приемлемость («без планки» 2026-05-20). T115 (CI) добавит pin
    через teги; будущая оптимизация (удаление неиспользуемого
    bundled `gmsh`, `ccx`, `dot` в AppImage) — отдельной задачей.
  - **Out of scope (BACKLOG)**: T124 (freecad-mcp wrapper —
    клиентская часть, не distribution), T125 (mypy fix в tests/ —
    pre-existing regression на main, обнаружен при pre-push T112),
    T115 (GHCR publish), T123 (Sim.Library warning), T122 (KiCad
    libraries git-clone fallback).
  - Spec — `specs/T110-containerization/spec.md` Phase 2 с полным
    implementation note (pin'ы, Qt6 deps, размер, bundled tools
    AppImage как бонус для T113 — `ccx`/`gmsh` уже доступны).

- **T114 + T121** — [closed 2026-05-20, PR #54] Phase 0.9
  Containerization, Phases 4 + 1.5 объединены в один PR
  (variant C, Vladimir 2026-05-19): T114 (`efactory-up` wrapper)
  задаёт runtime entrypoint, T121 (externalize libraries)
  надстраивает library bootstrap внутри него.
  - **T114** (`efactory-up`): wrapper в корне репозитория.
    Pre-flight (docker daemon, $DISPLAY, $XAUTHORITY), узкое xhost
    `+SI:localuser:#$(id -u)` с EXIT trap, persistent state mount'ы,
    projects mount, libs mount, locale pass-through. Флаги: `--pull`
    (обновить efactory:linux), `--version`, `--headless` (CI/pytest
    режим, без GUI mount'ов), `--update-libs` (пересоздать
    $HOME/efactory-libs/), `--with-3dmodels` (опциональный 3D-bootstrap),
    `--demo` (открыть SE-amp фикстуру), `-- ARGS` форвардинг в KiCad.
  - **T121** (libraries externalization): `Dockerfile.libs` собирает
    два tag'а — `efactory-libs:linux-dev` (slim ~450 MB: symbols
    221 MB + footprints 181 MB + templates 5.7 MB) и
    `efactory-libs:linux-dev-3d` (~4 GB: + packages3d 3.2 GB) через
    ARG INCLUDE_3DMODELS. Bootstrap-логика в `efactory-up`:
    `docker create` + `docker cp` 4× subdir → host
    `$HOME/efactory-libs/{symbols,footprints,template,3dmodels}`.
    Runtime per-subdir mount на `/usr/share/kicad/{...}` ro;
    3dmodels mount'ится только при непустой host-директории.
    Сброс user-level sym/fp-lib-table при первом bootstrap для
    re-init из system default (фиксит residual broken state от T111).
  - Удаление `scripts/run-kicad.sh` (subsumed by `efactory-up`);
    обновление `scripts/gen-se-amp-demo.py` output и README
    («Запуск KiCad GUI из контейнера» переписана с таблицей
    mount'ов).
  - **Out of scope T114+T121 (BACKLOG):** GHCR publish (T115),
    fallback git clone (T122), KiCad Sim.Library warning suppress (T123).
  - Spec — `specs/T110-containerization/spec.md` Phases 4 + 1.5,
    дополнено implementation note про combine variant C, split
    slim/3D и deferred items.
  - Acceptance: `./efactory-up` с чистого host'а → KiCad GUI с
    Symbol Library Browser, видящим Device/power/Valve/etc.
    `--update-libs` идемпотентен. `--headless` — 587/8 skipped,
    coverage 87.29% (== T111 baseline). Slim image 2.45 GB
    (acceptance ≤ 3 GB выполнен T111). Vladimir прогнал
    Simulator на SE-amp demo — `.tran` отрабатывает.

- **T111** — [closed 2026-05-19, PR #53] Phase 0.9 Containerization,
  Phase 1 — KiCad GUI passthrough из контейнера на хост через X11.
  Расширение final stage: apt-runtime `x11-apps`, `x11-utils`,
  `libgl1`, `dbus-x11`, `xauth`, `mesa-utils`,
  `libcanberra-gtk3-module`, `locales` (`ru_RU.UTF-8` + `en_US.UTF-8`
  сгенерированы). `ENV NO_AT_BRIDGE=1` + `LANG=C.UTF-8` default;
  `LANG/LC_ALL/LANGUAGE` пробрасываются из host. Один образ
  `efactory:linux` (без `-headless` split — разделение в T120/T121).
  Persistent state mount'ы для KiCad: `$HOME/efactory-state/
  {config,cache,local}` → `/opt/efactory/.{config,cache,local}`
  (setup wizard выполняется один раз). Wrapper-скрипты для ритуала
  ручной проверки: `scripts/run-kicad.sh` (запуск GUI из контейнера
  с `xhost +SI:localuser:#$(id -u)` + state mount'ы + locale
  pass-through + опциональный `--demo` mount $HOME/efactory-projects/),
  `scripts/gen-se-amp-demo.py` (материализует SE-amp 6П14П
  acceptance-фикстуру в `$HOME/efactory-projects/se-amp-demo/`
  с относительными `Sim.Library`-путями и минимальным `.kicad_pro`
  для Simulator). Smoke-script `scripts/smoke-gui.sh`: X11
  connectivity (`xdpyinfo`) + `kicad-cli version` + `xeyes`
  end-to-end. Spec — `specs/T110-containerization/spec.md` Phase 1,
  дополнено implementation note про deferred split и Wayland
  (XWayland-bridge работает, native Wayland mount пока не нужен).
  Image: 2.45 GB (+~30 MB на locales+canberra vs. T110 Phase 0).
  pytest 587/8 skipped, coverage 87.29% — без регрессии.
  **Known limitation, deferred to T121:** в образе нет
  `kicad-symbols/footprints/packages3d` — Symbol Library Browser
  показывает «библиотека не найдена». Inline `lib_symbols` (T100)
  обеспечивает рендеринг конкретного `.kicad_sch` и Simulator;
  броузер UI-сценарии закроет T121 (externalize libraries).

- **T110 Phase 0** — [closed 2026-05-19, PR #52] Phase 0.9
  Containerization, Phase 0 — базовый Dockerfile `efactory:linux-
  headless`. Multi-stage build: Ubuntu 24.04 LTS base + KiCad 10 (PPA
  `kicad/kicad-10.0-releases`) + ngspice → python-deps (uv + venv 3.14
  в `/opt/efactory/.venv`) → efactory-code (editable install) → final.
  Size: 2.43 GB (≤ 6 GB потолок). `docker run pytest` — 587 passed,
  8 skipped, coverage 87.29% (host: 593/2 — разница на AppImage-
  skipif'ах, очистка в T120). Закрыты C1 (venv permissions) и C3
  (user-agnostic mount paths: `/efactory/.claude/`, `/workspace`,
  `/libs`, `HOME=/opt/efactory`). Pre-push hook (ruff/format/mypy/
  lint-imports/pytest) — все зелёные. Spec —
  `specs/T110-containerization/spec.md` Phase 0. Следующие фазы (T111
  GUI passthrough, T112 FreeCAD, T113 FEM, T114 wrapper, T115 CI,
  T120 cleanup, T121 externalize libs) — отдельные PR.
- **T107 Phase 0** — [closed 2026-05-19, PR #46] Custom Soviet tube
  snippets: `Tubes_Soviet:GU50/6P45S/6N6P` через copy-rename базовых
  EL84/ECC81 форм. 3 demo фикстуры (`test_soviet_tubes_facade.py`)
  — common-cathode amp для каждой лампы, ngspice gain 20×/14×/227×.
  Phase 1 deferred — datasheet-accurate vector drawing (top-cap GU50,
  beam tetrode 6П45С, octal 6Н6П) с возможной LLM-vision delegation.
  Bug-fix mini-discovery: KiCad требует sub-unit names = parent name
  (initial "N6P_X_Y" не работал, fixed "6N6P_X_Y").
  593 passed (+3), coverage 87.99%.

<!-- Записи T103, T101, T105 Phase 0, T004b, T005 Phase 0, T104
     перенесены в CHANGELOG.md → [0.5.0] release-PR (2026-05-19). -->

<!-- Записи T010, T009, T006, T007, T004, T008, T100, T102 перенесены
     в CHANGELOG.md → [0.4.0] release-PR. -->

<!-- Записи T093, T095, T096, T097, T098, T099 перенесены в
     CHANGELOG.md → [0.3.0] release-PR. -->
