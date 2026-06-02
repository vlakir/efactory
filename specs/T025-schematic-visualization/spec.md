# Spec: T025 — Визуализация схемы в чате после `/sim-run`

**Статус:** Analyzed
**Дата создания:** 2026-06-02
**Clarified / Analyzed:** Clarified 2026-06-02 (Round 1+2), Analyzed
2026-06-02 (3 🔴 → resolved, 4 🟡 → noted, 4 🟢 → noted).
**Связанные документы:**
- `docker/runtime-agent-commands/sim-run.md` — текущая slash-инструкция,
  куда встраивается auto-show шаг.
- `src/application/sim_run.py` — use case, который потенциально
  расширяется до возврата `SchematicRender` артефакта.
- `docs/container-boundary.md` — образ/host контракт; рендер
  выполняется container-side, путь должен быть валиден для
  host-side Claude Code agent через bind-mount.
- BACKLOG.md, исходная формулировка T025 (2026-05-15) — переоценена
  в свете Phase 0.9 containerization.
- T032 (Phase 3) — наследует SVG-pipeline для LLM-vision валидации.

---

## 1. Overview

После запуска `/sim-run` пользователь видит в чате inline-рендер той
самой схемы, которая была отсимулирована — чтобы немедленно убедиться
«симулирую то, что нарисовал», без переключения в KiCad. Реализация:
расширяем `efactory bridge sim-run` пайплайн `kicad-cli sch export
svg` → magick convert PNG; путь к PNG печатается в stdout, Claude
Code agent показывает изображение inline по absolute path. SVG-побочный
артефакт остаётся фундаментом для будущей T032 (LLM-vision
валидация топологии).

## 2. Сценарии использования

efactory — без явных end-user'ов; работа идёт через runtime-агент в
`efactory:linux` (slash-команды) и через CLI разработчика.

- **Как runtime-агент**, я после `/sim-run` хочу показать пользователю
  схему inline — чтобы тот сразу видел topology, на которой получены
  напечатанные op-point / измерения.
- **Как разработчик**, прогоняющий sim-цикл через `efactory bridge
  sim-run`, я хочу, чтобы команда печатала absolute path к свежему
  PNG-рендеру — чтобы Claude Code agent в моём чате показывал его без
  дополнительных шагов.
- **Как Vladimir**, проектирующий audio-amp, я хочу видеть схему
  даже когда симуляция упала (netlist пустой, ngspice не сошёлся) —
  topology — главный инструмент диагностики.

## 3. Functional Requirements

### 3.1. Render-helper (фундамент)

- **ДОЛЖНА:** существовать чистая функция (или маленький use case)
  `render_schematic(sch_path, out_dir) -> SchematicRender`, которая:
  - вызывает `kicad-cli sch export svg --output <out_dir> <sch_path>`
    (без `--pages` → все листы; kicad-cli создаёт один `.svg` на лист);
  - для каждого SVG конвертит в PNG через `magick convert <svg>
    <png>` (одна вызов на файл; параметры рендера — по умолчанию
    KiCad theme, без `--black-and-white`);
  - возвращает `SchematicRender(png_paths=[Path,...],
    svg_paths=[Path,...], created_at=datetime)`.
- **ДОЛЖНА:** функция не модифицировать `.kicad_sch`, не
  взаимодействовать с ngspice / симуляцией.
- **ДОЛЖНА:** при ошибке `kicad-cli` / `magick` пробрасывать
  доменное исключение `SchematicRenderError`; caller сам решает,
  fail-soft или fail-hard.

### 3.2. Интеграция в `bridge sim-run` CLI-adapter

- **ДОЛЖНА:** `_execute_sim_run` adapter (`src/adapters/inbound/cli/
  app.py:1491+`) вызывать `render_schematic(.kicad_sch, out_dir)`
  **до** `sim_run` use case (Q8 → a; диагностика при failure free).
- **ДОЛЖНА:** при `SchematicRenderError` — adapter fail-soft:
  stderr warning, sim-pipeline продолжается, `schematic-render:`
  строк в stdout не будет.
- **ДОЛЖНА:** при sim-failure (ngspice non-zero) render-результат
  сохраняется, `schematic-render:` строки печатаются (Q9 → показать).
- **ДОЛЖНА:** adapter печатать в stdout по одной строке
  `schematic-render: <abs/path/to/png>` на каждый PNG (multi-sheet —
  несколько строк) **перед** sim-output.
- **НЕ ДОЛЖНА:** модифицировать `sim_run` use case signature или
  `SimulationResult` DTO (hexagonal).

### 3.3. Интеграция в `project create` CLI-adapter (Q12)

- **ДОЛЖНА:** `project create` adapter (`src/adapters/inbound/cli/
  app.py:~421`) вызывать `render_schematic` после успешного
  `create_project` use case (после git init).
- **ДОЛЖНА:** при `SchematicRenderError` — fail-soft: stderr warning,
  проект всё равно создан; `schematic-render:` строк нет.
- **ДОЛЖНА:** adapter печатать `schematic-render: <abs>` строки в
  stdout по успешному render'у.
- **НЕ ДОЛЖНА:** модифицировать `create_project` use case или
  `CreateProjectResult` DTO.

### 3.4. Slash-команды

- **ДОЛЖНА:** `docker/runtime-agent-commands/sim-run.md` дополниться
  шагом «после CLI-вывода: если stdout содержит строки
  `schematic-render: <path>` — показать каждый PNG inline по
  absolute path, независимо от успеха симуляции».
- **ДОЛЖНА:** `docker/runtime-agent-commands/project-create.md`
  получить аналогичный шаг.

### 3.5. Запреты

- **НЕ ДОЛЖНА:** запускать `xdg-open` / Sixel / любые host-side
  viewer'ы — UX = Claude Code inline only.
- **НЕ ДОЛЖНА:** модифицировать `.kicad_sch`.
- **НЕ ДОЛЖНА:** влиять на ngspice output / sim-результат / git
  state в `create_project`.

## 4. Success Criteria

- **Acceptance fixtures** (Analyze C-2 fix (b)): `op-amp-inverting`,
  `se-amp`, `tube-pp-amp` (growing complexity, all existing):
  - `efactory bridge sim-run --schematic <project>/<project>.kicad_sch`
    создаёт хотя бы один PNG в `<project>/.efactory/renders/<TS>/`;
  - каждый PNG валиден (`file <png>` → `PNG image data`, размер ≥
    5 KB, разрешение ≥ 800×600);
  - stdout содержит ≥ 1 строки `schematic-render: <abs path>` (для
    multi-sheet — по одной на лист);
  - SVG-побочный артефакт остаётся в той же директории (фундамент T032).
- **Acceptance — `/project-create`:** аналогичный набор PNG в
  `<project>/.efactory/renders/<TS>/` после успешного создания из
  любого из 3 acceptance шаблонов; stdout содержит
  `schematic-render:` строки.
- **Acceptance — sim-failure path** (W-2 уточнение): валидный
  `.kicad_sch` (render OK) + invalid netlist (ngspice non-zero) →
  render PNG'и есть, `schematic-render:` строки в stdout
  напечатаны, exit-code != 0 отражает sim-failure.
- **Double-failure (render + sim) — НЕ acceptance.** Только log
  warnings + non-zero exit-code; debug-only path.
- **Не-регрессия:** все 1744 существующих теста проходят, coverage
  ≥ 80% сохраняется (порог `--cov-fail-under=80`).
- **Pre-push 5/5 ✓** (ruff check / format / mypy / pytest / coverage).
- **L1 KB sync:** `agent.command-routing` table обновлена —
  пользовательские фразы «покажи схему» / «отрисуй проект» переводятся
  в `/sim-run` (auto-show реализует UX) или `/project-create`
  (создание + auto-show).
- **L2 deterministic test:** parametrized regression case в
  `tests/integration/agent_kb/test_control_examples.py` для нового
  routing.

## 5. Key Entities

- **`SchematicRender`** (application VO в
  `src/application/render_schematic.py`, frozen dataclass):
  - `png_paths: tuple[Path, ...]` — absolute paths к PNG (sorted by
    filename для стабильности, см. Analyze W-3).
  - `svg_paths: tuple[Path, ...]` — соответствующие SVG (фундамент T032).
  - `created_at: datetime` — UTC timestamp создания render-директории.
- **`SchematicRenderError`** — application-level exception (kicad-cli
  exit-code != 0 / rsvg-convert failure / отсутствующий output).
- **`SimulationResult` / `CreateProjectResult`** — **не модифицируются.**
  Render-output живёт на уровне CLI-adapter stdout, не в domain DTO
  (Q7 Adapter-level resolution).

## 6. Assumptions & Constraints

- `kicad-cli sch export svg` доступен в `efactory:linux` (host тоже,
  проверено 2026-06-02 — поддерживает `--output <DIR>`, multi-sheet →
  один SVG на лист).
- `rsvg-convert` (apt `librsvg2-bin`) добавляется в `Dockerfile` Stage 1
  (per Analyze C-1 fix (b)) — ≈3 MB layer, минимальное delta для
  SVG→PNG. Команда: `rsvg-convert <svg.in> -o <png.out>` (опционально
  `--width=1920` для разрешения).
- Claude Code agent умеет показывать локальные PNG inline по absolute
  path (предположение из Q1 Round 1; верифицируется L3 smoke).
- Target host — Linux через `efactory:linux` контейнер; Windows
  откладывается в Phase 8.
- `xterm-256color` без Sixel-поддержки — terminal-graphics out-of-scope.
- Bind-mount контракт `~/.efactory-state/projects/<project>` ↔
  `/efactory/projects/<project>` (per `docs/container-boundary.md`) —
  путь к PNG валиден для host-side агента после translation.
- Storage convention: render-артефакты живут в `<project>/.efactory/
  renders/<TS>/` (timestamped subdir), аналогично T024 plots; добавляется
  в `.gitignore` (если ещё нет паттерна).

## 7. Out of Scope

- `xdg-open` / host viewer integration (Phase 8 follow-up).
- Sixel / Kitty terminal-graphics (требует Sixel-capable терминал +
  chafa/img2sixel; follow-up).
- Windows `start` поддержка (Phase 8).
- LLM-vision валидация схемы — T032 (Phase 3).
- Schematic beautifier — T106 (Phase 3).
- Explicit standalone `/schematic-show` slash — auto-show в
  `/sim-run` + `/project-create` покрывает primary UX; если
  понадобится — follow-up.
- Concurrent KiCad reload (`.kicad_sch.staged` IPC) — T026.
- Sheet-by-sheet selective rendering (`--pages 2,3`) — kicad-cli
  поддерживает, но T025 рендерит все листы; selective — follow-up.
- Side-by-side diff render (схема до / после edit) — T021 follow-up.

---

## Clarify (заполняется Claude)

### Resolved (Round 1, 2026-06-02)

- **(Q1) Primary UX-канал** — Claude Code chat inline по absolute path
  к PNG. Sixel/Kitty и xdg-open — не primary в T025.
- **(Q2) Container-side выполнение** — `efactory bridge sim-run`
  запускается внутри `efactory:linux`. Path translation через
  bind-mount — путь, видимый из контейнера, должен быть валиден
  host-side для Claude Code agent (см. Q11 Round 2).
- **(Q3) Auto-show встраивается в `/sim-run`** — не отдельный slash.
  Explicit `/schematic-show` — follow-up, если auto-show недостаточен.
- **(Q4) T025 как фундамент** — реализуем `kicad-cli sch export svg`
  pipeline; T032 переиспользует SVG для LLM-vision.
- **(Q5) Windows откладывается в Phase 8** — `start` shim не входит в
  T025.
- **(Q6) Acceptance fixtures** — `rc-divider`, `se-amp`, `tube-pp-amp`.

### Resolved (Round 2, 2026-06-02)

- **(Q7) Adapter-level render-вызов** (corrected 2026-06-02 после
  Analyze C-3). `render_schematic` — отдельный use case в
  `application/render_schematic.py`, pure function. Вызов — в
  CLI-adapter `_execute_sim_run` (`src/adapters/inbound/cli/app.py:
  1491+`) и в `create project` CLI-adapter (`app.py:~421`), не
  внутри `sim_run` / `create_project` use cases. `SimulationResult`
  / `CreateProjectResult` **не модифицируются**. Hexagonal
  соблюдена; `bridge_sweep` / `design_to_sim` не задеты (они зовут
  `sim_run` напрямую, минуя adapter).
- **(Q8) Render до симуляции** — `render_schematic` вызывается
  первым шагом `sim_run` use case, до ngspice. Render ≤ 2 с,
  diagnostic value free при failure.
- **(Q9) Render всегда показывается** — независимо от sim-результата
  (ngspice non-zero, netlist invalid). При failure агент видит и
  диагностические измерения, и схему — главный отладочный canvas.
- **(Q10) Все sheets** — multi-sheet `.kicad_sch` рендерится
  полностью; `kicad-cli sch export svg --output <DIR>` без
  `--pages` создаёт по одному SVG на лист; magick конвертит каждый;
  stdout печатает `schematic-render:` строку на каждый PNG. (Изменено
  Vladimir в Round 2 относительно моей рекомендации «root only».)
- **(Q11) Storage path (a)** — `<project>/.efactory/renders/<TS>/`
  timestamped subdir; PNG + SVG живут вместе. Аналогично T024
  plot-конвенции; `.gitignore` уже исключает `.efactory/*` (под
  верифицировать в Analyze).
- **(Q12) Расширить на `/project-create`** — render-инфраструктура
  переиспользуется; `create_project` use case вызывает
  `render_schematic` после git init; `CreateProjectResult` тоже
  расширяется полем `render`. Slash `project-create.md` дополняется
  inline-показ шагом.
- **(Q13) SVG→PNG через `magick convert`** — pipeline: `kicad-cli
  sch export svg --output <dir> <sch>` → loop `magick convert
  <svg> <png>` по каждому файлу. SVG-побочный артефакт остаётся
  для T032 (LLM-vision) переиспользования.

---

## Analyze (заполняется Claude)

_Analyze пройден 2026-06-02. 3 🔴 Critical, 4 🟡 Warning, 4 🟢 Note._

### 🔴 Critical

- **C-1. ImageMagick + librsvg отсутствуют в `Dockerfile`.**
  `efactory:linux` Phase 0 stage устанавливает KiCad 10 + ngspice +
  Qt6 runtime, но `imagemagick` / `librsvg2-bin` не в apt-list.
  Render-pipeline `kicad-cli sch export svg → magick convert` в
  контейнере не запустится.

  **Варианты fix:**
  - **(a)** apt-get добавить `imagemagick librsvg2-bin` (≈40 MB
    layer). Polyvalent — magick покрывает все image-conversion
    use cases.
  - **(b)** apt-get добавить только `librsvg2-bin` (rsvg-convert
    standalone, ≈3 MB). Заточен под SVG→PNG, меньше surface area.
  - **(c)** Python depend `cairosvg` через `uv add` — без OS-deps
    кроме cairo. Минусы: cairo не всегда корректно рендерит KiCad
    SVG (font issues).

  **Рекомендация — (b)** `librsvg2-bin` (≈3 MB, мало deps, KiCad-
  ориентированный, прямой `rsvg-convert <svg> -o <png>`). Влечёт
  правку `Dockerfile` Stage 1 + buildx-rebuild через
  `efactory-build-dev` (T141 cache, ~секунды теплого).

- **C-2. Фикстура `rc-divider` не существует.**
  Vladimir выбрал в Q6 `rc-divider + se-amp + tube-pp-amp`, но
  `rc-divider` отсутствует в `data/templates/` (8 templates: se-amp,
  nfb-se-amp, op-amp-inverting, bjt-ce-nfb, tube-pp-amp, tube-line-
  preamp, tube-phono-riaa, active-lpf-sallen-key) и в
  `tests/fixtures/`. Acceptance с несуществующей фикстурой
  невыполним.

  **Варианты fix:**
  - **(a)** Создать минимальную тестовую фикстуру
    `tests/fixtures/schematics/rc-divider.kicad_sch` (V1 + R1 + C1 +
    GND, single sheet, 5 компонентов). Полностью под контролем
    T025.
  - **(b)** Заменить acceptance fixture на существующий
    `op-amp-inverting` (simplest existing template, single sheet,
    ~10 components).
  - **(c)** Прогнать render на всех 8 templates (полное покрытие,
    +CI time).

  **Рекомендация — (b)** `op-amp-inverting` вместо `rc-divider`:
  существующая фикстура, не создаём новую (scope discipline);
  включает op-amp макромодель (тестирует non-trivial topology).
  Возможен hybrid: `op-amp-inverting` (small) + `se-amp` (medium) +
  `tube-pp-amp` (large, мульти-tube). Спросить Vladimir.

- **C-3. Render-вызов архитектурно идёт в CLI-adapter, не в use
  case** (пересмотр Q7).

  Обнаружено: `sim_run` use case принимает `netlist: Path` (готовый
  netlist, текст), не `.kicad_sch`. Возвращает `SimulationResult`
  (domain DTO в `domain/simulation.py`). `sim_run` decoupled от
  KiCad — это правильный hexagonal.

  Если расширить `sim_run` параметром `schematic_path` и встроить
  render — use case становится coupled с KiCad CLI. Нарушение
  hexagonal + затрагивает `bridge_sweep` / `design_to_sim` callers
  (которые тоже зовут `sim_run` в loop, не хотят рендерить N раз).

  **Скорректированная архитектура:**
  - Новый use case `application/render_schematic.py:
    render_schematic(sch_path, out_dir) -> SchematicRender` — pure
    function, hexagonal-clean.
  - CLI-adapter `_execute_sim_run` (`src/adapters/inbound/cli/
    app.py:1491+`) вызывает `render_schematic` перед `sim_run`,
    печатает `schematic-render:` строки в stdout, потом обычный
    `sim_run` pipeline.
  - CLI-adapter `_run` для `project create` (app.py:~421)
    вызывает `render_schematic` после успешного `create_project`,
    печатает аналогичные строки.
  - **`SimulationResult` / `CreateProjectResult` не модифицируются.**
    Это упрощает scope T025 (меньше LOC, меньше breaking-surface).

  Q7-resolution из Clarify переписать с «use case-level» на
  «adapter-level invocation of render_schematic use case».

### 🟡 Warning

- **W-1. `bridge_sweep` / `design_to_sim` не должны рендерить.**
  Эти callers вызывают `sim_run` в loop (sweep — десятки итераций).
  C-3 adapter-level fix решает: render — только в `_execute_sim_run`
  и `project create` adapters, не в `sim_run` use case. Sweep
  использует `sim_run` напрямую без adapter — render не выполняется
  автоматически. Note: можно добавить `bridge sweep --render-baseline`
  follow-up если потребуется.

- **W-2. Render-failure vs acceptance criteria.**
  Acceptance требует stdout `schematic-render:` строки. Fail-soft
  (render fails → no string, continue sim) даёт corner case где
  acceptance fails technically. Уточнить:
  - **Happy-path acceptance (3 fixtures):** валидный `.kicad_sch` →
    `schematic-render:` строки + sim успех.
  - **Sim-failure acceptance:** валидный `.kicad_sch` (render OK) +
    invalid netlist (sim fails) → render строки есть, exit-code !=
    0.
  - **Double-failure (render + sim fail)** — НЕ acceptance, log
    warnings, exit-code != 0. Debug-only path.

- **W-3. Multi-sheet ordering из `kicad-cli sch export svg`.**
  kicad-cli `--help` не документирует порядок sheet-файлов в OUTPUT_DIR.
  Эмпирически нужно проверить (root-first vs alphabetical).
  Fixation: `SchematicRender.png_paths` упорядочен `sorted()` by
  filename — стабильный порядок независимо от kicad-cli поведения.

- **W-4. Storage path в test scope.**
  `<project>/.efactory/renders/<TS>/` — для user-projects (живут
  в `~/.efactory-state/projects/<name>/`, не в repo). Тесты пишут
  в `pytest tmp_path` (как существующие integration tests). `.gitignore`
  repo не нужно трогать.

### 🟢 Note

- **N-1. `magick` CLI syntax.** IM7 prefer `magick <input> <output>`
  над legacy `magick convert <input> <output>`. Если решим (b)
  rsvg-convert — moot. Если magick — используем `magick` напрямую.

- **N-2. KB sync L1+L2 — обязательно.**
  L1: `agent.command-routing` table — фразы «покажи схему», «отрисуй
  проект», «как выглядит схема» → routing в `/sim-run` (auto-show)
  или `/project-create`. L2: parametrized regression case в
  `tests/integration/agent_kb/test_control_examples.py`. L3 smoke —
  не требуется (нет KB infrastructure change, только routing
  delta).

- **N-3. Render в `bridge edit-and-resim` (T021) — follow-up.**
  Logical extension: показывать схему «до» и «после» edit. Out of
  scope T025; зафиксировать в BACKLOG если understand polishing
  T021 UX.

- **N-4. `SchematicRenderError` handling в CLI adapter.**
  Adapter ловит SchematicRenderError → stderr warning «render
  failed: <reason>» → continue без render-строк в stdout. Exit-code
  отражает основной pipeline (sim или create-project), не render
  failure (fail-soft per FR 3.2/3.3).

---

## Status гейтов

- Round 1 Clarify ✓
- Round 2 Clarify ✓
- Analyze ✓
- 🔴 решения от Vladimir (2026-06-02):
  - **C-1** → (b) `librsvg2-bin` + `rsvg-convert`.
  - **C-2** → (b) fixtures `op-amp-inverting + se-amp + tube-pp-amp`.
  - **C-3** → Q7 corrected: adapter-level render-вызов.
- Implementation — готово к старту по фазам.
