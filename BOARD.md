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




## Done

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
