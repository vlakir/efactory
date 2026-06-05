# Spec: T035 — Публикационный workflow как slash-команды

**Статус:** Analyzed
**Дата создания:** 2026-06-05
**Связанные документы:**

- `specs/T025-schematic-visualization/spec.md` — `KicadCliSchematicRenderer`
  (kicad-cli sch export svg + rsvg-convert), pattern timestamp-каталога
  `<out_root>/<UTC-timestamp>/`.
- `specs/T024-bridge-plot/` (если есть) — `plot_renderer.py` ASCII +
  PNG (matplotlib Agg, dpi=120). T035 переиспользует render-функции
  и параллельно вводит publication-grade варианты dpi=300.
- `specs/T022-bridge-sweep/spec.md` — `render_sweep_plot` (parametric).
- `specs/T023-measurements/spec.md` — measurement runners
  (gain/bandwidth/THD/phase-margin) → секция Summary sim-report.
- `specs/T029-erc-quality-gate/spec.md` — `kicad-cli` adapter pattern.
- `specs/T113-fem-solver/spec.md` — magnetics (FEM) artefact location
  для M-thin режима sim-report.
- `BACKLOG.md` T035 (формулировка 2026-06-03).
- Проектный `CLAUDE.md` — «Дисциплина sync с Agent Knowledge Base»
  Уровни 1+2 для новой slash-команды.

---

## 1. Overview

Vladimir пишет научно-технические статьи и отчёты по проектам РЭА,
спроектированным в efactory. На каждую публикацию нужны два класса
артефактов: (1) **схема** в publication-grade форматах (vector SVG/PDF
для верстальщика + raster PNG@300DPI для черновой вставки в Markdown
/ Word), в color и black-and-white версиях; (2) **отчёт о симуляции**
— Markdown-документ с подписанными графиками и таблицами метрик
(gain, bandwidth, THD, phase-margin и т.п.) для прямой вставки в
draft статьи. Сейчас всё это собирается вручную из терминальных
artefacts ASCII-плоттера и одиночных SVG из T025 — медленно и не
воспроизводимо. T035 вводит две slash-команды (`/export-schematic-
publication` + `/export-sim-report`), которые формируют каталог
`<project>/out/publications/<ts>/` с готовым к публикации набором.

## 2. User Stories

- **(US-1)** Как разработчик статьи об усилителе SE на 6П3С, я хочу
  одной командой получить схему в SVG / PDF / PNG@300DPI и в
  color / black-and-white версиях, чтобы вставить нужный вариант в
  LaTeX (`\includegraphics`) или в Word без ручного экспорта из
  KiCad GUI.
- **(US-2)** Как разработчик статьи я хочу одной командой собрать
  публикационный sim-report (TRAN / AC / DC sweep / parametric sweep
  графики + summary метрик от измерительных команд + ссылки на
  magnetics-artefacts если они есть), чтобы черновик секции
  «Результаты моделирования» был готов за минуты, а не часы.
- **(US-3)** Как разработчик статьи на русском языке я хочу, чтобы
  подписи осей графиков были на русском по умолчанию, а флагом
  `--lang en` переключались на английский для international submission.
- **(US-4)** Как пользователь, который уже запускал симуляцию через
  `/sim-run`, я хочу что `/export-sim-report` переиспользовал
  существующие результаты без перерасчёта; с опциональным флагом
  `--rerun` для свежего прогона.

## 3. Functional Requirements

### `/export-schematic-publication <project>` + CLI

- **ДОЛЖНА** принимать `<project>` — slug проекта в bind-mounted
  `data/projects/` (как `project-use` / `project-create`). Абсолютные
  пути НЕ принимаются (consistent с runtime-agent conventions).
- **ДОЛЖНА** генерировать **три формата артефактов** одной командой:
  - **SVG** (vector, через `kicad-cli sch export svg`);
  - **PDF** (vector, через `kicad-cli sch export pdf`);
  - **PNG @ 300 DPI** (raster, через `rsvg-convert --dpi-x 300
    --dpi-y 300` из SVG).
- **ДОЛЖНА** генерировать **две цветовые схемы** одной командой:
  - **color** (KiCad default theme);
  - **bw** (`--black-and-white` флаг kicad-cli).
- **ДОЛЖНА** поддерживать флаг `--multi-sheet-mode per-sheet|combined`
  (default `per-sheet`). `per-sheet` — отдельный файл на лист (как
  T025). `combined` — единый PDF со всеми листами через `kicad-cli`
  multi-sheet export feature (если доступно) или склейка post-hoc.
  Для PDF — combined; SVG/PNG combined невозможен (нет multi-page) —
  при `--multi-sheet-mode combined` оба формата остаются per-sheet
  с warning в README.
- **ДОЛЖНА** сохранять артефакты в структуре:

  ```
  <project>/out/publications/<ts>/schematic/
    color/
      per-sheet/                       (default mode)
        <sheet-name>.svg
        <sheet-name>.pdf
        <sheet-name>.png               (300 DPI)
      combined/                        (only when --multi-sheet-mode=combined)
        <project>.pdf
    bw/
      ... (mirror structure)
  ```

- **ДОЛЖНА** генерировать `<project>/out/publications/<ts>/README.md`
  с описанием: список файлов, DPI, формат, дата генерации, версия
  efactory, имя проекта. Язык — `--lang ru|en` (default `ru`).
- **ДОЛЖНА** возвращать exit code 0 при успехе, non-zero при провале
  kicad-cli (с информативным stderr из adapter chain T029-style).
- **ДОЛЖНА** печатать stdout уведомление в каскадном стиле T025:
  `publication-export: <abs_path_to_publications_ts>` — для агента-
  визарда и downstream tooling.

### `/export-sim-report <project> [--rerun]` + CLI

- **ДОЛЖНА** принимать `<project>` (slug, как выше) и опциональный
  `--rerun` (default `false`).
- **БЕЗ `--rerun`** — использовать существующие результаты в
  `<project>/out/sim/<latest_ts>/` (стандартное место выхода
  `/sim-run`); если результатов нет — fail с понятной ошибкой
  «no simulation results found; run `/sim-run <project>` first
  or use `--rerun`».
- **С `--rerun`** — запустить use case `design_to_sim` (тот же что
  `/sim-run` использует) для свежих результатов, затем формировать
  отчёт.
- **ДОЛЖНА** включать в отчёт следующие виды анализа из доступных
  в результатах симуляции:
  - **TRAN** — waveforms через `render_time_series_publication_png`
    (matplotlib dpi=300, locale-aware подписи);
  - **AC** — Bode (magnitude в dB) через
    `render_ac_sweep_publication_png` (log-x, dpi=300);
  - **Parametric sweep** (T022) — `render_sweep_plot_publication_png`
    (dpi=300, group-by support);
  - **Magnetics (T113-T133)** — **M-thin режим**: ссылки на
    готовые FEM artefacts (если найдены в `<project>/out/fem/`)
    + табличный summary метрик из последнего FEM-run
    (L_self, L_leak, B_peak, losses). НЕ генерирует новых
    FEM-плотов в T035.
  - **Measurements** (gain/bandwidth/THD/phase-margin) — секция
    «Summary», вытягивается из результатов запуска
    measurement-команд если они есть в `<project>/out/measurements/`
    (если нет — секция отсутствует).
- **ДОЛЖНА** сохранять артефакты в структуре:

  ```
  <project>/out/publications/<ts>/sim-report/
    report.md                    (главный документ — Markdown)
    plots/
      tran-<signal>.png          (300 DPI)
      ac-<signal>.png
      param-sweep-<y>-vs-<x>.png
    tables/                      (опционально, если есть metrics)
      summary.md                 (включается inline в report.md тоже)
  ```

  `report.md` ссылается на `plots/*.png` через `![alt](plots/...)`
  relative paths (portable Markdown).
- **ДОЛЖНА** в начале `report.md` секцию «Метаданные» с проектом,
  датой, версией efactory, source-ts симуляции (когда без `--rerun`).
- **ДОЛЖНА** генерировать `<project>/out/publications/<ts>/README.md`
  — то же что в schematic publication (либо общий README на ts-
  каталог, если обе команды вызывали на один и тот же `<ts>` —
  acceptable redundancy, см. Q11).
- **ДОЛЖНА** работать на всех 10 шаблонах из `data/templates/`
  (как минимум не падать; smoke check в integration tests).

### Общее

- **МОЖЕТ** генерировать пустые секции (с notice «no AC sweep data
  in this simulation») вместо fail, если конкретный анализ не
  запускался — для устойчивости к heterogeneous проектам.
- **НЕ ДОЛЖНА** генерировать PDF-документ со статьёй (`\documentclass
  ...`, abstract, references) — только building-blocks для вставки.
- **НЕ ДОЛЖНА** генерировать LaTeX/Markdown-сниппеты для прямой
  вставки (`\begin{figure}…`) — только описательный README (Q7=a).
- **НЕ ДОЛЖНА** добавлять новые виды симуляционного анализа —
  только публикационная packaging существующих.
- **НЕ ДОЛЖНА** трогать PCB-модуль (gerber preview, layer stackup) —
  это Фаза 4 (T037–T049).
- **НЕ ДОЛЖНА** добавлять BOM-секцию в sim-report (отдельная задача
  для PCB Фазы 4).

## 4. Success Criteria

- **(SC-1)** На тестовом проекте `se-amp` команда
  `/export-schematic-publication se-amp` за <60 секунд создаёт:
  - 6 файлов в `color/per-sheet/` (.svg + .pdf + .png — на каждый
    лист, у se-amp один лист → 3 файла);
  - 3 файла в `bw/per-sheet/`;
  - `README.md` ≥10 строк с описанием каждого файла;
  - exit 0.
- **(SC-2)** На тестовом проекте `se-amp` команда `/export-sim-report
  se-amp` (после предварительного `/sim-run se-amp`) за <30 секунд
  создаёт `report.md` с минимум одной TRAN-секцией и одной AC-
  секцией, plots/ каталог содержит ≥2 PNG-файла @ 300 DPI,
  metadata-секция содержит все обязательные поля.
- **(SC-3)** На том же проекте `/export-sim-report se-amp --rerun`
  запускает симуляцию с нуля и формирует отчёт; total time
  <120 секунд.
- **(SC-4)** Каждая публикационная PNG-функция (`render_*_publication_png`)
  имеет dpi=300 и проходит unit-тест проверки `Image.info['dpi'] ==
  (300, 300)` (Pillow read).
- **(SC-5)** Подписи осей в `--lang ru` — кириллица («частота, Гц
  (лог.)», «магнитуда, дБ», «время, с» и т.д.). В `--lang en` —
  английский (как сейчас). Verified unit-тестами на каждую функцию.
- **(SC-6)** Multi-sheet smoke: на `tube-pp-amp` (если multi-sheet)
  или на синтетическом multi-sheet проекте `--multi-sheet-mode
  combined` создаёт **один** PDF-файл во `combined/` подкаталоге;
  SVG/PNG остаются per-sheet с warning в README.
- **(SC-7)** На всех 10 templates `/export-sim-report --rerun`
  не падает (smoke integration test параметризированный по проектам).
- **(SC-8)** KB Уровень 1: bullet добавлены в
  `docker/runtime-agent-CLAUDE.md`, обе команды в mapping table
  `agent.command-routing`. KB topic `design.export-publication` для
  совместного описания workflow (опционально per-command topics
  если acceptance тестирование покажет необходимость).
- **(SC-9)** KB Уровень 2: parametrized regression test для обеих
  команд в `tests/integration/agent_kb/test_control_examples.py`.
- **(SC-10)** Pre-push 5/5 ✓: `ruff check`, `ruff format --check`,
  `mypy`, `pytest` (coverage ≥80% на новых модулях), importlinter
  contracts 3/3.

## 5. Key Entities

### Domain VOs

- **`PublicationBundle`** — главная aggregate, неизменяемая, frozen.
  Содержит `project: ProjectSlug`, `timestamp: datetime` (UTC),
  `efactory_version: str`, `lang: PublicationLang` (`RU`/`EN`),
  `schematic: SchematicPublicationArtifacts | None`,
  `sim_report: SimReportArtifacts | None` (одна из двух обязательна).
- **`SchematicPublicationArtifacts`** — group:
  - `color_per_sheet: tuple[SheetArtifactSet, ...]`,
  - `bw_per_sheet: tuple[SheetArtifactSet, ...]`,
  - `color_combined: Path | None`, `bw_combined: Path | None`
    (только при `--multi-sheet-mode combined`).
- **`SheetArtifactSet`** — `sheet_name: str`, `svg: Path`,
  `pdf: Path`, `png: Path` (300 DPI).
- **`SimReportArtifacts`** — `report_md: Path`, `plots: tuple[Path,
  ...]`, `tables: tuple[Path, ...]`, `source_simulation_ts:
  datetime | None` (None при `--rerun` для свежего прогона).
- **`PublicationLang`** — enum `RU` / `EN`.
- **`MultiSheetMode`** — enum `PER_SHEET` / `COMBINED`.

### Ports (outbound)

- **`SchematicPublicationRenderer`** — port (Protocol):
  - `render(schematic: Path, *, out_dir: Path, color: bool, multi_sheet_mode: MultiSheetMode) -> SchematicPublicationArtifacts`
- **`SimReportWriter`** — port (Protocol):
  - `write(sim_results: SimulationResultsBundle, *, out_dir: Path, lang: PublicationLang) -> SimReportArtifacts`
- **`PublicationReadmeWriter`** — port (Protocol, простой):
  - `write(bundle: PublicationBundle, *, out_dir: Path) -> Path`

### Adapters

- **`KicadCliSchematicPublicationRenderer`** — реализация
  `SchematicPublicationRenderer`. Использует существующий `AppManager`
  (T009) для `kicad-cli sch export svg|pdf [--black-and-white]`.
  Использует `rsvg-convert --dpi-x 300 --dpi-y 300` для PNG@300.
- **`MarkdownSimReportWriter`** — реализация `SimReportWriter`.
  Композирует `report.md` через jinja2 (если уже в зависимостях) либо
  через f-string template helpers (KISS). Вызывает publication-grade
  plot-функции из `cli/publication_plots.py`.
- **`MarkdownPublicationReadmeWriter`** — реализация README writer'а.

### Use cases (application layer)

- **`run_export_schematic_publication(project: str, *, multi_sheet_mode: MultiSheetMode, lang: PublicationLang) -> PublicationBundle`**
- **`run_export_sim_report(project: str, *, rerun: bool, lang: PublicationLang) -> PublicationBundle`**

### CLI / slash

- `efactory publication export-schematic <project> [--multi-sheet-mode ...] [--lang ru|en]`
- `efactory publication export-sim-report <project> [--rerun] [--lang ru|en]`
- `/export-schematic-publication <project>` → routes to CLI (KB
  Уровень 1).
- `/export-sim-report <project>` → routes to CLI.

## 6. Assumptions & Constraints

- **(A-1)** Все артефакты — read-only вывод, никаких мутаций входной
  схемы / шаблонов / результатов симуляции.
- **(A-2)** `<ts>` — UTC timestamp в формате T025 (`%Y%m%dT%H%M%SZ`),
  consistent с другими out-каталогами efactory.
- **(A-3)** При вызове обеих команд подряд каждая создаёт **свой**
  `<ts>`-каталог (не объединяются автоматически в один) — упрощает
  semantics, downside малозначителен (publications/ копится).
- **(A-4)** PDF combined-mode для multi-sheet полагается на
  встроенный multi-sheet export kicad-cli; если он создаёт несколько
  PDF — склейка через `pypdf` (light dep) в порядке имён файлов.
  Решение по dep — в Phase 2 implementation.
- **(A-5)** Для magnetics M-thin: detection FEM artefacts через
  существование `<project>/out/fem/<latest_ts>/` каталога; формат
  метрик читается из его summary JSON (предположение, что T113
  пишет такой; проверить в Phase 2).
- **(A-6)** Publication PNG dpi=300 — индустриальный standard для
  печатных публикаций; меньше — теряется детализация, больше —
  overkill и большой файл.
- **(A-7)** `--lang ru` подписи берутся из in-memory dict (i18n
  без gettext-overkill — 10-15 строк key/value на 2 языка).
- **(A-8)** Запрос Vladimir-а Q7=(a) означает README **только**
  с описанием файлов; LaTeX/Markdown-фрагменты НЕ генерируем
  (out of scope).

## 7. Out of Scope

- **PDF compose со статьёй** (documentclass, abstract, references,
  citations) — это работа автора, не efactory.
- **LaTeX/Markdown-сниппеты для прямой вставки** в README или
  отдельным файлом — Vladimir Q7=(a).
- **PCB publication** (gerber preview, board photo, layer stackup) —
  Фаза 4, отдельные задачи (T037+).
- **BOM publication** (component table для статьи) — Фаза 4.
- **Magnetics M-thick** (B-field maps, mesh viz, hysteresis curves
  как publication plots) — отдельная задача в BACKLOG (заведём при
  Phase 6 finalization).
- **3D-сборка / mechanical drawings** — не реализовано в efactory
  вообще, не в этом scope.
- **Auto-versioning артефактов** между прогонами (diff между
  publication runs, change-log) — может быть полезно в будущем,
  но в T035 не делаем.
- **Watermark / digital signature** на артефактах — не требуется.
- **Email / arxiv upload integration** — не наша задача.

---

## Clarify (заполняется Claude)

### Open questions

Нет. Все Q1-Q8 + 4 follow-up разрешены до начала analyze.

### Resolved (с ответами)

- **(Q1)** Формат schematic publication — **(c) SVG + PDF + PNG@300
  DPI оба одной командой** (Vladimir 2026-06-05).
- **(Q2)** Цветовая схема — **оба варианта (color + bw) в подкаталогах**
  одной командой (Vladimir 2026-06-05).
- **(Q3)** Multi-sheet — **отдельный флаг** `--multi-sheet-mode
  per-sheet|combined`, default `per-sheet` (follow-up подтверждён).
- **(Q4)** `/export-sim-report` — **все перечисленные виды анализа**
  (TRAN / AC / Parametric sweep / Magnetics M-thin / Measurements
  summary) (Vladimir 2026-06-05). **DC sweep вырезан** после
  Analyze C-1 — отсутствует как тип симуляции в efactory; вынесен
  в BACKLOG как T188 (Vladimir подтверждение 2026-06-05).
  Magnetics уточнён как M-thin (Vladimir 2026-06-05 follow-up):
  только табличный summary + ссылки на готовые FEM artefacts;
  новые publication-plots для magnetics — отдельная задача BACKLOG.
- **(Q5)** Зависимости команд — **(c) флаг `--rerun` опциональный**,
  default — переиспользовать существующие результаты, fail если
  их нет (Vladimir 2026-06-05). Follow-up: timestamp publication
  каталога — **(a) момент publication generation**, README
  показывает `source_simulation_ts` оригинальной симуляции.
- **(Q6)** Структура каталога — **(a) `<project>/out/publications/
  <ts>/{schematic/, sim-report/, README.md}`** (Vladimir 2026-06-05).
- **(Q7)** README content — **(a) только описание файлов** (DPI,
  формат, дата, версия efactory) (Vladimir 2026-06-05). НЕ
  генерируем LaTeX/Markdown фрагменты.
- **(Q8)** Локализация — **`--lang ru|en`, default `ru`** для
  подписей графиков (Vladimir 2026-06-05). README — той же языковой
  настройкой.
- **(Q-A)** `<project>` параметр — **slug** в `data/projects/`
  (consistent с `project-use` / `project-create`), не абсолютный
  path. Подтверждено follow-up.
- **(Q-B)** Acceptance тестовый проект — **`se-amp`** baseline
  + опционально `tube-pp-amp` для multi-sheet smoke (если у него
  multi-sheet, иначе синтетический). Подтверждено follow-up.

---

## Analyze (заполняется Claude)

Проведён 2026-06-05 после Clarify. Проверено через
`kicad-cli sch export pdf|svg --help`, `command -v rsvg-convert`,
grep'ы по `src/domain/simulation.py`, `src/`, `Dockerfile`.

### 🔴 Critical

- **(C-1) DC sweep НЕ существует в efactory как тип симуляции.**
  `src/domain/simulation.py` содержит только `OpAnalysis`,
  `TranAnalysis`, `AcAnalysis`, `FourierAnalysis` + результаты
  `TimeSeries`, `AcSweep`, `FourierResult`. DC sweep (`.dc V1 …`
  в ngspice) — отдельный тип анализа со своим результатом
  (parametric trace), не реализован ни в domain, ни в SPICE
  adapter, ни в renderer. Включение DC sweep в FR T035 = +1 фаза
  работы (domain extension + ngspice parsing + plot) = scope creep
  на ~2-3 дня. **Fix:** вырезать DC sweep из FR T035, завести
  отдельную задачу в `BACKLOG.md` (новый T-ID), в README sim-
  report'а ничего про DC не упоминать. Требует подтверждения
  Vladimir.

- **(C-2) Assumption A-4 неверна: PDF combined-mode из kicad-cli
  native, pypdf не нужен.** `kicad-cli sch export pdf` без
  `--pages` создаёт **один combined PDF** со всеми листами
  (output — `OUTPUT_FILE`, не каталог). Per-sheet PDF = N
  вызовов с `--pages 1`, `--pages 2`, ... каждый со своим
  `--output <sheet-name>.pdf`. **Fix:** убираем pypdf-зависимость
  из плана; combined = одна команда; per-sheet = цикл по
  sheet'ам с явным `--pages I`. Уточнение FR в Phase 2.

### 🟡 Warning

- **(W-1) `rsvg-convert` отсутствует на host (`command -v` пусто).**
  В `Dockerfile` (Stage 1, line 92) — `librsvg2-bin` стоит, в
  `efactory:linux` контейнере rsvg-convert будет. Это значит:
  acceptance integration тест **должен** запускаться внутри
  контейнера (как T029 design-check), не на host. **Fix:**
  для SC-1/SC-2/SC-3/SC-6 — pytest fixture с docker-bind-mount
  pattern; unit тесты — mocked `_rsvg_convert` (как в
  существующих тестах T025 renderer'а).

- **(W-2) Magnetics summary JSON формат не подтверждён.** T113
  пишет FEM-результаты в `out/fem/<ts>/` (вероятно), формат
  metrics JSON не проверен. Если формат не подходит / отсутствует
  — M-thin режим деградирует до warning в README «magnetics
  artefacts found but format not recognized». **Fix:** Phase 2
  implementation начнётся с probe актуального формата T113-output;
  если M-thin невозможен — Spec корректируется (M-thin → пропуск
  секции, не fail), в BACKLOG заводится «adapter для magnetics
  summary в publication-report».

- **(W-3) Multi-sheet smoke на `tube-pp-amp` (SC-6) — не
  гарантировано, что у него multi-sheet.** Все шаблоны в
  `data/templates/` визуально one-sheet (один `.kicad_sch`).
  **Fix:** в Phase 5 (smoke tests) создать **синтетический**
  multi-sheet проект через программный builder (sub-sheet
  через `Schematic` facade T100) — иначе SC-6 unverifiable.

- **(W-4) `<ts>` collision при ускоренном вызове двух команд.**
  Если Vladimir вызовет `/export-schematic-publication se-amp` и
  немедленно `/export-sim-report se-amp` — timestamp может
  совпасть (одинаковая секунда). Сейчас A-3 говорит «каждая
  создаёт свой ts», но при совпадении секунды второй вызов
  попадёт в **уже существующий** каталог и **потенциально
  перезапишет README.md**. **Fix:** при создании ts-каталога
  если он уже существует и содержит файлы — добавлять суффикс
  `-1`, `-2` (как rotate-логика); либо использовать ms-resolution
  timestamp. Реализация в Phase 1 domain helper'е.

### 🟢 Note

- **(N-1) Per-sheet PDF requires N kicad-cli invocations.**
  Не блокер, но усложняет implementation на ~10 LOC + N×kicad-cli
  spawn'ов вместо одного. Альтернатива: создать combined PDF и
  split через pypdf обратно — но это лишняя dep, отвергаем.

- **(N-2) Каждая команда → свой `<ts>` → свой README.** Уточняю
  FR (`README.md` отдельный для каждого вызова, не общий
  shared). Никакой merge-logic между двумя командами не делаем.
  Если Vladimir хочет «общий» — может вызвать обе команды и
  скопировать вручную, либо ввести `/export-publication-bundle`
  в BACKLOG как follow-up задачу.

- **(N-3) jinja2 vs f-string templates.** `pyproject.toml`
  проверить в Phase 2 — если jinja2 уже dep (T100 builder
  использует), берём её; иначе f-string + helpers (KISS).
  Decision в Phase 2, не блокирует spec.

- **(N-4) `project-use` "current project" state.** Опциональная
  ergonomics: если context активного проекта установлен
  (`project-use <slug>`), команды могут принимать пустой
  `<project>`. Не блокер; могу включить в Phase 4 как nice-to-have
  если время позволит. Если нет — отдельная задача в BACKLOG.

- **(N-5) Pillow для SC-4 проверки `Image.info['dpi']`.**
  Pillow — transitive dep matplotlib, на месте. Подтверждено
  `uv pip show pillow` (если нужно — проверю в Phase 1).

- **(N-6) `kicad-cli` `--theme` flag.** Color theme задаётся
  проектом по умолчанию, но можно `--theme <name>` override.
  Для publication-color возьмём KiCad default (consistent с
  T025); для BW — `--black-and-white`. Никакого custom-theme
  selection в T035 не делаем.

- **(N-7) Caching результатов между color/bw exports.**
  KiCad-cli rerun-overhead ~5-10s на запуск. Для одного проекта:
  color SVG + BW SVG + color PDF + BW PDF + (per-sheet × N) =
  4-6 kicad-cli вызовов. На se-amp (1 sheet) — ~20-40s. В
  пределах SC-1 (<60s). Если станет узким местом — рассмотреть
  parallelization (asyncio.gather) как follow-up.

### Решения для Phase 2

После C-1/C-2 fix'ов:

- DC sweep — удалить из FR Q4-list, завести `T<NEXT>` в BACKLOG.
- pypdf — убрать из плана.
- `combined` PDF — одна команда без `--pages`; `per-sheet` PDF —
  цикл с `--pages I`.

Phase 0 не требуется (нет «грязных» шаблонов для подготовки).
Implementation phases начинаются с Phase 1 (domain VOs + TDD).
