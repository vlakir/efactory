# Changelog

История заметных изменений. Формат — упрощённый
[Keep a Changelog](https://keepachangelog.com/).

Записи группируются по версиям или датам релизов. Для проектов без
формального версионирования допустимо использовать дату как заголовок.

Категории:
- **Added** — новая функциональность.
- **Changed** — изменения в существующей функциональности.
- **Fixed** — исправления багов.
- **Removed** — удалённая функциональность.
- **Deprecated** — то, что помечено к удалению, но пока работает.
- **Security** — изменения, важные с точки зрения безопасности.

Если изменение связано с задачей из `BOARD.md` / `BACKLOG.md`,
запись **обязательно** содержит T-ID в скобках, например:
`Added: Превью постов в Telegram (T<NNN>).` Это сохраняет уникальность
T-ID между релизами — `CHANGELOG.md` единственное persistent-
хранилище номеров завершённых задач (см. правило нумерации
в `README.md`).

---

## [Unreleased]

<!-- Здесь накапливаются изменения, которые войдут в следующую
     версию `[N.M.0]`. При закрытии milestone — переименовывается
     в очередную версию, ниже создаётся новая пустая `[Unreleased]`. -->

---

## [0.6.0] — 2026-05-19

Шестой milestone: **финальная зачистка Phase 1a deferred задач**.
Vladimir дал autonomous batch mandate "закрывай всё, что осталось до
Phase 1b" — за сессию закрыто 4 PR: T004b/T005 Phase 1, T105 Phase 1
(partial), T094 ADR, + release cut. **BACKLOG чистый до Phase 1b.**

После 0.6.0:
* edit-model CLI (swap SPICE-модели для tube/diode/transformer
  компонента);
* bridge_sweep — parametric OP-runs по Cartesian product;
* atomic multi-edit с rollback (SchematicSnapshot);
* multi-unit dual-triode instancing (Valve:ECC81B/83B/88B);
* ECC83 self-contained (без `(extends ...)` mechanism);
* CodeRabbit формально trактуется как best-effort signal — primary
  review = Гвидо self-review + опциональный `/ultrareview`.

Готовность к **Phase 1b — LLM chat-client (T011-T016)**. Все primitives
готовы:
* programmatic schematic build (T100/T104/T105 facade с pretty symbols),
* SPICE simulate (T008 ngspice),
* edit-and-resim flow (T004b/T005),
* model search/assign (T005, T101).

### Added

- **T004b/T005 Phase 1 — bridge edit-model + bridge_sweep +
  SchematicSnapshot.** `application/edit_component_model.py` — swap
  SPICE-модели через atomic multi-property text-replace (`Value` +
  `Sim.Library` + `Sim.Name`). `application/bridge_sweep.py` —
  parametric OP-sweep по Cartesian product (hexagonal: exporter +
  simulator через DI, domain VO `SweepRun`). `application/
  schematic_snapshot.py` — context manager для atomic multi-edit с
  rollback. CLI: `bridge edit-model`, `bridge sweep`, `bridge edit`
  обёрнут в snapshot. (T004b, T005 Phase 1)

- **T105 Phase 1 (a)+(c) — multi-unit dual-triode + ECC83 self-contained.**
  Registry расширен: `Valve:ECC81B/ECC83B/ECC88B` (unit 2 aliases с
  таким же `lib_id`). `Valve:ECC83` теперь self-contained snippet
  (без `(extends ...)` — Phase 0 attempt не работал). Writer fix:
  `(unit N)` в `(instances)` блоке теперь dynamic вместо hardcoded `1`.
  Demo: cascaded 2-stage preamp на 6Н2П с обеими halves ECC83 (X1+X2
  same lib_id, different units), gain 2920×. (T105 Phase 1)

### Changed

- **T094 ADR — sтранние review-боты переформулированы как best-effort
  signal.** CodeRabbit integration остаётся подключённой, но silent
  rate-limit / no-credits не блокирует merge. Primary review path —
  Гвидо self-review с 7-point checklist + опциональный `/ultrareview`
  для архитектурно-критичных PR'ов. ADR в `DECISIONS.md` фиксирует
  решение (вариант "в" из BACKLOG T094). Закрывает повторяющийся ныть
  ретро `[0.2.0]/[0.4.0]/[0.5.0]`. (T094)

### Retrospective

**Что зашло:**

- **Autonomous batch mode под Vladimir's "закрывай всё что осталось"
  mandate** — за одну сессию (Vladimir отлучился на ~3 hours) закрыто
  4 task PR + 1 release-PR. Не первый раз pattern работает: scope
  очерчен (всё deferred в Phase 1a section + T094), gates автоматичны,
  каждый PR self-contained.
- **Honest Phase split с явным deferred** — T105 Phase 1 был split:
  (a) ECC83 self-contained ✓, (c) multi-unit dual-triode ✓, (b) custom
  Soviet snippets → парковка в T107 (Phase 3, drawing-heavy). Не
  «когда-нибудь сделаем», а конкретно identified task с acceptance.
- **Re-use of existing primitives** — bridge_sweep = шаблон
  edit_component_value + design_to_sim. edit_component_model =
  edit_component_value + multi-property pattern. Реализация быстрая,
  potтому что foundation уже устоявшийся.
- **Pre-push гейты ловили все regression** автоматически (включая
  hexagonal violation в первой попытке bridge_sweep с adapter
  imports — `lint-imports` отловил).

**Что не зашло (или потребовало переделки):**

- **Initial bridge_sweep попытка нарушала hexagonal contract** —
  application импортировал adapters (KicadCliSchematicExporter,
  NgspiceSimulator). `lint-imports` отловил в первом push, refactor'нул
  на DI (exporter+simulator pass-through). **Урок:** новые use cases
  должны принимать porty через DI, не создавать adapters сами.
- **Writer hardcoded `(unit 1)` в `(instances ...)` блоке** — баг
  T104 (я в T104 patched первую `(unit N)` line, но `(instances)`-
  level осталась `1`). Обнаружено только в T105 P1 multi-unit test
  (count assertion). **Урок:** при `replace_all` для multiple
  occurrences проверять ВСЕ matches, не первую попавшуюся пару.
- **Custom Soviet snippets (GU50/6П45С/6Н6П)** — drawing-heavy work,
  пришлось honestly defer в T107 (Phase 3). Не блокирует Phase 1b
  но висит. Не имеет smart-way fix — нужно рисовать vector полилинии
  по datasheet pinout. Возможно с помощью LLM-vision при T032/T106
  Phase 3 implementation.

**Правки методики (внесены / актуализированы):**

- **`/ultrareview` как primary external review** (T094 ADR) — заменяет
  пассивный CodeRabbit polling. Vladimir-triggered, выборочно.
- **Phase split pattern продолжает работать** — Phase 0 + Phase 1
  deferred + Phase 2-3 backlog. Применено к T100/T103/T104/T105/T106.
  Закрепляется как methodology для крупных задач.
- **DI для application use cases** — hexagonal contract обязательно
  через `lint-imports` (existing rule, applied более последовательно).

**Технический долг и идеи для 0.7.0:**

- **Phase 1b — LLM chat-client (T011-T016)** — следующая большая фаза.
  Все primitives готовы, нужен полный ритуал spec/clarify/analyze.
  Vladimir будет делать spec вручную (новая подсистема, новый stack:
  Rich TUI + MCP client + tool-use loop).
- **T106 (scheme layout beautifier)** — Phase 3, после T032 SVG
  render. Phase 0 (label-collision detection) — quick win если в
  свободные часы.
- **T107 (custom Soviet snippets GU50/6П45С/6Н6П)** — drawing-heavy.
  Возможно делегировать LLM-vision при T032 готовности.
- **`uv build` smoke в pre-push** (накопленный долг с [0.4.0]).
- **Mistake recovery automation** (gpr branch-start alias) — не сделано
  с retro `[0.5.0]`. Стоит закрыть при следующем меthod-improvement PR.

---

## [0.5.0] — 2026-05-19

Пятый milestone: **Phase 1a follow-ups доведены до production-ready**
(минус parked T002/T003 bootstrap-скриптов). [0.4.0] закрыл фундамент
Phase 1a MVP-ядра; [0.5.0] доводит follow-up-задачи, обнаруженные в
процессе, плюс расширяет registry/library и добавляет primitive
edit-resim workflow.

После 0.5.0 efactory:

- умеет рендерить ламповые усилители с **реальными ламповыми
  symbols** (4 valves в registry + 6П14П common-cathode demo с
  правильным rendering);
- имеет SPICE-библиотеку диодов (3 стартовых + framework для
  расширения);
- закрыл W2 wire-routing risk в SE-amp (gain 48.5×);
- даёт **bridge edit** CLI для модификации .kicad_sch + composable
  Python use case для edit-and-resim flow (готов для LLM-агента
  Phase 1b);
- расширил SpiceModelLibrary list-команды composable фильтрами
  (`--source X --subcategory Y`).

Готовность к Phase 1b LLM chat-client (T011-T016) — следующий
milestone.

### Added

- **T101 — Diode SPICE-библиотека** (расширение T007 generalization).
  `domain.ComponentCategory.DIODE` + `DiodeKind` enum (rectifier/
  signal/schottky/zener/led); `SpiceModelLibrary` сканирует
  `data/models/diodes/<source>/`; стартовый набор `duncan/`:
  1N4007 (rectifier 1000V/1A), 1N4148 (signal 100V/200mA, fast
  switching trr 4ns), BAT85 (schottky 30V/200mA, low Vf). CLI
  `efactory diode list/show`. `facade.add_diode` поддерживает
  `spice_model=...` (X-prefix subckt-instance, auto `.include`) и
  legacy `spice_params='...'` (D-prefix inline); hardcoded default
  (T100 Phase 1) удалён, ValueError на отсутствие обоих.
  Backward-compat — rectifier test работает без правок. (T101)

- **T103 — SE-amp wire-router fix** (закрывает T100 W2 risk
  realized в T102). Полностью переписан SE-amp layout с
  использованием T104 `Valve:EL84` symbol. Plate-к-OPT.P1 wire идёт
  ВЫШЕ B+ rail (Y=67.31 < Y=58.42 в mm), что исключает все
  пересечения с G2/P2 rail-stub'ами. `.tran 10u 80m uic` для
  надёжного bias settling. `test_facade_se_amp_tran_shows_amplification`
  снят со skip, измеренный plate AC swing **48.5×** от input
  (threshold ≥5×). Speaker swing 39 mV p-p после OPT 25:1 step-down.
  ERC: 0 errors. (T103)

- **T105 Phase 0 — extend Valve registry** на 4 valves (с EL84):
  - `Valve:ECC81` (12AT7 dual-triode) — для 6Н1П, 6Н2П, 6Н3П
  - `Valve:ECC88` (6DJ8 dual-triode) — для 6Н23П, 6Н1П alt
  - `Valve:EC92` (single triode) — для 6Ж1П etc
  - `Valve:EL84` (pentode, T104) — для 6П14П
  
  Dual-triodes используются только unit 1 (½), что соответствует
  ½-modeled T006 SPICE моделям (3-pin: P/G/K). Writer
  `_collect_lib_symbols` с topological sort + auto-load parent через
  `(extends ...)` — infrastructure готова для derived symbols, но
  KiCad pin resolution для derived требует доработки (T105 Phase 1
  deferred). Demo: 6Н2П common-cathode amp через Valve:ECC81,
  ngspice TRAN gain ≥ 10×. (T105 Phase 0)

- **T004b + T005 Phase 0 — bridge edit + model search filters.**
  `application/edit_component_value.py` — atomic text-based regex
  replace value-property компонента в `.kicad_sch` (защита:
  ComponentNotFoundError, MultipleMatchesError на duplicate refs).
  `application/edit_and_resim.py` — composition edit + design_to_sim
  для Python use case (LLM-agent ready). CLI
  `bridge edit <project> --schematic PATH --set REF=VALUE`:
  multi-edit через repeated `--set`, per-edit atomic, session-logged.
  T005 Phase 0: `tube/diode/transformer/load list` принимают
  `--source X --subcategory Y` для composable фильтрации (model
  search functional). (T004b, T005 Phase 0)

### Changed

- **T104 follow-ups (closure):** Phase 0 PR (#35) уже мержён в
  [0.4.0]; здесь дополнительные правки `chore(backlog)` PR #36 —
  T002/T003 parked в новый раздел Tech Debt (Vladimir explicitly не
  готов брать), T105 формально registered в Phase 1a.

### Retrospective

**Что зашло:**

- **Autonomous batch mode.** Vladimir дал команду "добить Phase 1a"
  на ночь — за сессию закрыто **5 task PR + 1 chore + 1 release-PR
  open** (~7 commits в main). Pattern работает когда scope очерчен
  (закрытые задачи в BACKLOG + явные acceptance criteria).
- **Phased delivery** (Phase 0 / Phase 1 split) для крупных задач
  (T105, T004b/T005) — закрываем essentials, остальное honestly
  паркуется как "Phase 1 deferred" с явными criteria. Не "потом
  доделаем как-нибудь", а конкретный todo с scope.
- **Re-use existing infrastructure.** T004b/T005 = текстовый regex
  edit + filter в существующих CLI commands. Не пришлось вводить
  новый MCP-server, schematic parser или sweep-domain (всё это
  отложено к Phase 1 deferred / Phase 1b).
- **Pre-push гейты** ловили все regression сразу — backward compat
  T101 (rectifier test без правок) и T103 (старые T100 фикстуры)
  подтверждены автоматически без manual smoke.

**Что не зашло (или потребовало пересмотра):**

- **Закоммитала на main ошибочно** перед push T105 (создала ветку
  ПОСЛЕ commit, а не до). Push fail'ил (нет такой ветки), remote
  не пострадал — recovery: `git branch <name>` + `git reset --hard
  origin/main`. **Урок методики:** перед каждым новым task —
  *first* `git checkout -b T<NNN>-<slug>`, ТОЛЬКО потом редактирование.
  Если есть автоматизация — добавить shell-аlias или git hook
  блокирующий commit в main для non-chore изменений.
- **ECC83 `(extends ECC81)` mechanism сложнее ожиданий.** Embed
  ECC83 derived → pins NC, хотя ECC81 (parent) напрямую работает.
  KiCad pin resolution для extends-symbol требует ещё чего-то
  (Phase 1 investigation). Decision был honestly defer — T105 Phase
  1 deferred в BACKLOG. **Урок:** при первой встрече с unfamiliar
  KiCad mechanism — pre-spike перед coding (как с T100
  `kicad-sch-api`), не coding-then-debug.
- **Multi-unit valves stripped к unit 1** — приводит к
  `lib_symbol_mismatch` cosmetic warning (наш embedded ≠ system
  Valve.kicad_sym из-за вырезанного накала). 4 из 4 новых valves
  выдают этот warning. Pragmatic accept; full fix = multi-unit
  instancing с NC markers (T105 Phase 1).

**Правки методики (внесены / актуализированы):**

- **Phase split pattern** для крупных задач — Phase 0 (essentials) +
  Phase 1 deferred (advanced) в BACKLOG. Закрепляется как
  workflow для autonomous batch. Pre-existing precedent: T100
  Phase 0–3, T104 Phase 0.
- **Tech Debt секция в BACKLOG** — задачи parked без owner (T002/
  T003 пока). Не путать с архитектурными follow-up'ами (T094) —
  те имеют clear motivation, просто откладываются. Tech Debt = "
  признаём что нужно, но не сейчас".
- **`chore(backlog)` methodology PRs без T-ID** — продолжает
  работать. Применено в backlog reorg PR #36.

**Технический долг и идеи для 0.6.0:**

- **T103/T104/T105 Phase 1** (все pushed back deferred):
  - SE-amp facade wire-router auto-junction для chuжих pin-crossings
    (≤50 LOC, T100 §Analyze W2 mitigation, accepts T103 partial fix).
  - `(extends ...)` pin resolution для derived Valve symbols.
  - Custom snippets для уникальных советских ламп без western
    аналога (GU50, 6П45С, 6Н6П).
  - Multi-unit dual-triode instancing (отдельные halves через
    unit-A/B sub-references).
- **T004b/T005 Phase 1 (deferred)**: bridge_sweep parametric +
  delta-table, model_assign CLI (Sim.Library/Sim.Name swap),
  snapshot/rollback multi-edit atomicity.
- **T011-T016 (Phase 1b — LLM chat-client)**: следующая большая
  фаза. Все primitives готовы: edit_and_resim, model_search,
  programmatic schematic build. Требует spec/clarify/analyze.
- **T094** (CodeRabbit credits) остаётся parked — кончились на
  release-PR [0.4.0] (#34).
- **`uv build` smoke в pre-push** (накопленный долг с [0.4.0]).
- **Mistake recovery automation:** git pre-commit hook блокировать
  non-chore commit в main; alias `gnb <name>` (=`git checkout -b
  T<NNN>-<name>`) для quick branch start.

---

## [0.4.0] — 2026-05-18

Четвёртый milestone: **закрыто Phase 1a MVP-ядро дорожной карты
CONCEPT §13**. После 0.3.0 domain-фундамент был готов принимать
реальные bridge'и; в 0.4.0 они построены сверху донизу — от
git/session-log инфраструктуры до программной сборки `.kicad_sch` через
Python API и реального прогона ngspice.

После 0.4.0 efactory умеет:

- инициализировать проект с git и structured session log
  (`<session_root>/<session_id>/log.jsonl`);
- находить KiCad / FreeCAD / ngspice на любой Linux-машине
  (env → `which` → `.desktop` → known paths → AppImage fallback);
- собирать tube / transformer / load SPICE-модели из библиотеки
  (T006 база 50+ ламп, T007 generic transformer/load);
- программно строить `.kicad_sch` через фасад `efactory.schematic`
  (без `kicad-sch-api`, поверх `sexpdata` — вариант D из ADR T100);
- экспортировать SPICE-netlist через `kicad-cli sch export netlist`
  и прогонять `ngspice -b` с реальным OP / TRAN / AC анализом;
- весь pipeline покрыт integration-тестами с реальными KiCad и
  ngspice.

Domain не понадобилось трогать на этом milestone — hexagonal-фундамент
0.1.0/0.3.0 принял 8 новых задач без правок (только расширения).

### Added

- **`efactory.schematic` programmatic schematic facade (T100).**
  Внутренний фасад поверх `sexpdata` для построения `.kicad_sch` в
  KiCad 10 формате. Реализация в 5 фазах: Phase 0 — RC reproducer
  (R/C/V_DC/Ground/Wire); Phase 1 — Diode/Inductor/V_AC + half-wave
  rectifier; Phase 2 — BJT/MOSFET + tube/transformer subckt через
  T006/T007 + SE-amp 6П14П; Phase 2 follow-up — grid-align,
  wire-based layout, GUI-runnable; Phase 3 — ADR T100 + удаление
  ручной фикстуры `tests/fixtures/rc_filter.kicad_sch` (строится
  через фасад в `tests/conftest.py`). Hexagonal: port
  `ports.outbound.schematic_writer.SchematicWriter` + adapter
  `KicadSchematicWriter` + domain VO в `domain.schematic`. 14
  embedded `lib_symbols` snippets (Device.R/C/L/D, Q_NPN/PNP/NMOS/
  PMOS, Simulation_SPICE.VDC/VSIN, Connector_Generic.Conn_01x04,
  power.GND/PWR_FLAG) — `.kicad_sch` self-contained, не зависят от
  `KICAD_SYMBOL_DIR`. Pre-spike отверг `kicad-sch-api` 0.5.6 как
  несовместимую с KiCad 10 `*.kicad_symdir/` (binary per-symbol)
  + 78 транзитивных deps с MCP-балластом. ADR T100 фиксирует
  выбор D + альтернативы A/B/C/E + план миграции на KiCad 11/12.
  Acceptance: 4 фикстуры (RC, rectifier, common-emitter BJT, SE-amp)
  ERC=0, netlist валидный, ngspice OP/TRAN/AC ожидаемо. Coverage на
  `schematic_kicad/`: facade 97%, writer 100%, `domain.schematic`
  100%. (T100)

- **Реальный ngspice OP / TRAN / AC (T008).** SPICE-симуляция через
  `NgspiceSimulator` (subprocess + ASCII raw parser). Domain:
  `AnalysisSpec = Op | Tran | Ac` (pydantic discriminated union),
  `TimeSeries` / `AcSweep` VO, `SimulationResult` с invariant «ровно
  одна ветвь». Port `Simulator.run(netlist, analysis, *,
  timeout_seconds=60.0)`. Adapter
  `src/adapters/outbound/ngspice/` (simulator + wrapper с `GND → 0`
  substitution + raw parser); `StubSimulator` удалён. CLI:
  `bridge design-to-netlist` + 3-уровневая typer-иерархия
  `bridge sim-run {op,tran,ac}` и `bridge design-to-sim {op,tran,ac}`.
  SPICE-суффиксы (`1k`, `1.5Meg`, не путает `m` с `Meg`).
  E2E acceptance на RC-фильтре: OP `|V|≈1V`, TRAN steady DC, AC
  `|H(fc)|≈0.707` на fc=159 Hz. Reality-check уроки T008 ушли в
  auto-memory: Y-down convention, ground через power-symbol с
  substitution, KiCad SPICE pin-order quirk. (T008)

- **KiCad → SPICE pipeline (T004).** `KicadCliSchematicExporter`
  через `kicad-cli sch export netlist --format spice` (T009
  app_manager.run KICAD_CLI; pragmatic exit code: success если
  netlist реально создан, exit 2 для warnings OK). Domain:
  `Simulation` (id, project_id, schematic_path, netlist_path,
  status, created_at, result), `SimulationStatus`,
  `SimulationResult`. Ports `SchematicExporter` + `Simulator` +
  контрактные exceptions
  (`SchematicExportError` / `SimulatorUnavailableError` /
  `SimulationFailedError`). Application use case `design_to_sim`:
  get_project → resolve paths → mkdir sim → export → simulator
  (catch `SimulatorUnavailableError` → status=`NETLIST_READY`).
  CLI: `bridge design-to-sim <project> --schematic PATH
  [--netlist-output PATH]` + session-log `bridge.design_to_sim`.
  Split-scope: ngspice вынесен в T008. (T004)

- **Tube SPICE model library framework (T006).**
  `domain.SpiceModel` (id, name, tube_type, source, file_path,
  subckt_pins) + enums `TubeType` / `ModelSource`. Outbound port
  `TubeModelLibrary` + `FilesystemTubeModelLibrary` adapter:
  scan `data/models/tubes/{koren,ayumi,duncan,custom}/*.{lib,inc,
  cir}`, парсинг `.SUBCKT` header + `tube_type` detection (header
  override или pin-count fallback), id = uppercase filename stem.
  Конвертер `convert_ayumi_to_ngspice` (`^ → **`) применяется на
  read_subckt для Ayumi. CLI `efactory tube list/show`. Built-in
  ламповая библиотека — ~50 моделей (7 Koren + 2 Ayumi + 4 советских
  + 37 расширение): triodes, pentodes, dual_triodes, rectifiers.
  User overlay через `<user_library_root>/`. (T006)

- **Generic SPICE-модели transformers + loads (T007).**
  Generalization T006: `ComponentCategory` (tube/transformer/load)
  + `SpiceModel.subcategory` (str) с typed accessors `@property`
  (`tube_type` / `transformer_kind` / `load_kind`) и category-guard.
  `TubeType` расширен `RECTIFIER`. Adapter rename
  `TubeModelLibrary → SpiceModelLibrary` (port +
  `FilesystemSpiceModelLibrary`); scanning
  `<root>/<category>/<source>/`. Универсальный header
  `* subcategory:` + legacy `* tube_type:` backward compat.
  Pin-эвристика только для tubes; transformer/load без header →
  `SpiceModelInvalidError`. Settings (breaking): `library_root` +
  `user_library_root`. CLI: 3 subapp (`tube` / `transformer` /
  `load`). Data: `OPT_SE_5K_8`, `OPT_PP_6K6_8`, `SPEAKER_8OHM`
  (с mech. резонансом), `SPEAKER_4OHM`, `DUMMY_LOAD_8R`. (T007)

- **`platform_layer` + `app_manager` (T009).** Фундамент для
  bridges Phase 1a: `domain.ApplicationKind` (kicad / kicad-cli /
  freecad / femm / ngspice) + `Status` / `OsKind` / `Info`.
  `NativePlatformLayer`: 5-step resolution chain (env → `which`
  → `.desktop` → known paths → KICAD_CLI fallback через KiCad
  AppImage); поддержка AppImage в `~/kicad/`, `~/Загрузки/`,
  `~/Applications/`, etc. `SubprocessAppManager`: unified `run`
  (blocking `subprocess.run` для headless) + `launch` (Popen detach
  для GUI) + `stop` (TERM→5s→KILL) / `restart`, in-memory PID
  registry. CLI `efactory app status / launch / run / stop /
  restart` + session-log. Live smoke: KiCad+FreeCAD AppImage
  найдены, `efactory app run kicad-cli -- --version` → 10.0.2.
  Methodology lesson: изначально предположил «KiCad нет на машине»,
  Vladimir поправил → auto-memory `feedback_check_environment.md`:
  проверять окружение через `command -v` + `.desktop` + AppImage в
  `~/`/`~/Загрузки/`, не угадывать. (T009)

- **Phase 1a opener: git init + structured session log (T010).**
  Auto-init git repo + initial commit при `project create` (без
  GPG, без зависимости от глобального git-config); structured
  session log в `<session_root>/<session_id>/log.jsonl`. Новые
  outbound ports `GitRepository` (subprocess adapter с env-override
  AUTHOR/COMMITTER и `--no-gpg-sign`) и `SessionLogger` (filesystem
  JSONL, best-effort, `ensure_ascii=False`). `Settings.session_root`
  + `EFACTORY_SESSION_ID` env override (для группировки CLI команд
  в одну сессию — пригодится chat-client'у Phase 1b).
  `CreateProjectResult{project, git_initialized}` — application
  слой не знает про логирование (N9 separation). CLI helper
  `_log_command[T]` оборачивает все 9 команд (project.* +
  decision.*). (T010)

### Changed

- **Tube .lib `PWRS()` → ngspice-native `sgn()*pwr(abs(), )` (T102).**
  Все 14 custom tube .lib (`6P14P`, `6N1P`, `GU50`, `GM70`, ...) в
  `data/models/tubes/custom/` переписаны на чистый ngspice-синтаксис
  через `convert_pwrs_to_ngspice` (char-парсер с балансом скобок,
  рекурсия на PWRS-в-PWRS, идемпотентна) + one-shot
  `scripts/patch_tubes_pwrs.py` (14 patched / 3 clean). Ngspice 45
  без `--compatibility-mode=psa` теперь корректно парсит модели.
  Smoke `.op` на патченном 6N1P в diode-mode не валится с
  `'pwrs'`-ошибкой. Альтернатива `ngspice --compatibility-mode psa`
  отвергнута без ADR (это data-fix, не архитектурный выбор).
  Symmetry: `scripts/` добавлен в `[tool.ruff] exclude` (dev-tooling
  outside production, симметрично с `tests/`). (T102)

### Retrospective

**Что зашло:**

- **Pre-spike перед спекой T100** (~30 минут с `kicad-sch-api` 0.5.6
  на нашем `rc_filter.kicad_sch`) спас от форка чужой библиотеки
  или недели возни с binary `*.kicad_symdir/`. За один сеанс стало
  ясно — вариант D (собственный фасад поверх `sexpdata`) единственный
  sensible. **Урок:** для задач, где принципиально «насколько хорошо
  готовая библиотека покрывает наш use case» — pre-spike обязателен
  до spec, не после.

- **Phased delivery T100** (Phase 0/1/2/3, каждая = одна сессия,
  каждая = отдельный коммит) держала scope узко. Phase 0 (RC
  reproducer) был **рефакторингом** hardcoded → API, не дизайном
  с нуля — это ключевой move scope discipline. Кто-то ходил в
  «давай заодно сделаем SE-amp в Phase 0» — кто-то это я, и
  spec явно сказала «нет», и мы устояли.

- **TDD outside-in** в каждой фазе: e2e тест («facade → save →
  kicad-cli erc → netlist → ngspice OP → assert |V|≈1V») сначала
  красный, потом реализация делает зелёным. Очень предсказуемый
  поток без эмоций.

- **Embedded `lib_symbols` snippets** в адаптере (force-include в
  wheel) — .kicad_sch получились self-contained. На любой машине
  с KiCad 10 открываются без сюрпризов от глобальной
  `KICAD_SYMBOL_DIR`. Подсказка для будущего: data inline ≥
  cache-dependence.

- **T102 = чистая симметрия с T006 Ayumi.** Одна функция в
  существующем `conversion.py` + тонкий one-shot script. Не
  пришлось вводить новый module или ADR. Когда есть симметричный
  прецедент в codebase — следуем ему, не изобретаем заново.

**Что не зашло (или потребовало пересмотра):**

- **W2 risk realized.** В T100 Phase 2 SE-amp tube TRAN-тест был
  под `@pytest.mark.skip` из-за PWRS-блокера (T006 PSpice-формула,
  закрывался отдельной задачей). Это означало: W2-мониторинг
  (wire-router пересекает чужие pin'ы → KiCad merg`ит net'ы) был
  не проверен фактически. Acceptance Phase 2 был partial — «netlist
  содержит XV1 + .include», а не «ngspice реально прогоняет».
  T100 закрыт с этим долгом. В T102 при `unskip` сразу всплыло:
  `/plate` слил `tube.P + tube.G2 + OPT.P1 + OPT.P2 + V_B+`.
  Layout-фикс пришлось вынести в T103. **Урок:** когда Analyze
  пишет Warning Mitigation — проверять его в integration перед
  закрытием task. «Netlist содержит ожидаемые имена» ≠ «реально
  работает». Skip от стороннего блокера маскирует риски,
  обозначенные в Analyze.

- **Acceptance T102 был зависим от стороннего блокера.**
  Формулировка «SE-amp test снят со skip и проходит» содержала
  implicit assumption «нет других блокеров кроме PWRS». В реальности
  оказалось два блокера (PWRS + W2), acceptance переформулирован в
  процессе. **Урок:** acceptance должен мериться через объект,
  который задача меняет напрямую (для T102 — конвертер + ngspice
  не валится на subckt-parse), а не через сторонний test,
  завязанный на другие подсистемы. Проверка «снят со skip и
  проходит» — антипаттерн, если skip-причина не была единственным
  блокером.

- **GUI verification step (`feedback_kicad_fixtures`)** перед merge
  T100 формально проведён, но я интерпретировала Vladimir-овское
  «поехали дальше» как подтверждение GUI без явного запроса.
  Это могло быть тёмное казино — мог сказать «merge не глядя».
  **Урок:** явно спрашивать «открыл в GUI? всё ок?» перед merge,
  не интерпретировать общий гудок. Особенно если есть feedback-
  правило, требующее manual step.

- **`uv build` не прогонялся** ни в T100, ни в T102. force-include
  путей wheel-target (`src/.../lib_symbols` → `adapters/.../
  lib_symbols`) проверены только косвенно через `pytest` (который
  использует source-layout, не wheel). Если кто-то соберёт wheel —
  возможны сюрпризы. Не критично сейчас, но в release-checklist
  добавить smoke `uv build && unzip -l dist/*.whl | grep
  lib_symbols`.

**Правки методики (внесены по ходу):**

- **`scripts/` в `[tool.ruff] exclude`** (T102) — структурное
  исключение типа dev-tooling файлов (симметрия с `tests/`), не
  расширение `[tool.ruff.lint] ignore`-правил и не `noqa` per-line.
  Если появится новая категория dev-tooling — следуем тому же
  паттерну. Зафиксировано прозрачно в commit-message + PR
  description + self-review; согласовано с Vladimir до merge.

- **Closing-правка BOARD после `gh pr create`** (`Doing → Done`
  с реальным `PR #N` отдельным commit'ом, squash-merge collapse'ит
  в один) — продолжает работать дисциплинированно. Применена в
  T100 + T102 без сбоев. Без изменений в правиле.

- **Pre-spike перед spec для задач с готовыми библиотеками** — не
  формализованное правило, но T100 продемонстрировал ценность.
  Стоит ли вшивать в spec-ритуал? Пока — нет, по-прежнему делаем
  case-by-case (когда choice-architectural и зависит от unknown
  библиотечного поведения).

**Технический долг и идеи для 0.5.0:**

- **T103** — SE-amp wire-router fix (T100 W2 risk realized в T102).
  Не блокирует Phase 1b LLM chat, но висит. Самый горячий
  кандидат на ближайшую сессию — контекст SE-amp layout ещё свежий.
- **T101** — Diode SPICE-модели → `SpiceModelLibrary` (DRY-симметрия
  с T006/T007, диоды сейчас inline через `Sim.Params` в фасаде).
- **T004b** — `bridge_edit_and_resim` с автосравнением (продолжение
  Phase 1a, продакшен-польза bridge).
- **T002 / T003** — bootstrap.sh / bootstrap.ps1 (установщики KiCad
  / ngspice / FreeCAD; не на критическом пути ядра, но нужны для
  reproducible setup на свежей машине).
- **Phase 1b — LLM chat-client (T011-T016)** — крупная новая
  подсистема, требует полный spec/clarify/analyze. Старт после
  закрытия T103 / T101 / T004b. Готовность ядра — есть: фасад
  T100 даёт API, которое LLM может вызывать как tool.
- **`uv build` smoke в pre-push** — проверка что wheel содержит
  все force-include data files. ≤30 строк изменений в
  `.pre-commit-config.yaml`.
- **W2 mitigation в `Schematic.facade`** — примитивный канальный
  router (вертикальные/горизонтальные коридоры между рядами grid'а
  для wire-stub'ов). ≤50 LOC по T100 §Analyze W2. Возможно
  объединить с T103 в одну задачу.

---

## [0.3.0] — 2026-05-17

Третий milestone: цикл «расширение domain'а до самодостаточной
manifest-first модели проекта». Hexagonal-фундамент 0.2.0 расширен
тремя направлениями (Phase VO + derived status, Manifest YAML
primary, Decision aggregate), что закрыло полное направление D из
ADR T096 (зафиксировано в 0.2.0 retrospective как tech-debt) и
подготовило ядро для Фазы 1a дорожной карты CONCEPT §13.

После 0.3.0:
- проект самодостаточен и портативен (manifest = truth, SQL = index);
- проектная история фиксируется в `decisions/*.md` (DDR);
- domain-модель готова принимать реальные bridge'и (KiCad, ngspice,
  FreeCAD, FEMM) — это работа Фазы 1a.

### Added

- **Decision aggregate (журнал проектных решений; CONCEPT §4.4).**
  Каждое значимое решение фиксируется как markdown файл
  `<project>/decisions/D###_<slug>.md` (truth) + краткая запись в
  `project.yaml → decisions:` (index).
  - `domain.Decision` frozen-VO: id (`D###` / `D1000+`), title,
    date, status (`proposed | accepted | rejected`), summary,
    rationale, evidence (relative Path | None), session
    (relative Path | None).
  - `domain.DecisionRef` — компактная запись для manifest YAML.
  - `Project.decisions: tuple[DecisionRef, ...] = ()` — новое
    поле, default empty (forward-compat с pre-T099 manifest'ами).
  - Outbound port `DecisionRepository` (Protocol: save / load /
    list_all / next_id) + контрактные `DecisionNotFoundError`,
    `DecisionInvalidError`.
  - Filesystem markdown adapter
    (`adapters/outbound/decision_markdown/`): atomic write
    (tmp + os.replace), парсинг по anchor-секциям (`# `,
    `**Дата:** `, `**Статус:** `, `## Summary`, `## Rationale`,
    опционально `## Evidence`, `**Сессия:**`). Unknown секции
    (`## Context` / `## Variants` / etc.) игнорируются — пользователь
    может расширять файл руками. Слаг через NFKD + ASCII drop +
    dash-collapse, max 50 chars, fallback `untitled`.
  - Application use cases: `AddDecision`, `ListDecisions`,
    `GetDecision`. Новый error `DecisionPersistenceError`
    (markdown saved, manifest sync failed → подсказка `reindex`).
  - CLI subapp: `efactory decision add --project --title --summary
    --rationale [--status] [--date] [--evidence] [--session]`,
    `efactory decision list --project`, `efactory decision show
    --project --id D001`. ID auto-increment per project.
  - `ReindexProjects` расширен optional `decision_repo`:
    `Project.decisions` пересобирается из реальных markdown файлов
    (markdown = truth). Без `decision_repo` поведение идентично
    T098. CLI `efactory project reindex` пробрасывает adapter
    автоматически.
  - +37 тестов (12 domain Decision, 23 markdown adapter с tmp_path,
    8 use cases с fake-портами, 6 e2e CLI включая manual-edit
    acceptance). Spec — `specs/T099-decision-aggregate/spec.md`
    (Analyzed: 10 Clarify resolved + 3 Critical + 3 Warning +
    8 Note). (T099)

- **Manifest YAML primary, SQL = index (T098).** Главное обещание
  efactory: проект самодостаточен и портативен. `project.yaml`
  в корне папки проекта становится источником истины; SQLite —
  быстрый индекс для `list`.
  - Outbound port `ProjectManifestRepository` (Protocol: save /
    load / exists / discover_all) + контрактные
    `ManifestNotFoundError`, `ManifestInvalidError` (объявлены
    в port, adapter переэкспортирует — чтобы application мог
    ловить без нарушения layered contract).
  - Filesystem YAML adapter
    (`adapters/outbound/manifest_yaml/`): PyYAML safe_load/dump,
    atomic os.replace, exclude path для портативности (W1),
    `schema_version: 1`, `sort_keys=False`, `allow_unicode=True`.
  - `Project.updated_at: datetime` — новое domain поле, default
    factory now(UTC); SQL миграция `cc78f2ee52bb` добавляет
    column + backfill = created_at для existing rows.
  - SQL `save` → idempotent upsert (C1): insert-or-update by id.
    Один путь для CreateProject и ReindexProjects.
  - Application errors: `IndexPersistenceError(project_name,
    cause)` — partial-failure (manifest saved, SQL upsert failed;
    подсказка `reindex`); `ProjectManifestMissingError` — SQL
    знает, manifest на диске нет (desync).
  - Use cases переработаны на manifest-first:
    - `CreateProject`: dir → manifest.save → SQL upsert.
    - `UpdateProject`: SQL.get_by_name (path) → manifest.load →
      mutate → updated_at=now() → manifest.save → SQL.update.
    - `GetProject`: SQL только для path, всё остальное — manifest.
    - `DeleteProject`: отвязан от `get_project`; работает даже
      без manifest на диске.
  - Новый `ReindexProjects` use case + `ReindexSummary{indexed,
    bootstrapped, orphans, failed}`:
    - Primary mode: manifest → SQL upsert.
    - Bootstrap mode: SQL-only записи → создать manifest из SQL
      (для проектов созданных до T098); `updated_at = created_at`
      (Clarify #10).
    - `--remove-orphans` (default False): удалить SQL-строки без
      manifest вместо bootstrap.
    - Best-effort: ошибки собираются в `failed`, не блокируют.
  - CLI: `efactory project reindex [--storage-root]
    [--remove-orphans]` с TSV summary; exit 1 при failed > 0,
    exit 0 иначе.
  - README обновлён: новый раздел «Manifest как источник истины»
    с portability-workflow.
  - +44 теста (1 миграция backfill, 1 SQL upsert, 20 manifest
    adapter, 2 application errors, 3 CreateProject, 4 UpdateProject,
    3 GetProject, 11 ReindexProjects, 3 reindex e2e, 1 portability
    e2e, 1 partial-failure e2e). Spec —
    `specs/T098-manifest-primary/spec.md` (Analyzed: 10 Clarify
    + 3 доп. resolved, 3 Critical + 3 Warning + 7 Note). (T098)

- **Phase VO + derived `Project.status` + Update use case (T097).**
  Реализация фазы B направления D (ADR T096).
  - `domain.Phase` — frozen Pydantic VO с 6 каноническими
    фазами (schematic / simulation / pcb / magnetics / enclosure /
    documentation), методы `start / complete / skip / unskip` +
    `transitioned_to(target_status)` dispatcher с матрицей
    разрешённых переходов.
  - `ProjectStatus` × 7 (CONCEPT §4.3): idea / schematic /
    simulated / pcb_designed / magnetics_done / enclosure_done /
    production_ready. **Derived** от phases через
    `@computed_field`: последняя непрерывно-закрытая фаза с
    начала; chain прерывается на pending/in_progress; skipped
    считается закрытой.
  - `Project.phases: tuple[Phase, ...]` (6 фаз в каноническом
    порядке, default — все pending).
  - `Application.UpdateProject` use case + `PhaseUpdate` DTO +
    `MetadataRepository.update(project) → None`.
  - Persistence: SQL `phases` table с FK CASCADE + Alembic
    миграция `d82c9915c172` с backfill 6 pending rows для
    existing проектов через batch_alter_table (SQLite-совместимо).
  - CLI: `efactory project update <name> --new-name` /
    `--phase <name> --status <s>`; shortcuts `add-phase` /
    `skip-phase`; обновлённый `show` с таблицей фаз.
  - `# type: ignore[prop-decorator]` для `@computed_field +
    @property` (Pydantic-recommended workaround под mypy#5916,
    согласовано).
  - `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls =
    ["typer.Option", "typer.Argument"]` в pyproject.toml.
  - +56 тестов. Spec — `specs/T097-phase-vo/spec.md` (Analyzed:
    10 Clarify + 3 Critical + 3 Warning + 6 Note). (T097)

- **Дизайн-направление расширения domain'а зафиксировано: D**
  (`Phase VO + derived status + Update` → `Manifest = primary
  storage` → `Decision aggregate`). ADR в `DECISIONS.md`
  (`2026-05-17 — Domain expansion direction: D`); рассмотрены
  6 альтернатив (A первым, B одним, C первым, SQL=primary,
  Phase=scalar, PhaseName=whitelist) с обоснованием отвержения.
  Декомпозиция в `BACKLOG.md`: T097, T098, T099 — с acceptance
  criteria каждой. Spec — `specs/T096-domain-expansion/spec.md`
  (Done). Реализации в scope T096 нет. (T096)

- **Auto-install pre-commit pre-push hook через hatchling custom
  build hook.** После `git clone && uv sync` хук установлен
  автоматически, отдельная команда `uv run pre-commit install
  --hook-type pre-push` больше не нужна (остаётся как fallback).
  - `hatch_build.py` в корне реализует
    `BuildHookInterface.initialize`, делегирует на
    `uv run --no-sync pre-commit install --hook-type pre-push`.
    Использует `shutil.which('uv')` (избегаем `S607`), очищает
    `VIRTUAL_ENV` из build venv (иначе uv игнорирует проектный
    `.venv/`).
  - Регистрация через `[tool.hatch.build.hooks.custom]` в
    `pyproject.toml`.
  - Guard'ы: skip при отсутствии `.git/` (tarball/non-VCS) и
    при отсутствии `uv` на PATH — exit 0, warning в stderr.
  - Идемпотентность бесплатно: без `--reinstall` uv кеширует
    editable wheel, hook не дёргается на повторных `uv sync`.
  - ADR — `DECISIONS.md`
    (`2026-05-17 — Auto-install pre-push hook через hatchling
    custom build hook`), spec —
    `specs/T095-auto-install-hook/spec.md`.
  - README → «Проверки перед push» обновлён: ручная команда
    помечена fallback. (T095)

### Changed

- Closing-правка `BOARD.md`: запись `Doing → Done` оформляется
  отдельным commit'ом **после** `gh pr create`, чтобы пометка
  содержала реальный `[closed YYYY-MM-DD, PR #N]` вместо
  placeholder `PR current` (повторившегося ×6 в `[0.2.0]`:
  T086–T091). Зафиксировано подразделом «Closing-правка `BOARD:
  Doing → Done`» в `CLAUDE.md § Git workflow`. Глобальное правило
  «closing-правка в задачном PR, без парного chore-PR»
  сохраняется — здесь только проектное уточнение порядка шагов на
  ветке. В 0.3.0 применено без помарок 3 раза (T097, T098, T099).
  (T093)
- `Project.model_config` получил `extra='ignore'` (T098 Clarify #5)
  — manifest YAML с future-полями (description, type, и т.п.,
  которые приедут со своими фичами) валидируется без ошибок;
  unknown поля молча игнорируются. Документировано: «v1 manifest
  schema ignores fields outside the spec; they will be removed
  on next write». (T098)
- `[tool.ruff.lint.ignore]` дополнен `S603` (subprocess call
  without shell=True и без user-input — известный false-positive).
  Введено по ходу T095 (`hatch_build.py` — первый subprocess в
  проекте); обоснование в самой ignore-секции `pyproject.toml`.
  (T095)
- `ManifestNotFoundError`, `ManifestInvalidError` контрактные
  исключения порта `ProjectManifestRepository` перенесены из
  adapter в port (adapter переэкспортирует) — application-слой
  ловит их без нарушения layered contract `application > ports >
  domain`. (T098)
- `validate_name` (T092 валидатор против path-traversal) вынесен
  в общий `domain/_name.py` — разрыв циклического импорта
  `project ↔ decision`. `ProjectName` и `DecisionTitle` теперь
  разделяют один валидатор. (T099)
- `ReindexProjects.reindex_projects` принимает optional
  `decision_repo: DecisionRepository | None` параметр. Без него —
  поведение идентично T098 phase 2 (backward compat). (T099)

### Retrospective

**Что зашло:**

- **Полное направление D закрыто за один milestone без правок
  ADR T096.** T097 → T098 → T099 встали в depends-chain как
  планировалось: derived `Project.status` (T097) → manifest-first
  pattern (T098) → markdown + manifest reference (T099) повторил
  паттерн T098. Архитектурная декомпозиция оправдалась.
- **Ритуал spec → clarify → analyze работает для крупных фич
  стабильно.** Три раза (T097, T098, T099) Claude писал
  draft → 10+ clarify-вопросов → resolved дефолтами Разработчиком
  → Analyze (Critical/Warning/Note) → Analyzed. До implement
  ни одной архитектурной правки сверх scope.
- **TDD outside-in держится по умолчанию.** Каждый use case и
  adapter — Red e2e/unit → Green реализация → коммит. Никаких
  «как это протестировать» пауз.
- **Closing-правка BOARD после `gh pr create` (T093) применилась
  3 раза без помарок.** В 0.2.0 placeholder `PR current` повторился
  ×6; в 0.3.0 не повторился ни разу. Правило стабильно.
- **Pre-push hook (T095) экономит внимание.** Все 6 PR cycle 0.3.0
  прошли гейт автоматически на push (включая release-PR).
  Несколько раз ловил мои опечатки до push'а (D213 docstring
  style, FBT001/003 на bool флаге).
- **`# type: ignore[prop-decorator]` (T097 feedback)** сработал
  как ожидалось во всех 3 milestone-задачах с computed_field —
  обсуждать каждый раз не нужно.
- **import-linter independence contract расширяется автоматически
  при появлении новых adapter sub-packages.** T098 добавил
  `manifest_yaml`, T099 — `decision_markdown`. Контракт ловит
  любые попытки cross-adapter импортов.
- **Manifest = truth, SQL = index** архитектурно подтвердилась
  через два примера: `project.yaml` (T098) и `decisions/*.md`
  (T099). Паттерн одинаков: atomic write первичного хранилища →
  обновление индекса; partial-failure → подсказка `reindex`.

**Что не зашло:**

- **CodeRabbit опять на rate-limit.** Через все 6 PR (T097, T098
  ×2 если считать revert, T099, release) status-check показывал
  SUCCESS без реального ревью. Альтернатива не выбрана — T094
  остаётся в BACKLOG как открытый техдолг.
- **Большие PR с phase-разбиением.** T098 содержал 3 фазы (phase 1
  spec, phase 2 use cases, phase 3 CLI+e2e) — каждая отдельным
  коммитом до squash; squash-merge даёт один коммит в main, но
  обзорный diff большой (1000+ строк). T099 уложился в 2 фазы.
  Альтернатива — мелкие PR на каждую фазу — отвергнута: больше
  overhead на review/CodeRabbit (и так на rate-limit), и фазы не
  имеют самостоятельной ценности (incomplete intermediate
  states).
- **Pyright/mypy не дружит с pydantic `RelativePath` coercion.**
  В T099 adapter `_parse` Pydantic v2 спокойно coerce'ит str →
  Path через AfterValidator, но static-checker требует явный
  type. Один `# type: ignore[arg-type]` локально (документирован
  в self-review T099). Если повторится — обсудим.

**Правки методики (внесены по ходу):**

- **`# type: ignore[prop-decorator]`** для `@computed_field +
  @property` теперь применяется без обсуждения — это
  Pydantic-recommended workaround (mypy#5916). Зафиксировано в
  auto-memory (`feedback_computed_field_type_ignore.md`).
- **Closing-правка BOARD после `gh pr create`** окончательно
  стабилизировалась. Никаких изменений в правиле — просто
  дисциплинированное применение.
- **CHANGELOG cut** в release-PR (без парного chore-PR) —
  применено первый раз в этом milestone. Сработало: один PR
  с переименованием Unreleased + новой пустой Unreleased + Done
  очисткой BOARD.

**Технический долг и идеи для 0.4.0:**

- T094 (CodeRabbit paid / альтернатива) остаётся открытым —
  Разработчик пока откладывает.
- Renaming `MetadataRepository → ProjectIndex` (T098 Clarify #4
  паркинг) — мини-задача, не критично, можно сделать «по дороге»
  при следующем рефакторинге.
- Auto-reindex после ручной правки `project.yaml` или
  `decisions/*.md` (T098 Clarify #8) — пока явный `reindex`,
  но при появлении демона / web — пересмотрим.
- Готовность к Фазе 1a — следующий шаг: bootstrap (T002/T003),
  KiCad bridge (T004), модели ламп (T006), pipeline OP/tran/AC
  (T008). Domain-фундамент готов принимать.

---

## [0.2.0] — 2026-05-17

Второй milestone: hexagonal-фундамент 0.1.0 обкатан полным CRUD-набором
для домена `Project` (Create/List/Show/Delete), автоматизирован 5-
проверочный гейт через pre-commit hook, закрыта первая security-
уязвимость (path-traversal в `Project.name`). Архитектура подтвердила
рабочий характер на 4 use case'ах без правок фундамента.

### Security
- Валидация `Project.name` против path-traversal в `domain/project.py`.
  До T092 имя вида `../../etc` проходило domain-валидацию (которая
  проверяла только non-empty/non-whitespace) и попадало в
  `projects_root / name`. Для `delete_project` T090 это означало
  `shutil.rmtree` за пределами `projects_root` — потенциальное
  разрушение хост-FS. Сейчас вход — только локальный CLI (низкая
  реальная эксплуатируемость), но защита проактивная: при появлении
  MCP / HTTP-API имя может прийти из недоверенного источника.
  - `_validate_name` дополнен правилами: запрет имён `.` и `..`,
    запрет символов `/` и `\`.
  - CLI `efactory project create` ловит `pydantic.ValidationError`
    и выводит «Invalid project name: ...» в stderr с
    `exit_code=2` (вместо безобразного Rich-traceback с pydantic
    internals).
  - 14 параметризованных unit-тестов на отказ опасных имён (`..`,
    `.`, `../etc`, `..\\etc`, `/absolute`, `a/b`, `a\\b`,
    `trailing/`, `\\leading`, `./rel` и т.д.) + 7 на человеческие
    имена (включая юникод `тёплый-усилитель`) + 1 e2e на UX при
    bad name. 59 passed, coverage 99.20%. (T092)

### Added
- Pre-commit hook на 5-проверочный гейт через
  [pre-commit](https://pre-commit.com) framework на stage `pre-push`.
  - `.pre-commit-config.yaml` с пятью local hooks (`ruff check` /
    `ruff format --check` / `mypy src` / `lint-imports` / `pytest`).
    Local-стиль (без mirror-репозиториев) — версии инструментов
    те же, что фиксированы в `uv.lock`, без отдельного pinning.
  - `pre-commit` добавлен в dev-deps (`pyproject.toml` / `uv.lock`).
  - Однократная установка после клонирования —
    `uv run pre-commit install --hook-type pre-push`. Документировано
    в README → «Проверки перед push».
  - Существующий `.git/hooks/pre-push` (защита `main` от прямого push)
    сохраняется как `.git/hooks/pre-push.legacy` и запускается первым
    в migration mode pre-commit.
  - `git push` теперь автоматически прогоняет гейт; способы скипа
    (`SKIP=pytest git push`, `git push --no-verify`) документированы. (T091)
- Четвёртый use case `DeleteProject` — завершает базовый набор
  CRUD (Create, Read-Many, Read-One, Delete) для домена `Project`.
  - `ports/outbound/metadata_repository.py`: + `delete_by_name(name) -> None`.
  - `ports/outbound/project_file_repository.py`: +
    `remove_project_directory(path) -> None`.
  - `application/delete_project.py`: новый use case (порядок:
    `get_by_name` → `delete_by_name` → `remove_project_directory`)
    и re-export `ProjectNotFoundError` из `application.get_project`
    (общее исключение для read-and-act use cases).
  - `adapters/outbound/persistence_sql/repository.py`: реализация
    `delete_by_name` через `delete(...).where(name == ...)`. Noop
    при отсутствии строки (идемпотентно).
  - `adapters/outbound/file_store/project_file_repository.py`:
    реализация `remove_project_directory` через `shutil.rmtree`
    в `asyncio.to_thread`. Idempotent: если каталога нет — тихо
    возвращается (orphan-row страшнее orphan-папки, поэтому FS-
    операция последняя и не блокирует общий success).
  - `adapters/inbound/cli/app.py`: команда
    `efactory project delete --name <name>` — выводит
    «Deleted project <name>» при успехе; при отсутствии печатает
    `Project '<name>' not found` в stderr + `exit_code=1`.
  - Тесты (TDD outside-in): 2 e2e (happy path + unknown name; happy
    проверяет, что `show` после delete → exit 1, `list` пуст),
    2 unit с fake-портами (happy + raises; косвенно подтверждает
    порядок `get → delete`), 2 integration SQL (`delete_by_name`
    удаляет / noop на отсутствующее имя), 2 integration FS
    (`remove_project_directory` удаляет дерево / idempotent на
    отсутствующий путь). 37 passed, coverage 99.14% (+8 новых
    тестов). (T090)
- В `BACKLOG.md` новая задача **T091** (раздел «Архитектурные
  follow-up'ы Walking Skeleton») — pre-commit hook на 5-проверочный
  гейт (`pre-commit` framework + `.pre-commit-config.yaml`). Сейчас
  гейт прогоняется вручную; автоматизировать через `pre-commit`. (T090)
- В `BACKLOG.md` новая задача **T092** (там же) — валидация
  `Project.name` против path-traversal. Выявлено при self-review T090:
  имя «../../etc» проходит текущую domain-валидацию и попадает
  в `projects_root / name` (критично для `delete_project` →
  `shutil.rmtree`). Текущий вход — только локальный CLI, поэтому не
  CVE-уровень; станет критично при появлении MCP / HTTP. (T090)
- Третий use case `GetProject` (по имени) — продолжение обкатки
  hexagonal-фундамента после T088.
  - `ports/outbound/metadata_repository.py`: `MetadataRepository`
    Protocol расширен методом `get_by_name(name) -> Project | None`.
  - `application/get_project.py`: use case + `ProjectNotFoundError`
    (явное application-исключение, чтобы CLI / API могли отличить
    «нет такого» от «БД упала»).
  - `adapters/outbound/persistence_sql/repository.py`: реализация
    `get_by_name` через `select(...).where(name == ...).limit(1)`.
  - `adapters/inbound/cli/app.py`: команда
    `efactory project show --name <name>` — построчный вывод
    метаданных проекта; при отсутствии печатает
    `Project '<name>' not found` в stderr и выходит с `exit_code=1`.
  - Тесты (TDD outside-in): 2 e2e (happy + unknown name),
    2 unit с fake-портом (found / raises), 2 integration
    (get returns row / get returns None). Coverage 99.02%
    (29 passed; +6 новых). (T089)
- Второй use case `ListProjects` — проверка hexagonal-фундамента на
  втором сквозном срезе (CLI → application → SQL-adapter → domain).
  - `ports/outbound/metadata_repository.py`: `MetadataRepository`
    Protocol расширен методом `list_all(self) -> list[Project]`.
  - `application/list_projects.py`: тонкий use case, делегирует
    выборку и сортировку adapter'у.
  - `adapters/outbound/persistence_sql/repository.py`: реализация
    `list_all` через `select(...).order_by(created_at DESC)`,
    `model_to_project` mapping.
  - `adapters/inbound/cli/app.py`: команда
    `efactory project list` — TSV-вывод
    `name<TAB>created_at_iso<TAB>path`, пустой список выводит
    «No projects found.».
  - Тесты (TDD outside-in): 2 e2e (newest-first + empty), 3 unit
    с fake-портом (empty / returns / delegates ordering), 2 integration
    (sort DESC + empty). Coverage 98.84% (23 passed; +7 новых тестов). (T088)
- `composition/settings.py`: XDG-style default'ы для `projects_root`
  и `database_url` через `Field(default_factory=...)` —
  `$XDG_DATA_HOME/efactory/{projects,efactory.db}` или
  `$HOME/.local/share/efactory/...` если переменная не задана.
  Walking Skeleton CLI работает из чистого окружения без обязательного
  `.secrets` или env (`Settings()` больше не падает с
  `ValidationError`). Явное переопределение через
  `EFACTORY_PROJECTS_ROOT` / `EFACTORY_DATABASE_URL` или
  `.secrets`-файл остаётся возможным и имеет приоритет над default'ами. (T087)
- `composition/main.py`: хелпер `_ensure_storage_dirs` — composition
  root до запуска Alembic-миграций создаёт `projects_root` и
  родительский каталог SQLite-файла (URL парсится через
  `sqlalchemy.engine.make_url`, не-SQLite драйверы пропускаются). (T087)
- Тесты: `tests/unit/composition/test_settings.py` (3 теста —
  XDG-default, XDG_DATA_HOME override, env override) и
  `tests/integration/composition/test_main.py` (1 тест — `build_cli_app`
  без env создаёт storage-каталоги и сквозной use case работает). (T087)
- В `BACKLOG.md` новый раздел «Архитектурные follow-up'ы Walking
  Skeleton» с задачей **T087** — дать `Settings` разумные default'ы
  для `projects_root` / `database_url`, чтобы Walking Skeleton CLI
  работал из коробки. Выявлено при работе над T086. (T086, закрыт в T087)

### Changed
- README «Быстрый старт» упрощён до двух строчек —
  `uv sync && uv run efactory project create --name myprj`. Блок
  создания `.secrets` (введённый в T086) убран после появления
  default'ов `Settings`. `.secrets`/env описаны справочно как
  способ переопределить пути по умолчанию. (T087)
- README «Быстрый старт» (предыдущая итерация в T086): устаревшая
  команда `uv run python src/main.py` заменена на Walking Skeleton
  CLI `uv run efactory project create --name <name>` + блок создания
  `.secrets` (на тот момент `Settings()` падал с `ValidationError` без
  явных env). Промежуточное состояние, схлопнутое в T087. (T086)

### Fixed
- Уточнение к Retrospective `[0.1.0]`: пункт «снять
  "провизорный" статус с ADR про Kùzu в `DECISIONS.md`»
  был ошибочным — статус снят финальным squash-коммитом T085
  (см. `DECISIONS.md` ADR «Kùzu как embedded граф-БД для
  топологий», раздел Последствия → Статус). Попал в ретро
  по неточной session-memory: запись «сделаем при следующей
  правке DECISIONS» не была сверена с актуальным состоянием
  ADR. Сам блок Retrospective как часть milestone-snapshot
  `[0.1.0]` не редактируется. (T086)

### Retrospective

**Что зашло:**

- **TDD outside-in лёг как шаблон.** Четыре use case'а CRUD
  (T085 Create, T088 List, T089 Show, T090 Delete) сделаны по
  одному образцу: e2e Red → unit Red с fake-портами → integration
  Red → Green. Время на use case стабильное (~40 мин), без
  «как же мне это протестировать»-пауз.
- **Архитектурный вопрос «правильный ли фундамент 0.1.0?»
  получил утвердительный ответ через 4 практики.** Ни один из
  4 use case'ов не потребовал правок Settings, composition root,
  layers contracts, миграционной системы. Hexagonal со старта
  работает.
- **Pre-commit hook (T091) окупился сразу.** Следующий же PR
  (T092) прошёл гейт без ручной `&&`-цепочки. Освобождение
  внимания заметно — perception «забыть гейт» сместилась с
  «вероятно» на «невозможно». Local-стиль hooks (вместо mirror-
  репозиториев) обеспечил единые версии инструментов с `uv.lock`.
- **Парковка побочных находок работает.** В ходе T086 всплыл
  Settings без default'ов → T087. В ходе T090 при self-review
  всплыл path-traversal → T092. Оба запаркованы в момент
  обнаружения, разобраны следующими PR — scope текущей задачи
  оставался чистым.
- **CodeRabbit реально проревьюил один раз (PR #10) — feedback
  оказался полезный.** Три замечания (PR ref + грамматика
  «об»/«о», строгий `exit_code == 1`, явные ассерты на поля)
  — все валидные, учли в fix-up commit. Не игнорировали.
- **Защита в domain, не в адаптерах** (T092 path-traversal) —
  правильное архитектурное решение: все use cases и адаптеры
  защищены автоматически, при появлении MCP/HTTP не нужно
  дублировать валидацию.

**Что не зашло:**

- **CodeRabbit упирался в rate-limit на 6+ PR из 9.** Free-tier
  не выдерживает интенсивной работы (rate-limit 42 минуты после
  пары PR). Status-check показывал SUCCESS, что вводило в
  заблуждение — реального ревью не было. Раз бот работает, его
  фидбек ценный, но полагаться на него нельзя.
- **Помарка `PR current` → `PR #N` повторилась 6 раз.** В записи
  T086, T087, T088, T089, T090, T091 — каждый раз правили в
  следующем PR. Корень: BOARD-запись закрытия делается **до**
  `gh pr create`, поэтому номер PR ещё не известен. Возможные
  решения для следующего milestone: (а) сделать closing-правку
  BOARD отдельным финальным commit'ом после `gh pr create`,
  (б) принять placeholder как ОК и систематически править в
  следующем PR (как делали).
- **Один раз я написал хрупкий unit-тест с monkey-patch + `# noqa:
  SLF001`** (T090, третий тест на порядок DB→FS) — нарушение
  методики «без noqa без обсуждения». Поймал по `pre-commit`,
  удалил тест как избыточный (паттерн уже виден из кода и
  косвенно подтверждается raises-тестом). Методически правильнее
  было сразу понять избыточность, не писать.
- **Qodo на паузе у этого аккаунта** — не использовался во
  всём 0.2.0 цикле (как и в 0.1.0). Если paid seat не появится —
  можно отключить, чтобы не шумел «paused»-комментариями на
  каждом PR.

**Правки методики (внесены по ходу):**

- **`pre-commit install --hook-type pre-push`** — добавлен в
  README → «Проверки перед push». Должен быть обязательным шагом
  после `uv sync` для всех новых разработчиков; обновится в
  template `dreamteam` отдельно.
- **Грамматика «об изменениях» (а не «о изменениях») перед
  гласной** — поправлено во всех BOARD-записях Done через
  `replace_all` в T086 fix-up. Унаследовано из template; в
  template `dreamteam` следующая правка попадёт отдельным PR
  (не сейчас, не в этой сессии).
- **Auto-memory `feedback_tdd.md`** (из ранней сессии) применился
  последовательно 5 раз без отступлений. Подтверждено.

**Технический долг и идеи для 0.3.0:**

- Помарка `PR current` — выбрать один из подходов выше и
  применять единообразно.
- Если CodeRabbit продолжит rate-limit — оценить paid plan
  или альтернативу (например, `/ultrareview` для критичных PR
  — Разработчик-триггерируемая).
- Возможно `uv sync` mог бы сам устанавливать pre-commit hook
  через post-install script (опционально).
- Domain расширение: следующий agregat (Component? Schematic?)
  или второй use case с записями (Update — когда появится
  реальное поле для обновления).

---

## [0.1.0] — 2026-05-17

Первый осмысленный milestone проекта: концепт проекта зафиксирован в
живой документации, дорожная карта разложена по фазам в backlog,
заложен архитектурный фундамент (hexagonal, TDD, async) и проверен
Walking Skeleton сквозного use case.

### Added
- Разложение `CONCEPT.md` v5.1 (immutable) по живой проектной
  документации: цель / принципы / диаграмма пайплайна / таблица
  «готовое vs своё» в `README.md`; 7 ADR в `DECISIONS.md`
  (архитектурный принцип MCP-обвязки, выбор kicad-sch-api,
  kicad-mcp-pro, SPICEBridge, PyOpenMagnetics+FEMM,
  FreeCAD+freecad-mcp, стратегия версионирования через
  `compatibility.toml`); 49 задач (`T002`–`T050`) по фазам
  1a/1b/2/3/4 дорожной карты в `BACKLOG.md`. (T001)
- Декомпозиция фаз 5 (намоточные изделия), 6 (корпус),
  7 (производственная документация), 8 (будущее) дорожной
  карты CONCEPT.md §13 в `BACKLOG.md`: 34 задачи
  (`T051`–`T084`). (T050)
- Архитектурный фундамент проекта:
  - **Фаза 0 (дизайн).** Спецификация
    `specs/T085-architecture-foundation/spec.md` (Analyzed) и
    9 ADR в `DECISIONS.md` — Hexagonal Architecture, TDD-first,
    async-first, Pydantic v2 domain + отдельные persistence-
    модели, ручная DI-композиция, SQLAlchemy 2.0 + aiosqlite +
    Alembic для метаданных, Kùzu для графа топологий
    (провизорно), pydantic-settings для конфига, import-linter
    для автоматической изоляции слоёв.
  - **Фаза 1 (скелет).** Структура `src/` по hexagonal-слоям
    (`domain/`, `application/`, `ports/{inbound,outbound}/`,
    `adapters/{inbound,outbound}/`, `composition/`) с README в
    каждой папке слоя. Runtime-зависимости (`pydantic`,
    `pydantic-settings`, `sqlalchemy[asyncio]`, `aiosqlite`,
    `alembic`, `kuzu`, `typer`) и dev-зависимость `import-linter`
    в `pyproject.toml`. Editable-install 5 верхнеуровневых
    слоёв через `[build-system]` (hatchling-`packages`). Alembic
    инициализирован с async-шаблоном (`migrations/` внутри
    SQL-адаптера, исключены из ruff/mypy/coverage), стартовая
    пустая миграция-плейсхолдер. Kùzu Critical #1 закрыт: wheel
    под Python 3.14 работает, sync API обёрнут в
    `asyncio.to_thread` — подтверждено integration-smoke-тестом
    `tests/integration/adapters/graph_store/test_kuzu_smoke.py`.
    `import-linter` сконфигурирован: layers contract
    (composition → adapters → application → ports → domain)
    + forbidden contract для `domain` (запрет
    sqlalchemy/aiosqlite/alembic/kuzu/mcp/anthropic/typer).
    Все 5 проверок качества (ruff / format / mypy / pytest /
    lint-imports) зелёные.
  - **Фаза 2 (Walking Skeleton).** Сквозной use case
    `CreateProject` (`efactory project create --name <name>`) через
    все слои end-to-end по TDD outside-in:
    - `domain.Project` — Pydantic v2 aggregate (id UUID, name с
      инвариантом non-empty, path, created_at TZ-aware, статус
      ProjectStatus enum).
    - `application.create_project` — тонкий use case, оркестрирует
      два outbound-порта.
    - `ports.outbound.MetadataRepository` и `ProjectFileRepository` —
      Protocol-интерфейсы.
    - `adapters.outbound.persistence_sql` — модели SQLAlchemy 2.0
      typed declarative, явный mapping `domain ↔ persistence`,
      реализация `MetadataRepository`, утилита запуска Alembic-
      миграций (`migrations_runner`), revision
      `create_projects_table` через autogenerate.
    - `adapters.outbound.file_store.FilesystemProjectFileRepository`
      — создание директории проекта через `asyncio.to_thread`.
    - `adapters.inbound.cli` — Typer-app с командой
      `project create --name`, зависимости пробрасываются через
      фабрику `build_app(...)`.
    - `composition.settings.Settings` — pydantic-settings (env
      prefix `EFACTORY_`, optional `.secrets` file).
    - `composition.main.build_cli_app` / `run` — composition root:
      Settings → миграции → engine + session_factory → repositories
      → CLI-app. Entry point `efactory = "composition.main:run"`.
    - Третий import-linter контракт: `independence` между
      адаптерами (`adapters.inbound.cli`,
      `adapters.outbound.persistence_sql`, `…file_store`).
    - Тестовый стек: e2e walking skeleton, unit-тесты domain/
      application с fake-портами (без `unittest.mock`), integration
      адаптеров с реальными SQLite и FS в `tmp_path`. Coverage
      ≥ 80% (≈98% после исключения Protocol-портов и
      TYPE_CHECKING-блоков). Все 5 проверок качества зелёные.
    - Штатные настройки плагинов (без подавлений): `pydantic.mypy`
      в mypy, `runtime-evaluated-base-classes` в
      `flake8-type-checking` (для Pydantic/SQLA typed declarative),
      `--import-mode=importlib` в pytest. (T085)

### Retrospective

**Что зашло:**

- Outside-in TDD на T085 дал чистый Walking Skeleton без mock-ов:
  domain/application — fake-порты, адаптеры — integration с реальными
  SQLite/FS в `tmp_path`. Coverage ≈98% при честном (не «mock-fest»)
  тестовом стеке.
- Ритуал **Spec → Clarify → Analyze** на T085 поймал риск Kùzu под
  Python 3.14 на этапе дизайна (Critical #1). В фазе 1 риск закрыли
  smoke-тестом — wheel ставится, sync API работает через
  `asyncio.to_thread`. До блокера дело не дошло.
- Editable install через `hatchling`-`packages` вместо `PYTHONPATH`-
  хака — import-linter нашёл слои «из коробки».
- BACKLOG как буфер: при разложении CONCEPT.md (T001) и
  декомпозиции фаз 5–8 (T050) идеи парковались отдельными T-задачами,
  scope текущей задачи оставался чистым.

**Что не зашло:**

- Парные chore-PR на закрытие BOARD (T001 → PR #2, T050 → PR #4) —
  лишний overhead на ревью и сторонние боты, на каждую задачу ×2 PR
  без самостоятельной ценности. Породило правило (см. ниже).
- CodeRabbit упирался в rate limit на T050 (~40 мин) и на T085
  (58 мин); оба раза мерджили через self-review fallback. Бесплатные
  ревью-боты в критическом пути — ненадёжны.
- `README.md` «Быстрый старт» остался в template-варианте
  (`uv run python src/main.py`) и устарел сразу после T085 — Walking
  Skeleton предоставляет CLI `efactory project create --name <name>`.
  Tech-debt, в следующий milestone.
- `DECISIONS.md` ADR про Kùzu всё ещё помечен «провизорный»; фаза 1
  закрыла этот риск, статус надо снять. Tech-debt, в следующий
  milestone.

**Правки методики (внесены по ходу):**

- **Closing-правка BOARD (Doing → Done) делается прямо в задачном
  PR**, без парного chore-PR. Зафиксировано в проектном и глобальном
  `CLAUDE.md`, в auto-memory проекта
  (`feedback_closing_board_in_task_pr.md`) и в mem0. T085 уже
  закрылся по новому правилу.
- **Укрупняем PR.** Границы PR определяет логическая связность
  задачи, а не желание «PR покороче». Парный chore — допустим только
  как fallback (забыли в задачном PR — поправили после merge).
- **TDD строго во всём efactory** (Red → Green → Refactor) — outside-in
  для hexagonal, domain без mock-ов, адаптеры — integration с
  реальными зависимостями. Зафиксировано в auto-memory
  (`feedback_tdd.md`) и в mem0.
