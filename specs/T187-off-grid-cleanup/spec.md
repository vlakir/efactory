# Spec: T187 — Off-grid cleanup в шаблонах + grid-check утилита

**Статус:** Done
**Дата создания:** 2026-06-05
**Связанные документы:**
- BACKLOG.md → Фаза 3 → T187 (исходная формулировка, до Plan B redirect).
- T029 (closed PR #118) — ERC quality gate, в Phase 0 probe которого
  отловлены off-grid warnings и заведена T187.
- T029 spec — `specs/T029-erc-quality-gate/spec.md` (общая инфраструктура
  `kicad-cli sch erc --format json` + markdown-отчёт; T187 переиспользует
  тот же runner и формат).
- T026 — staged-modifications: writer-level снап применяется к applied
  working copy, не к staged-диффу (диктует семантику integration с
  `KicadSchematicWriter`).
- T031 phase-5-templates — три «builderless» шаблона (`6p13s-se-resistive`,
  `6zh32p-mic-preamp`, `6zh38p-if-amp`) были baked one-shot скриптом
  `/tmp/build_t031_templates.py` (НЕ committed), что определяет scope
  ремонта для этих трёх.
- T134 — KB sync дисциплина (Уровень 1+2): новый KB topic + routing row
  + deterministic L2 regression case.

---

## 1. Overview

Массовая чистка `endpoint_off_grid` warnings во встроенных шаблонах
проекта. Probe 2026-06-05 (на ветке `main` после T029 squash-merge)
показал, что 6 из 11 шаблонов имеют off-grid endpoints (всего 81
warning, vs 95 в первоначальной оценке BACKLOG — T029 builder-фиксы
уже подмели часть). Пять шаблонов чистые. Симуляция работает (netlist
по uuid'ам, не координатам), но в ERC-отчёте они шумят и в KiCad GUI
«компонент чуть-чуть не довинчен» — любая ручная правка рискует
развалить connectivity.

Фича — **двухслойный фикс по Plan B (выбран Vladimir-ом 2026-06-05)**:

1. **Превентивный слой.** В `Schematic` facade
   (`adapters/outbound/schematic_kicad/facade.py`) — снап позиций
   компонентов и endpoints проводников к connection grid (1.27 mm)
   на entry-point'ах API. Регенерация 3 builderless-шаблонов
   (`6p13s-se-resistive`, `6zh32p-mic-preamp`, `6zh38p-if-amp`)
   через возвращённый в `scripts/regenerate-templates.py` build-script
   T031, и 3 buildered (`active-lpf-sallen-key`, `bjt-ce-nfb`,
   `op-amp-inverting`) — через существующих builders в `_BAKERS`.

2. **Diagnostic слой.** CLI `efactory schematic check-grid <project>`
   (read-only) — детектор off-grid endpoints из `.kicad_sch` с
   локализацией (symbol-ref / pos / nearest grid point / Δ). Slash
   `/grid-check` для agent-driven workflow. Inplace используется в
   T187 как proof-of-fix; долго живёт как regression guard
   для пользовательских / hand-edited схем (вне scope T187).

Не пишем грид-snap auto-fix на baked `.kicad_sch` (BACKLOG-обоснование:
разные элементы прыгают в разные стороны, рвут провода). Снап
применяется **только в writer pipeline** (facade → file), когда
координаты ещё известны как atomic component placements, а не как
независимые wire endpoints.

## 2. Сценарии использования

- **S1.** Разработчик-builder. Я добавляю компонент через
  `sch.add_resistor(at=(101.5, 80.3))` (off-grid координаты по
  невнимательности). Facade на entry-point молча snap'ит к
  `(101.6, 80.01)` (ближайший узел 1.27-grid), а опционально через
  `EFACTORY_STRICT_GRID=1` — поднимает `OffGridPositionError`. Default —
  silent snap (сохраняет UX). Конечный `.kicad_sch` всегда на grid.
- **S2.** Регенерация шаблонов. `uv run python scripts/regenerate-
  templates.py` (без `--template`) пересобирает все 8 шаблонов из
  builders + 3 T031 builders, итог `data/templates/*/` — на disk без
  off-grid warnings. ERC-отчёт T029 чистый.
- **S3.** Agent (внутри `efactory:linux`). Пользователь говорит «проверь
  схему на grid» / «check the grid alignment» → routing'ом `/grid-check`
  → output: «0 off-grid endpoints» / список нарушений с локализацией.
  Agent не правит — предлагает Vladimir-у ручной фикс в GUI с указанием
  координат.
- **S4.** CI / pre-push (потенциальный, вне scope T187 заведения). Лонг-
  ран: `efactory schematic check-grid data/templates/*/` в pre-push
  hook фейлит push при появлении регрессии. T187 ship'ит CLI, в hook
  не интегрирует.
- **S5.** Hand-edited schematic. Пользователь добавил компонент в KiCad
  GUI без grid-snap (custom drawing grid). Запускает `/grid-check` →
  получает список, исправляет в GUI.

## 3. Functional Requirements

### Слой 1 — Snap-on-write (facade)

**ДОЛЖНА.**

- F1. Все public API `Schematic.add_*` и `Schematic.connect(...)` /
  `Schematic.label(...)` принимают координаты в мм, но перед сохранением
  в internal представление **snap'ят к connection grid 1.27 mm**.
  Snap-функция — `_snap_connection_grid(value, grid_mm=1.27) → round(value
  / grid_mm) * grid_mm`, отдельная от существующей `_round_grid` (0.01 mm
  drawing-grid).
- F2. Применение snap покрывает: (a) Position'ы компонентов; (b) wire
  endpoints; (c) label-positions; (d) spice-directive at-coords; (e)
  pwr-flag / no-connect markers. Pin local-offsets (внутри
  `_SymbolDef.pin_layouts`) **не** snap'ятся — это library geometry, не
  user-input. Они уже на 2.54 mm grid by-design KiCad.
- F3. При `EFACTORY_STRICT_GRID=1` (env-var) silent snap заменяется на
  `OffGridPositionError(name, requested, snapped, delta)` — diagnostic
  для разработки новых builders. Default — silent snap.
- F4. Snap идемпотентен и стабилен по float-точности (round-trip через
  `_snap_connection_grid` → bit-exact).

**НЕ ДОЛЖНА.**

- N1. Не модифицировать pin local-offsets в `_SymbolDef`.
- N2. Не snap'ить `lib_symbols` (graphical primitives внутри symbol
  definition).
- N3. Не править существующие `data/templates/*.kicad_sch` файлы
  напрямую — только через builder + regenerate.

### Слой 2 — Detector CLI

**ДОЛЖНА.**

- F5. CLI `efactory schematic check-grid <project-or-sch>` — путь к
  проекту (директория с `.kicad_sch`) или путь к `.kicad_sch`
  напрямую. Симметрично UX `efactory design check` из T029.
- F6. Auto-detect `.kicad_sch` при опущенном `<project>`: pattern из
  `/sim-run` (`*.kicad_sch` в cwd top-level + 1 subdir, ровно 1 match).
- F7. Реализация — переиспользует **готовый** `KicadCliErcRunner` из
  T029. Фильтрует violations по `type == "endpoint_off_grid"`,
  пересобирает в domain `OffGridReport`. **Не** парсит `.kicad_sch`
  S-expr сами — kicad-cli уже сделал работу.
- F8. Markdown-отчёт в `<project_root>/out/grid-check/<UTC-ISO-ts>/
  report.md` или `<sch.parent>/out/grid-check/<ts>/report.md` для
  standalone single-file. Symmetry с T029 layout.
- F9. Содержание отчёта: таблица violations с колонками `kind` (pin /
  wire-endpoint / label / pwr-flag), `description` (как из ERC JSON),
  `pos (mm)`, `nearest-grid (mm)`, `delta (mm)`, `uuid`. Группировка
  по abs-Δ от grid (большие drift'ы сверху — приоритет ручного
  фикса).
- F10. Exit-codes симметричны T029: `0` — clean; `1` — есть off-grid
  endpoints; `2` — infrastructure fail (kicad-cli unavailable / parse
  error).
- F11. Slash `/grid-check [<project>]` в `docker/runtime-agent-
  commands/grid-check.md` с auto-detect.

**НЕ ДОЛЖНА.**

- N4. Не модифицировать `.kicad_sch`. Read-only end-to-end.
- N5. Не реализовывать собственный KiCad S-expr parser — только
  через kicad-cli JSON.
- N6. Не блокировать `/sim-run` / `design_to_sim` — это не gate, это
  диагностика. ERC gate из T029 покрывает hard-errors; off-grid —
  visibility-only.

### Слой 3 — Регенерация шаблонов

**ДОЛЖНА.**

- F12. Восстановить build-script для 3 T031 builderless шаблонов как
  proper Python модули — `tests/integration/adapters/schematic_kicad/
  test_6p13s_se_resistive_facade.py::_build_6p13s_se_resistive` (etc.),
  параллельно с pattern остальных facade builders. Reverse-engineering
  из baked `.kicad_sch` — извлечь компоненты / wires / labels / SPICE
  directive по текущему файлу, переписать через `Schematic` facade.
- F13. Добавить 3 новых импорта-functions в
  `scripts/regenerate-templates.py` + 3 новых записи в `_BAKERS` →
  `regenerate-templates.py` теперь регенерирует все 11 шаблонов.
- F14. Builder snap (F1-F4) применяется в этих builders автоматически
  — никаких ручных правок координат в builder-коде не требуется.
- F15. Прогон `uv run python scripts/regenerate-templates.py` (полная
  ребилда) → 11 шаблонов на disk, ERC `endpoint_off_grid` count == 0
  для всех 11.

**МОЖЕТ.**

- M1. При reverse-engineering T031 builders snap-fix может слегка
  сместить компоненты на ≤0.5 mm (визуально незаметно). SPICE-numerics
  должны остаться идентичными (verified в SC3).

**НЕ ДОЛЖНА.**

- N7. Не менять SPICE-параметры компонентов (R/C/L values,
  tube SPICE models, voltage source amplitudes) при reverse-engineering.
- N8. Не править существующие 5 чистых шаблонов (`nfb-se-amp`,
  `se-amp`, `tube-line-preamp`, `tube-phono-riaa`, `tube-pp-amp`) — они
  уже ERC clean и тестов на них не трогаем.

## 4. Success Criteria

- **SC1.** Все 11 встроенных шаблонов после T187 имеют ERC
  `endpoint_off_grid count == 0` (через `kicad-cli sch erc --format
  json`, тот же что T029).
- **SC2.** `efactory schematic check-grid` на 11 шаблонах → 0 violations
  для каждого; exit-code 0.
- **SC3.** Smoke `/sim-run` через `EFACTORY_PROJECTS_ROOT=/tmp/...
  efactory bridge design-to-sim op <prj>` на **3 представительных** —
  по одному из каждой «семьи»:
  - **6 builderless 3-T031:** `6p13s-se-resistive` (op-point: V_plate
    ∈ [40, 120] V, Ia ∈ [25, 50] mA, Ig2 < 15 mA — границы T031 §6
    test_t031_phase5_templates.py);
  - **2 buildered «power-rail-shift»:** `op-amp-inverting` (op-point:
    V_out near 0 V at zero V_in);
  - **1 buildered «mixed»:** `bjt-ce-nfb` (op-point: V_collector в
    ожидаемом diapason).
  Числовые результаты должны быть **numerically identical**
  (per-node-name remapping — same V/I/op-point values) до/после snap-
  fix; не требуется bit-exact text diff `.cir` или netlist (uuid'ы /
  node names могут поменяться при reverse-engineering Phase 0). См.
  Analyze W2.
- **SC4.** Coverage новых модулей (`OffGridReport`, snap-helper,
  detector use case, adapter wrapper) ≥80% (проектный threshold).
- **SC5.** Pre-push hooks (5/5) проходят: ruff check, ruff format,
  mypy, lint-imports, pytest.
- **SC6.** KB sync (T134 Уровень 1 + 2): новый topic
  `design.grid-check` + mapping `/grid-check` в
  `agent.command-routing` + deterministic L2 regression test
  (`tests/integration/agent_kb/test_control_examples.py`,
  parametrized case с query «проверь грид схемы» → expected_topic
  `design.grid-check`).
- **SC7.** Регенерация всех 11 шаблонов одной командой
  `uv run python scripts/regenerate-templates.py` (без `--template`)
  завершается без ошибок и snapshot/facade-тесты остаются зелёными
  после обновления (если требуется).
- **SC8.** `EFACTORY_STRICT_GRID=1 uv run python scripts/regenerate-
  templates.py` завершается успешно (никакой builder не пытается
  передать off-grid координаты после T187 фикса).

## 5. Key Entities

### Domain layer (`domain/grid.py`)

- `GridStepMm` — newtype `float` (semantic alias) для grid step (default
  1.27 mm).
- `OffGridEndpoint` — frozen pydantic: `kind: Literal["pin", "wire",
  "label", "pwr-flag", "no-connect"]`, `description: str`, `pos: tuple[
  float, float]`, `nearest_grid: tuple[float, float]`, `delta_mm:
  tuple[float, float]`, `uuid: str`.
- `OffGridReport` — frozen pydantic: `schematic_path: Path`,
  `timestamp: datetime`, `kicad_version: str`, `grid_step_mm:
  GridStepMm`, `endpoints: list[OffGridEndpoint]`, computed `count: int`.
- `snap_to_grid(value: float, grid_mm: float = 1.27) -> float` —
  чистая функция, `round(value / grid_mm) * grid_mm`. Используется
  и в facade (writer), и в detector (для `nearest_grid`).

### Domain exceptions

- `OffGridPositionError(component_name: str, requested: tuple[float,
  float], snapped: tuple[float, float], delta_mm: tuple[float, float])`
  — для `EFACTORY_STRICT_GRID=1` режима. Не для production.

### Outbound ports

- Никаких новых outbound ports — T187 переиспользует `ErcRunner`
  (T029) для получения raw violations. Detector — pure-application
  слой.

### Use case (`application/run_grid_check.py`)

- `async def run_grid_check(*, schematic: Path, project_root: Path |
  None, erc_runner: ErcRunner, report_writer: GridReportWriter | None
  = None, grid_step_mm: GridStepMm = 1.27) -> OffGridReport`.
  - Зовёт `erc_runner.run(...)`, фильтрует violations по `type ==
    "endpoint_off_grid"`, маппит в `OffGridEndpoint` с подсчётом
    nearest grid + delta.
  - При `report_writer is not None` — пишет markdown отчёт.
  - Не бросает на `count > 0` — это не gate.

### Adapters

- Нового KiCad CLI adapter не нужен — переиспользуем
  `KicadCliErcRunner` (T029).
- `adapters/outbound/grid_report_markdown/writer.py` —
  `MarkdownGridReportWriter`, рендер таблицы.

### Facade snap (`adapters/outbound/schematic_kicad/facade.py`)

- Новая private function `_snap_connection_grid(value: float,
  grid_mm: float = 1.27) -> float`.
- Применяется в:
  - `_to_position` (entry-point координат компонентов);
  - `Schematic.add_resistor / add_capacitor / add_inductor / add_diode
    / add_v_dc / add_v_ac / add_ground / add_pwr_flag / add_bjt /
    add_mosfet / add_opamp / add_subcircuit / add_tube`;
  - wire endpoint writer (внутри `connect`);
  - label writer (`Schematic.label`);
  - SPICE-directive at-coord writer.
- Pin transform (`_transform_pin`) **не** трогается — pin local-
  offsets уже on-grid.

### CLI / slash

- Новая CLI subgroup `efactory schematic` с командой `check-grid`
  (под зонтиком существующего `efactory` CLI, см. T029 wiring как
  pattern для `efactory design check`).
- Slash `/grid-check` в `docker/runtime-agent-commands/grid-check.md`.

## 6. Assumptions & Constraints

- **A1. KiCad 10.0.3+ connection grid = 1.27 mm** (probe-verified
  через ERC behavior). `.kicad_pro` per-project может переопределить
  drawing-grid, но connection-grid для ERC — глобальный constant в
  KiCad ≥ 8.x. Hardcoded 1.27 mm допустим; через `--grid-step` CLI-
  flag — overrideable (для будущих imperial-only схем).
- **A2.** Snap к ближайшему grid point на ≤0.5 mm движение визуально
  незаметно и не меняет SPICE topology (netlist по uuid'ам).
  Verifiable через SC3.
- **A3.** Реверс T031 builderless шаблонов — straightforward:
  компоненты типизированы (R, C, V, tube via `Valve:EL84` symbol),
  net-labels явны, no buried sheet hierarchy. Probe требуется в
  Phase 0 для confirmation размера усилия.
- **A4.** T029 `KicadCliErcRunner` уже в репо после squash-merge PR
  #118 на main — у T187 на старте есть доступ к composition root и
  тестам.
- **A5.** 5 чистых шаблонов уже соответствуют snap-инварианту по
  факту — T187 не нарушает их. Их builders (facade.py + builder
  functions) после snap entry-point получают **identity-no-op** snap
  (координаты уже on-grid), bit-exact regen.
- **A6.** Existing `_round_grid` (0.01 mm drawing-grid) **остаётся** —
  она устраняет FP-jitter после rotation и независима от connection-
  grid snap. Pipeline: rotation → `_round_grid` (FP-jitter clean) →
  `_snap_connection_grid` (force on-grid). Order matters.

## 7. Out of Scope

- **DRC / PCB-level grid checks** (`.kicad_pcb`) — Phase 4, PCB модуль.
- **Custom grid step config через `.kicad_pro` чтение** — supported
  только через CLI `--grid-step`. Парсинг `.kicad_pro` для grid
  settings — overkill для T187 (KiCad 10 хранит drawing-grid, не
  connection-grid).
- **Pre-push grid-check на user-репо** — T187 ship'ит CLI, integration
  в pre-push hook — отдельная задача (если потребуется).
- **Auto-fix существующих schematic'ов на disk** — режим reject'нут на
  спец-уровне (BACKLOG / clarify R10 T029).
- **Снап labels-positions при `connect()` — между labels/junctions**
  — нет, label / junction координаты trust-input при F2.
- **5 чистых шаблонов** (`nfb-se-amp`, `se-amp`, `tube-line-preamp`,
  `tube-phono-riaa`, `tube-pp-amp`) — не регенерируются и не
  фиксятся в T187. Они уже clean; их builders унаследуют snap entry-
  point бесплатно при следующем регенерационном сеансе (другая задача).
- **Reverse-engineering T031 builderless шаблонов до точного состояния
  baked .kicad_sch** — допустимы микро-сдвиги ≤0.5 mm (SC3 защищает
  SPICE-numerics, не визуальные UUIDs).

---

## Clarify (заполняется Claude)

### Open questions

- **Q1. Reverse-engineering T031 builderless шаблонов — proper builder
  vs preserved baked + manual snap?** Базовый предлагаемый план —
  написать proper Python builders для 3 T031 шаблонов (F12) и
  включить их в `_BAKERS`. Альтернатива: оставить их как baked без
  builder-source-of-truth и поправить в GUI вручную (как в исходном
  BACKLOG-Plan A). Альтернатива дешевле (~30 min ручной правки в
  GUI на 3 schematic'а с 6 одинаковыми endpoint-fingerprint), но не
  даёт preventive guarantee для будущих regen-сеансов. Какой выбрать?
- **Q2. CLI namespace для detector — `efactory schematic check-grid`
  или `efactory design check-grid`?** BACKLOG предлагает первый, T029
  ship'нул второй (`efactory design check` для ERC). Симметрия — за
  второй (логически: «check whatever about design»). Первый — за
  semantic split (design = ERC + simulation correctness; schematic =
  geometric / visual). Какой берём?
- **Q3. Snap default mode — silent или strict?** F3 предлагает silent
  default + `EFACTORY_STRICT_GRID=1` opt-in. Альтернативно: strict
  default с opt-out (`EFACTORY_LAX_GRID=1`). Strict default безопаснее
  (поймаем off-grid в новых builders сразу), но потенциально ломает
  существующих builders (T031 / sim-test builders) на первом запуске
  до их фикса. Silent default UX-friendly, strict — safety-net для
  CI / pre-push. Что предпочитаешь?
- **Q4. Detector grid-step — hardcoded 1.27 vs `--grid-step` flag?**
  F5 / A1 hardcoded по умолчанию + `--grid-step` flag overrideable.
  Альтернативно: всегда читать из конфига `.kicad_pro` (если он есть)
  или из ENV. KiCad ≥ 8 жёстко 1.27 mm для connection-grid → hardcoded
  достаточно. Подтверждаем?
- **Q5. Slash + KB topic name — `/grid-check` / `design.grid-check`,
  или `/schematic-check-grid` / `schematic.grid-check` (под T026
  namespace `schematic.*`)?** Симметрия с `/design-check` диктует
  первое; consistency с T026 namespace `schematic.*` (staged-mods)
  тянет ко второму. Outcome либо одинаково uplift'ит KB. Какое
  предпочитаешь?
- **Q6. Фазирование T187 — 5 фаз достаточно?**
  - Phase 0: probe revere-engineering 3 builderless шаблонов (~30
    min), оценить сложность; вынести решение по Q1.
  - Phase 1: domain TDD (`snap_to_grid` / `OffGridReport` /
    `OffGridEndpoint` / use case) + facade snap entry-point.
  - Phase 2: detector adapter + markdown writer + integration tests
    через реальный kicad-cli.
  - Phase 3: CLI / slash / composition wiring + KB sync (T134 1+2).
  - Phase 4: реализация builders / регенерация 6 шаблонов / SC1-SC8
    acceptance / PR.
  Тебя устраивает разбивка, или мерджим Phase 1/2 / разрезаем 4?
- **Q7. Что детектор делает с violations типа `pin_not_connected`,
  `wire_dangling`, `unconnected_label` — оставить или фильтровать
  только off-grid?** F7 говорит «фильтрует по `endpoint_off_grid`».
  Альтернатива: вынести фильтр в параметр (`--include all|off-grid|
  ...`). Минимальная польза в T187, но open question — может быть
  smell of overengineering.
- **Q8. Snap внутри `connect(pin_a, pin_b)`.** Если pin_a и pin_b
  уже on-grid (came from snapped Position), то wire endpoint
  автоматически on-grid и snap внутри `connect` — no-op. Но если
  builder зовёт `connect(custom_point_a, custom_point_b)` с
  координатами кастом-точки (T-junction, например) — snap нужен.
  F2 (b) покрывает. Подтверди что согласен.

### Resolved (с ответами)

- **R1 ← Q1. (Vladimir, 2026-06-05) Proper builders для 3 T031 шаблонов.**
  Phase 0 probe reverse-engineering'а ([6p13s-se-resistive, 6zh32p-mic-
  preamp, 6zh38p-if-amp] → Python builder в test_*_facade.py pattern),
  затем включение в `_BAKERS`. Preventive guarantee для будущих
  регенераций. Manual GUI fallback (Plan A из BACKLOG) применяется
  ТОЛЬКО если probe в Phase 0 покажет, что reverse-engineering
  для какого-то одного шаблона прохибитивно сложен — тогда explicit
  re-decision с Vladimir-ом.
- **R2 ← Q2. (Vladimir) CLI namespace: `efactory design check-grid`.**
  Симметрия с T029 (`efactory design check`). Логика: design-уровень
  объединяет ERC + grid (correctness of design definition); schematic-
  уровень оставляем за T026 staged-modifications (manipulation of
  schematic file).
- **R3 ← Q3. (Vladimir) Snap default — silent + `EFACTORY_STRICT_GRID=1`
  opt-in.** UX-friendly для builders, strict как safety-net для CI /
  pre-push / новых builders. Strict default отложен (потенциально
  вернёмся, если builders проявят регрессию off-grid).
- **R4 ← Q4. (Vladimir) Grid step — hardcoded 1.27 mm + `--grid-step
  <mm>` CLI flag.** KiCad ≥ 8 connection-grid жёстко 1.27 mm; не
  парсим `.kicad_pro`. Flag оставлен на случай imperial-only legacy
  схем (не наш случай, но дешёвая страховка).
- **R5 ← Q5. (Vladimir) Slash + KB topic — `/grid-check` +
  `design.grid-check`.** Симметрия с `/design-check` + `design.erc-
  quality-gate` из T029. Namespace `design.*` накапливает diagnostics
  по design-definition (ERC, off-grid). `schematic.*` остаётся за T026
  manipulation-операциями (staged-mods, etc.).
- **R6 ← Q6. (Vladimir) Фазирование 5 фаз ок.** Phase 0 probe (reverse-
  engineering + Q1 confirmation) → Phase 1 domain TDD + facade snap
  entry-point → Phase 2 detector adapter + writer + integration tests
  → Phase 3 CLI / slash / composition wiring + KB sync → Phase 4
  builders / регенерация / SC1-SC8 / PR.
- **R7 ← Q7. (Vladimir) Detector фильтрует только `endpoint_off_grid`.**
  Минимальный scope T187. `--include` flag не добавляем (overengineering
  для текущей задачи). Если в будущем потребуется broader diagnostic —
  отдельная задача.
- **R8 ← Q8. (Vladimir) Snap в `connect(pin_a, pin_b)` для custom
  T-junction точек.** F2 (b) подтверждён. Pin-derived endpoints
  автоматически on-grid (наследуют snap из Position); custom-point
  wire endpoints (T-junction, redirect) snap'ятся явно.

---

## Analyze (заполняется Claude после resolved-clarify)

Pass-1 (2026-06-05, после resolved R1-R8). **3 Warning / 4 Note,
0 Critical.** Acceptance: gate чист, можно начинать Phase 0.

### 🟡 Warning

- **W1. Reverse-engineering Phase 0 — риск scope blow-up.** Если
  baked `.kicad_sch` 3 T031 шаблонов содержат hand-tweaked nuances
  (custom label positions, специфичные wire-routing'и для читаемости),
  reverse-engineering до точного state может занять > 1 фазы. Probe
  Phase 0 должен явно ответить: «builder восстановим за ≤ 1 сессия
  на шаблон». Если нет — fallback: manual GUI fix (R1 contingency).
  Mitigation: SC3 защищает только SPICE-numerics, **не** визуальный
  layout до-pixel — допустимы микро-сдвиги, что упрощает reverse.
  Phase 0 acceptance: spec уточнить «builder восстанавливает SPICE-
  идентичную схему, визуально близкую (та же топология, размещение
  компонентов с ≤2 mm tolerance)».

- **W2. SC3 «bit-exact identity» — недостижимо после snap-fix.**
  Текущая формулировка SC3: «numerical результаты bit-exact до/после».
  После snap (e.g., y=80.5 → y=80.01) **uuid'ы компонентов сохраняются**
  (если builder детерминированный с тем же RNG seed), netlist по
  uuid'ам идентичен, ngspice OP bit-exact ✓. НО: если в Phase 0
  reverse-engineering меняет builder logic (новый код = другой UUID
  seed), uuid'ы изменятся → netlist текстуально другой (одни и те же
  значения R/C/L, но другие node names и instance names) → ngspice OP
  numerically identical (всё, что считается — V/I/op-point — те же),
  но **strict bit-exact diff** падает на разнице node names.
  Mitigation: SC3 уточнить как «numerically identical op-point»
  (compare values per node-name remapping), а не bit-exact text diff.
  Phase 4 acceptance: сравнение OP via `op.json` (or parsed ngspice
  raw), не diff `.cir`.

- **W3. `efactory design check-grid` vs `efactory design check`
  взаимодействие.** Сейчас T029 `efactory design check` фокус: ERC
  hard-errors блокируют. T187 `check-grid` — diagnostic only. Если
  пользователь хочет «всё проверить» — будет звать ДВЕ команды? Или
  один объединённый `efactory design check --include-grid`?
  Решение: T187 ship'ит SEPARATE команды для чёткой ответственности
  и UNIX-philosophy (one tool one job). Объединение — отдельная
  задача T188+ (если нужна). Spec уточнить: F5 явно «отдельная
  subcommand, не флаг к существующей `check`». КАЖДАЯ команда
  ship'ит свой markdown report (separate `out/erc/<ts>/` vs
  `out/grid-check/<ts>/`).

### 🟢 Note

- **N1. `_snap_connection_grid` order vs `_round_grid`.** В A6 spec
  фиксирует pipeline order: rotation → `_round_grid` (FP-jitter clean
  к 0.01 mm) → `_snap_connection_grid` (force к 1.27 mm). Реализация
  должна вызвать `_snap_connection_grid(_round_grid(value))`. Bit-
  exactness round-trip: `_round_grid(0.01) = 0.01` → `_snap_(0.01) =
  0.0` ; `_round_grid(1.27) = 1.27` → `_snap_(1.27) = 1.27`. OK для
  obvious cases; edge-case y=0.635 (midpoint) → `_round_grid(0.635) =
  0.64` → `_snap_(0.64) = 1.27` (away from 0). Поведение «round half
  to even» Python'овского `round()` обеспечивает консистентность.
  Документировать в snap-helper docstring.

- **N2. Pin local-offsets в `_SymbolDef` уже on-grid.** Probe
  facade.py:148-155 — tube pin offsets вида (-7.62, 1.27) = (6×grid,
  1×grid). Резистор / конденсатор pin offsets — стандартные KiCad
  symbols (`Device:R`, `Device:C`) — KiCad library by-design on-grid.
  Op-amp `Amplifier_Operational:LM358` тоже on-grid. Эмпирический
  риск: если в будущем будет добавлен custom symbol с pin offset не
  кратным 1.27 — snap entry-point на Position не спасёт. Mitigation:
  assert в `_PinLayout` constructor (или в unit-test) что local offsets
  кратны 1.27. Phase 1 acceptance.

- **N3. `EFACTORY_STRICT_GRID=1` в CI / pre-push.** R3 ship'ит silent
  default. Полезно в CI / pre-push выставить `EFACTORY_STRICT_GRID=1`
  как safety-net против регрессий. Pre-push hook tweak — отдельный
  follow-up (не в-scope T187, BACKLOG candidate). Документировать в
  ADR-T187a / KB topic как recommended CI setup.

- **N4. `data/templates/*/{{PROJECT_NAME}}.kicad_pro`.** Регенерация
  шаблонов перезаписывает `.kicad_sch`, но `.kicad_pro` обычно
  передаётся через bake step (см. `_bake_se_amp` lines 215-228). Для
  3 T031 builderless шаблонов нужен такой же bake-step. Phase 4
  включает: новый `_bake_6p13s_se_resistive` / `_bake_6zh32p_mic_
  preamp` / `_bake_6zh38p_if_amp` с минимальным `.kicad_pro` JSON
  (как у se-amp baker). При reverse-engineering сверить с
  существующим baked `.kicad_pro` — если custom design_settings, то
  preserve.

### Acceptance gate

✓ **0 Critical**. Можно стартовать Phase 0 (probe reverse-engineering
3 T031 builderless шаблонов).

W1-W3 — spec и acceptance уточняются в-process (не блокеры).

N1-N4 — implementation-time notes.
