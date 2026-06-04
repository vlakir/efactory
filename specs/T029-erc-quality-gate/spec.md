# Spec: T029 — ERC quality gate

**Статус:** Analyzed
**Дата создания:** 2026-06-04
**Связанные документы:**
- BACKLOG.md → Фаза 3 → T029 (исходная формулировка, reformulated 2026-06-03).
- ADR 2026-05-19 «no MCP, CLI + filesystem» (отказ от `kicad-mcp-pro`).
- T021 — `efactory:linux` контейнер с предустановленным KiCad 10.x.
- T025 — `kicad-cli` adapter pattern (schematic renderer).
- T026 — staged-modifications: T029 гоняет ERC по working copy (применённой
  schematic), а не по staged-диффу.
- T134 — KB sync дисциплина: новый KB topic `design.erc-quality-gate` +
  командное routing для `/design-check`.

---

## 1. Overview

ERC quality gate подключает `kicad-cli sch erc` к pipeline'у дизайна
**как hard-блокер** перед SPICE-симуляцией: схема с ERC errors не доходит
до ngspice, пользователь получает понятный отчёт с путями нарушений вместо
загадочного «нет операционной точки» или netlist-stub'а. Warnings проходят,
но рендерятся в human-readable markdown-отчёт в `out/erc/<ts>/report.md` —
visibility без блокировки.

Standalone-команды `/design-check <project>` и `efactory design check
<project>` дают разработчику запустить ERC без симуляции (например — после
вручную поправленного `.kicad_sch`, до коммита) с теми же отчётами.

Фича заменяет режим «sim молча запустился на сломанной схеме → debug чёрным
ящиком» на «fail-fast at design-time с точной локализацией нарушения».

## 2. User Stories / Сценарии использования

- **US1.** Как разработчик, я запускаю `/sim-run` на чистой схеме →
  pipeline проходит как раньше, в stdout одна строка `ERC: 0 errors,
  0 warnings`, симуляция выполняется.
- **US2.** Как разработчик, я запускаю `/sim-run` на схеме с ERC error
  (например, неподключённый пин Op-amp) → симуляция **не запускается**,
  exit-code != 0, в stdout — суммарное сообщение и путь к
  `out/erc/<ts>/report.md` с локализацией нарушения (symbol U1, pin 1,
  pos x/y, uuid).
- **US3.** Как разработчик, я запускаю `/sim-run` на схеме с warnings (но
  без errors) → симуляция выполняется, в stdout — `ERC: 0 errors, N
  warnings → out/erc/<ts>/report.md`, без блокировки.
- **US4.** Как разработчик, я запускаю `/design-check <project>` после
  ручного редактирования `.kicad_sch` в KiCad GUI → standalone-проверка
  без вызова ngspice, тот же markdown-отчёт, понятный exit-code.
- **US5.** Как разработчик/CI, я зову `efactory design check
  <project>` напрямую (без slash-обвязки) → идентичная семантика, exit-
  code 0 (ok), 1 (errors), 2 (kicad-cli unavailable / parse fail).

## 3. Functional Requirements

### ДОЛЖНА

- F1. Вызывать `kicad-cli sch erc --format json --severity-all --output
  <tmp.json> <schematic>` с `LANG=C` для стабильного локалью-независимого
  stderr.
- F2. Парсить выход по JSON-schema `https://schemas.kicad.org/erc.v1.json`
  (probe-verified 2026-06-04, KiCad 10.0.3).
- F3. Группировать violations **по полю `type`** (стабильный английский
  ID), не по `description` (локализован).
- F4. Считать счётчики по severity (`error` / `warning` / `exclusion`).
- F5. На наличие хотя бы одного `severity=error` — бросать
  `ErcErrorsFoundError(ErcReport)` из use-case `run_erc_check`.
- F6. На warnings без errors — возвращать `ErcReport` без исключения,
  pipeline продолжает.
- F7. Сохранять human-readable markdown-отчёт в
  `<project_root>/out/erc/<UTC-ISO-ts>/report.md`, рядом — копию
  raw `erc.json`.
- F8. Markdown-отчёт включает: header (timestamp / schematic / kicad
  version), summary (counts по severity), таблицу violations
  (severity / type / description), детализацию по каждой violation с
  items (symbol-описание, pos x/y, uuid).
- F9. Hard-fail на отсутствие `kicad-cli` в PATH →
  `KiCadCliUnavailableError`.
- F10. Hard-fail на malformed JSON / отсутствующий expected key →
  `ErcParseError`.
- F11. CLI `efactory design check <project>` принимает `<project>` как
  путь к проекту (директория с `.kicad_sch`) или путь к файлу
  `.kicad_sch` напрямую (через типизированный аргумент).
- F12. Slash `/design-check [<project>]` — auto-detect `.kicad_sch` в cwd
  (pattern скопирован из `/sim-run` — top-level + 1 subdir, ровно 1
  match).
- F13. `efactory bridge sim-run` интегрирует ERC gate **перед** вызовом
  `design_to_netlist` (или внутри `design_to_sim`, на ранней стадии).
- F14. Слаш `/design-check` принимает опциональный `--severity
  error|warning|all` (default `all`) для фильтрации **только отчёта**
  (счётчики и exit-code не меняются).
- F15. Honor'ить `ignored_checks` из выхода KiCad (это exclusions,
  выставленные пользователем в KiCad GUI) — показывать списком в отчёте,
  не считать за errors.

### МОЖЕТ

- M1. Опциональный `--erc-timeout SECONDS` (default 30s) на subprocess
  вызов; превышение → `ErcTimeoutError`.

### НЕ ДОЛЖНА

- N1. **Никакого escape hatch:** запрещено `--no-erc` /
  `--allow-erc-errors` / переменная окружения для пропуска gate. Сломали
  схему → чините схему.
- N2. Не модифицировать `.kicad_sch` для авто-фикса.
- N3. Не поддерживать custom ERC rules / exclusions UI (рассчитываем на
  KiCad GUI).
- N4. Не кешировать результаты ERC между запусками.
- N5. Не вызывать ERC на staged-modifications (T026) — гоняем только по
  working copy.

## 4. Success Criteria

- **SC1.** Все 11 встроенных шаблонов (`data/templates/*/`) после фикса
  4 «грязных» (см. §6.A1) проходят ERC с `error_count == 0` (warnings
  допустимы).
- **SC2.** `/sim-run` на синтетическом проекте с искусственным
  unconnected pin → ngspice **не вызывается**, exit-code != 0, в stdout
  присутствует строка `ERC errors: 1, see out/erc/<ts>/report.md`,
  markdown-файл создан и содержит локализацию пина.
- **SC3.** `/sim-run` на нашем эталонном `se-amp` шаблоне (0 errors, 1
  warning) → симуляция проходит, в stdout `ERC: 0 errors, 1 warnings →
  out/erc/<ts>/report.md`, sim-результат записывается как раньше.
- **SC4.** `/design-check <project>` на проекте с errors → exit-code 1,
  без вызова ngspice, отчёт создан.
- **SC5.** `efactory design check <project>` на не-KiCad директории
  (нет `.kicad_sch`) → exit-code != 0, понятное сообщение.
- **SC6.** Coverage новых модулей ≥80% (проектный threshold). Adapter
  KiCad CLI — integration test против реальной фикстуры.
- **SC7.** Pre-push hooks (5/5) проходят: ruff, format, mypy, lint-
  imports, pytest.
- **SC8.** KB sync (T134 Уровень 1 + 2): новый topic
  `design.erc-quality-gate` + mapping `/design-check` в
  `agent.command-routing` + deterministic regression test для KB-search.

## 5. Key Entities

### Domain layer (`domain/erc.py`)

- `ErcSeverity` — Enum {ERROR, WARNING, EXCLUSION}.
- `ErcItem` — frozen pydantic: `description: str`, `pos: tuple[float,
  float]`, `uuid: str`.
- `ErcViolation` — frozen pydantic: `severity: ErcSeverity`, `type: str`,
  `description: str`, `items: list[ErcItem]`.
- `ErcIgnoredCheck` — frozen pydantic: `key: str`, `description: str`.
- `ErcReport` — frozen pydantic: `kicad_version: str`,
  `schematic_path: Path`, `timestamp: datetime`,
  `violations: list[ErcViolation]`, `ignored_checks: list[ErcIgnoredCheck]`,
  computed counts `error_count`, `warning_count`, `exclusion_count`.

### Domain exceptions (`domain/erc.py`)

- `ErcErrorsFoundError(ErcReport)` — для блокировки sim_run.
- `KiCadCliUnavailableError` — kicad-cli не в PATH.
- `ErcParseError` — malformed JSON или schema mismatch.
- `ErcTimeoutError` — превышен timeout.

### Outbound ports (`ports/outbound/erc.py`)

- `ErcRunner` (Protocol): `async def run(schematic: Path, *,
  timeout_seconds: float) → ErcReport`.
- `ErcReportWriter` (Protocol): `async def write(report: ErcReport,
  out_root: Path) → Path` — возвращает путь к созданному `report.md`.

### Use case (`application/run_erc_check.py`)

- `async def run_erc_check(*, schematic: Path, project_root: Path | None,
  erc_runner: ErcRunner, report_writer: ErcReportWriter | None = None,
  timeout_seconds: float = 30.0) → ErcReport`.
  - При `report_writer is not None and project_root is not None` —
    рендерит отчёт.
  - При `error_count > 0` — бросает `ErcErrorsFoundError(report)`.

### Integration в design_to_sim

- В `application/design_to_sim.py` добавляется первый шаг: вызов
  `run_erc_check(schematic=..., ...)`. Если бросает
  `ErcErrorsFoundError` — пробрасывается наружу (никакого silent skip).
- Сигнатура `design_to_sim` расширяется параметрами `erc_runner` и
  `erc_report_writer`. Композиция в CLI — в `composition/build_app.py`.

### Adapters

- `adapters/outbound/erc_kicad_cli/runner.py` — `KicadCliErcRunner`
  (subprocess wrapper, `LANG=C`, tmp-file output).
- `adapters/outbound/erc_kicad_cli/parser.py` — JSON-парсер с schema-
  validation (проверка `$schema` префикса).
- `adapters/outbound/erc_report_markdown/writer.py` —
  `MarkdownErcReportWriter`, рендерит шаблонизированный markdown.

### CLI / slash

- Новая CLI-группа `efactory design` с командой `check`.
- Slash `/design-check` в `docker/runtime-agent-commands/design-check.md`.
- Bridge `efactory bridge sim-run` — добавляется ERC gate, нет нового
  флага.

## 6. Assumptions & Constraints

- **A1. Чистка шаблонов в-scope T029.** Bundled-PR: 4 шаблона с
  `power_pin_not_driven` / `pin_not_connected` чинятся в этом же PR,
  чтобы acceptance SC1 проходил. Off-grid warnings — отдельный T187
  (вынесен в BACKLOG, не в-scope T029).
  - active-lpf-sallen-key: 1 err (`power_pin_not_driven` на #PWR01).
  - bjt-ce-nfb: 1 err (`power_pin_not_driven` на #PWR01).
  - op-amp-inverting: 1 err (`power_pin_not_driven` на U1 V+).
  - tube-line-preamp: 1 err (`pin_not_connected` на R4 Pin 1 — реальный
    отвязанный пин).

  **Правки выполняются через builders** в
  `tests/integration/adapters/schematic_kicad/test_<name>_facade.py::_build_<name>`,
  не прямой правкой `data/templates/*.kicad_sch`. После правки builder'а —
  `uv run python scripts/regenerate-templates.py --template <name>`
  пересобирает baked artifact. Прямая правка `data/templates/` отвергнута
  (2026-06-05, Phase 0 probe): она ломает snapshot-тесты и стирается
  следующим `regenerate-templates.py`. Снимки/facade-тесты обновляются по
  необходимости — это ожидаемая стоимость bundled подхода. Probe-результат
  (прямые правки): все 11 шаблонов = 0 ERC errors, R4→/grid2 canonical
  grid-leak. Path-of-implementation подтверждён, повторяем через builders.
- **A2.** KiCad 10.0.3+ (probe-verified). `kicad-cli sch erc` API
  стабилен с KiCad 8.x, `$schema = erc.v1.json` стабилен.
- **A3.** В `efactory:linux` контейнере `kicad-cli` всегда установлен
  (T021 Phase 1). На dev-машине Vladimir-а — KiCad apt-package.
- **A4.** `description` в JSON локализован → парсим только `type`.
- **A5.** Multi-sheet и single-sheet схемы — обе поддержки (probe
  показал массив `sheets[]`).
- **A6.** При запуске `kicad-cli sch erc` КiCad подхватывает соседний
  `.kicad_pro` автоматически (project-level rules, custom severity
  overrides). Мы не передаём `.kicad_pro` явно, не редактируем его.
- **A7.** Standard `out/<subdir>/<ts>/...` layout проекта.

## 7. Out of Scope

- DRC (Design Rule Check, на `.kicad_pcb`) — Фаза 4, PCB-модуль.
- Beautifier (T106 Phase 0+) — текстовые overlap'ы, wire routing.
- Кастомные ERC rules — пользователь настраивает в KiCad GUI на
  `.kicad_pro`, мы honor'им.
- Авто-фикс ERC violations — facade.py уже ставит PWR_FLAG/NoConnect для
  части кейсов, но это not part of T029. Расширение auto-fix покрытия —
  отдельная задача.
- ERC на staged-modifications (T026) — гоняем только по applied
  working copy.
- Caching ERC между запусками — каждый /sim-run и /design-check заново
  гоняет kicad-cli. При узком месте — отдельная задача.
- Off-grid warnings массовая чистка шаблонов — отдельный **T187**
  (вынесен в BACKLOG).
- ERC web-export / GUI — только markdown + JSON, никаких рендеров SVG.

---

## Clarify (заполняется Claude)

### Open questions

(закрыто — см. Resolved.)

### Resolved (с ответами)

- **R1. (Vladimir, 2026-06-04)** Bundled-PR (Strategy B): T029 ship'ит
  и hard-gate, и фикс 4 «грязных» шаблонов в одном PR. Не нарушает
  scope discipline (fixing templates чтобы они проходили новый gate).
- **R2. (Vladimir, 2026-06-04)** Off-grid warnings массовая чистка
  вынесена в **T187** (BACKLOG, не в-scope T029).
- **R3. (Vladimir, 2026-06-04)** Markdown-отчёт сохраняется в
  `<project_root>/out/erc/<UTC-ISO-ts>/report.md`.
- **R4 ← Q1. Markdown формат — table-based + Ignored Checks.**
  Структура отчёта (final):
  ```markdown
  # ERC Report — <schematic-basename>

  - **Schematic:** <abs path>
  - **Timestamp:** <UTC ISO 8601>
  - **KiCad version:** 10.0.3
  - **Summary:** errors=N, warnings=M, exclusions=K

  ## Violations

  ### error: power_pin_not_driven (×N)

  *Description:* Input Power pin not driven by any Output Power pins.

  | Symbol | Pos (mm) | UUID |
  |---|---|---|
  | U1 Pin 1 [+] | 0.82, 0.72 | d7cd0635-... |

  ### warning: endpoint_off_grid (×M)

  ...

  ## Ignored Checks

  *Checks excluded by KiCad GUI (`.kicad_pro` exclusions or built-in
  ignored severities):*

  - `single_global_label` — Global label only appears once in the
    schematic.
  - `simulation_model_issue` — SPICE model issue.
  ```
  Группировка violations по `type` внутри severity-section, сортировка
  errors → warnings → exclusions. Ignored Checks — отдельный раздел в
  конце.
- **R5 ← Q2. `/sim-run` stdout — одна строка summary.** При warnings
  без errors: `ERC: 0 errors, N warnings → out/erc/<ts>/report.md`.
  При errors: `ERC errors: N (out/erc/<ts>/report.md) — sim skipped`.
  Без breakdown по type в stdout — детали в markdown.
- **R6 ← Q3. CLI exit-codes:** `0` — ok (error_count == 0); `1` —
  ERC errors > 0; `2` — infrastructure fail (kicad-cli unavailable,
  parse error, timeout).
- **R7 ← Q4. `/design-check` auto-detect.** Без аргумента — pattern
  из `/sim-run` (find `.kicad_sch` top-level + 1 subdir cwd, ровно 1
  match). С аргументом — принимаем напрямую путь к `.kicad_sch` или
  к директории проекта (в последнем случае — auto-detect внутри
  директории). Multi-match без аргумента → ask user (как `/sim-run`).
- **R8 ← Q5. ERC gate — самый ранний выход в `design_to_sim`.**
  Выбран вариант (a): ERC вызывается **до** `design_to_netlist`,
  гоняется по реальному `.kicad_sch` пользователя. Facade-добавления
  (`PWR_FLAG`, `NoConnect`) — in-memory к netlist, не на диск; ERC
  не видит их и не должен. Логика: «дизайн считается валидным,
  если KiCad ERC доволен» — добавки facade — детали SPICE-export
  pipeline, не дизайна.
- **R9 ← Q6. ERC по working copy, staged игнорируется.** При
  наличии pending staged `.kicad_sch` (T026) — гоняем по applied
  working copy. Staged-state — детали T026 workflow, ERC оперирует
  «текущим состоянием на диске». Никаких warnings про pending staged.
- **R10 ← Q7. T187 — гибрид (script-detect + manual fix).** Acceptance
  T187: (a) написать утилиту-детектор off-grid pin/wire endpoints из
  `.kicad_sch` (read-only); (b) для каждого шаблона прогнать утилиту,
  получить список точек; (c) Vladimir вручную в KiCad GUI поправляет
  по списку. Не пишем грид-snap auto-fix — risk развалить connectivity.
  Обновлено в BACKLOG записи T187.
- **R11 ← Q8. Фазирование — 6 фаз.** Phase 0 (4 шаблона fix) → Phase 1
  (domain TDD) → Phase 2 (adapters integration tests) → Phase 3 (use
  case + design_to_sim integration + composition wiring) → Phase 4
  (CLI `efactory design check` + bridge `sim-run` integration) →
  Phase 5 (slash `/design-check` + KB sync T134 Уровень 1+2 + ADR) →
  Phase 6 (acceptance SC1-SC8, pre-push, BOARD Doing→Done, PR).
  Один коммит на ветке per phase, финальный squash перед merge.

### Post-Analyze amendments (Vladimir, 2026-06-04)

- **R12 ← C1. `sim-run --netlist` — skip ERC by design (вариант a).**
  ERC gate активен **только** в schematic-режиме (`design_to_sim`
  pipeline). Режим `efactory bridge sim-run --netlist <file>` остаётся
  без ERC: power-user shortcut, нет `.kicad_sch` для проверки. Agent
  при `/sim-run` всегда стартует со schematic — `--netlist`
  используется только в bridge-CLI вручную (debug). Фиксы в §3:
  - F13 уточняется: «ERC gate подключается в `design_to_sim`. В
    `sim_run` (готовый netlist) ERC **не** запускается.»
  - Новый F16: «`efactory bridge sim-run --netlist <file>` не вызывает
    ERC; в stdout — одна строка `ERC: skipped (pre-built netlist
    mode)` для visibility.»
- **R13 ← W1. Fallback для `project_root=None`.** При standalone
  single-file ERC без проектного root — отчёт пишется в
  `<schematic.parent>/out/erc/<UTC-ISO-ts>/report.md`. Уточнить
  в §3 F7 и §5 use case docstring.
- **R14 ← W2. CLI = slash контракт.** CLI `efactory design check`
  имеет идентичное `/design-check` поведение: auto-detect cwd при
  опущенном `<project>`, `--severity error|warning|all` (default
  `all`), exit-codes per R6, тот же markdown отчёт. §3 F11 расширить
  до симметрии с F12.
- **R15 ← W3. Parsing — JSON-only.** Adapter парсит **только**
  `--output <tmp.json>` файл. Stdout/stderr `kicad-cli sch erc`
  игнорируются полностью (только exit-code != 0 учитывается для
  differentiate с C1.b). Env-vars `LANG=C` (и `LC_ALL=C` для
  bullet-proof) выставляются перед subprocess, но это лишь best-
  effort на случай если KiCad залогирует что-то полезное в stderr —
  не предполагается, что мы это парсим.
- **R16 ← W4. Тестовая стратификация — hybrid.** Unit-тесты JSON-
  парсера на хардкод-фикстурах JSON (fast, always-run). Integration-
  тесты `KicadCliErcRunner` с реальным `kicad-cli` subprocess —
  маркер `pytest.mark.integration`, авто-skip если `which kicad-cli`
  пуст. Coverage threshold (≥80%) применяется к unit; integration —
  best-effort. Acceptance: на dev-машине Vladimir-а (KiCad apt) и в
  `efactory:linux` контейнере (T021) integration-тесты выполняются;
  на «чистом» CI без KiCad — пропускаются.
- **R17 ← W5. SchematicParseError vs ErcParseError.** Новый exception
  `SchematicParseError(stderr: str)` в `domain/erc.py` для случая
  «kicad-cli crashed на malformed schematic» (exit-code != 0, no
  JSON output / pure text on stderr). Отдельный от `ErcParseError`
  (malformed JSON, schema mismatch). Adapter различает по: (a) есть
  ли файл `--output` после subprocess, (b) parseable ли как JSON, (c)
  есть ли expected `$schema` ключ.

---

## Analyze (заполняется Claude после resolved-clarify)

Pass-1 (2026-06-04, после resolved Q1-Q8). 1 Critical / 5 Warning /
6 Note.

### 🔴 Critical

- **C1. `sim-run --netlist <file>` (без schematic) — ERC физически
  невозможен.** §3 F13 говорит «ERC gate в `design_to_sim`», но CLI
  `efactory bridge sim-run` имеет **два** режима: `sim_run` (готовый
  netlist) и `design_to_sim` (schematic → netlist → sim). На первом
  ERC невозможен — нет `.kicad_sch`. Нужно явное решение:
  - **(a)** `sim-run --netlist` остаётся без ERC gate (skip-by-design,
    pre-built netlist считается «у пользователя своя ответственность»).
    Acceptance: agent при `/sim-run` всегда использует schematic-режим;
    `--netlist`-режим — power-user / debug.
  - **(b)** `sim-run --netlist` ругается warning'ом «ERC не выполнен,
    т.к. нет schematic».
  - **(c)** `sim-run --netlist` блокируется ошибкой (требовать
    schematic).
  Рекомендую **(a)** — least intrusive, не ломает existing power-user
  flow. Фиксим в §3 как F13 (уточнить scope: ERC gate только в
  `design_to_sim` pipeline) + новый F16. **Требует ответа Vladimir-а
  перед Phase 3 (где интегрируется в `design_to_sim`).**

### 🟡 Warning

- **W1. `project_root` неопределён для standalone single-file ERC.**
  §5 use case принимает `project_root: Path | None`. Если пользователь
  зовёт `efactory design check /any/path/single.kicad_sch` без проекта
  (нет `.kicad_pro` рядом, нет cwd-проекта), куда писать отчёт?
  Предложение: fallback — `<schematic_parent>/out/erc/<ts>/report.md`
  (рядом со схемой). Уточнить в §3 F7 и §5 use case docstring.

- **W2. CLI vs slash inconsistency.** §3 F11/F12 описывают slash
  `/design-check` (`--severity`, auto-detect). CLI `efactory design
  check` должен иметь те же поведения, но §3 явно про CLI не говорит.
  Уточнить: CLI принимает `--severity error|warning|all`, авто-детект
  при опущенном `<project>` (как slash), exit-codes из R6.

- **W3. KiCad localization stderr unpredictable with `LANG=C`.** В
  probe (2026-06-04) первый запуск без `LANG=C` выдал stderr на
  русском (Qt-translation). Batch-probe с `LANG=C` запустил stdout
  в `/dev/null`, не верифицировал что Qt'шный translator подчинился
  `LANG`. Adapter должен парсить **только JSON-файл `--output`**,
  игнорировать stdout/stderr beyond exit-code. Возможно нужно
  `LC_ALL=C` или `QT_LANGUAGE=en` env-var — выясняется в Phase 2.

- **W4. Adapter integration tests требуют `kicad-cli` в PATH.** Если CI
  без KiCad → tests падают. Решения:
  - **(a)** Integration tests маркируются `pytest.mark.integration`,
    запускаются опционально (flag `--run-integration`), на CI без
    kicad-cli — пропускаются.
  - **(b)** Mock subprocess + fixture JSON-outputs (faster, но не
    тестирует реальный contract).
  - **(c)** Hybrid: unit-tests парсера на fixture JSONs (always-run),
    integration-tests с реальным subprocess (skip if no kicad-cli).
  Рекомендую **(c)**. Уточнить в Phase 2 acceptance.

- **W5. Malformed `.kicad_sch` vs ERC fail.** Если файл — не валидный
  KiCad-schematic, `kicad-cli` падает с exit-code !=0 без полезного
  JSON. Adapter должен **различать**:
  - kicad-cli crashed (no JSON output, exit != 0) → `ErcParseError`
    или новый `SchematicParseError` с stderr-message.
  - kicad-cli ok, ERC found errors (JSON есть, exit-code 5 с
    `--exit-code-violations` или 0 без флага) → `ErcReport` с
    error_count > 0.
  Уточнить в §3 F10 и §5 exceptions list.

### 🟢 Note

- **N1. Schema version drift.** Если KiCad bump'нет `$schema` →
  `erc.v2.json`, наш парсер должен fail c понятным сообщением «KiCad
  ERC schema version unsupported», а не silent corrupt. Phase 2: явная
  проверка `$schema.endswith('erc.v1.json')` или `erc.v1.X.json`.

- **N2. Timestamp granularity.** `<UTC-ISO-ts>` директория — формат
  `YYYY-MM-DDTHH-MM-SS` (двоеточие не подходит для Windows-fs).
  Concurrent runs в одной секунде — race. Использовать
  `YYYY-MM-DDTHH-MM-SS.ffffff` (microseconds) для безопасности.

- **N3. `out/erc/` cleanup policy.** Каждый run = новая директория.
  После 100 runs — 100 директорий. Policy: ничего не чистим автоматом,
  это решение пользователя. Можно потом сделать `efactory tidy`
  (отдельная задача).

- **N4. T026 staged-mod education для agent.** R9 говорит ERC по
  working copy. Agent должен в KB знать: если есть pending staged
  schematic → сначала `/schematic-apply`, только потом `/sim-run`,
  иначе ERC проверит «старое» состояние. Не блокер T029, добавим в
  KB topic `design.erc-quality-gate` как cross-ref на
  `schematic.staged-modifications`.

- **N5. PWR_FLAG в facade ≠ ERC fix.** §6 A1 говорит «facade.py уже
  ставит PWR_FLAG/NoConnect маркеры». Но R8 фиксирует: ERC видит
  файл **до** facade-добавлений. Значит facade-fixes — это про
  netlist-генерацию (ngspice happy), не про ERC happiness. 4 «грязных»
  шаблона имеют ERC errors **в исходном `.kicad_sch`**, не в-memory
  netlist. Phase 0 чинит именно `.kicad_sch` файлы шаблонов, не
  facade-логику. Записать как note в Phase 0 plan.

- **N6. `out/erc/` создание directory tree.** Markdown writer должен
  `mkdir(parents=True, exist_ok=True)` перед write. Стандартно, но
  явно укажем в `MarkdownErcReportWriter` docstring.

### Acceptance gate

Перед Phase 1 (start of implementation):
- **C1 требует ответа Vladimir-а** (выбор a/b/c).
- W1, W2, W5 — фиксы в spec на следующем pass.
- W3, W4 — закрываются эмпирически на Phase 2 (adapter implementation),
  не блокируют Phase 1 (domain TDD).
- N1-N6 — implementation-time notes, не блокируют start.
