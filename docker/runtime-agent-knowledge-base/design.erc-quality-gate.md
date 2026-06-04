---
topic: design.erc-quality-gate
description: ERC quality gate в efactory pipeline — поведение, exit-codes, типичные fix-ы (T029)
tags: [design, erc, kicad, simulation, quality-gate]
---
# ERC quality gate (T029)

`efactory` подключает `kicad-cli sch erc` как **hard-блокер** перед
SPICE-симуляцией: схема с ERC errors не доходит до ngspice. Это
лечит главный класс пользовательских жалоб — «sim молча запустился
на сломанной схеме → debug чёрным ящиком». Warnings проходят, но
рендерятся в markdown-отчёт.

## Где gate активен

- **`/sim-run` → `efactory bridge sim-run --schematic ...`** —
  `design_to_sim` pipeline. ERC запускается ДО `design_to_netlist`,
  на реальном `.kicad_sch` пользователя (не на in-memory netlist с
  facade-добавками).
- **`/design-check` → `efactory design check ...`** — standalone
  ERC-check без вызова ngspice. Полезно после ручного редактирования
  в KiCad GUI до коммита.
- **`efactory bridge sim-run --netlist <file>`** (без schematic) —
  ERC physically невозможен, gate skipped by design. В stdout видна
  строка `ERC: skipped (pre-built netlist mode)` (R12).

## Exit-code контракт (R6)

| Code | Значение | Что делать |
|---|---|---|
| `0` | ERC ok (errors=0) | продолжай работу |
| `1` | ERC errors > 0 | прочитай `out/erc/<ts>/report.md`, чини схему |
| `2` | infrastructure (`kicad-cli` отсутствует / malformed `.kicad_sch` / timeout) | не ERC issue — проверь окружение |

`ERC infrastructure failure: ...` в stderr → exit 2.
`ERC errors: N (...)` в stderr → exit 1.

## Markdown отчёт

Лежит в `<project_root>/out/erc/<UTC-ISO-ts>/report.md` (microsecond
timestamp, чтоб concurrent runs не сталкивались). Структура: header
(schematic, timestamp, KiCad version, summary counts), `## Violations`
секция (table per type), `## Ignored Checks` (exclusions из
`.kicad_pro` если есть).

Каждый item в violations имеет `symbol description`, `pos (mm)`,
`uuid` — достаточно для локализации в KiCad GUI (Edit → Find by UUID).

## Самые частые violations

| Type | Что значит | Fix |
|---|---|---|
| `power_pin_not_driven` | net не имеет PWR_FLAG-источника (KiCad считает power input pin без drive'а) | поставь `power:PWR_FLAG` на ту же net'у (т.е. на GND или Vcc rail) |
| `pin_not_connected` | symbol pin не присоединён wire'ом | либо подсоедини pin, либо поставь `no_connect` symbol |
| `endpoint_off_grid` | конец wire/pin не на 1.27mm сетке | wire snap или edit-by-pixel в KiCad GUI (warning, не блокирует) |
| `single_global_label` | global label встречается в схеме только раз | если так задумано — добавь exclusion в `.kicad_pro`; иначе исправь typo |
| `simulation_model_issue` | проблема с SPICE Sim.Library / Sim.Pins | проверь `Sim.*` свойства symbol'а |

## Dev-pipeline: builders, не прямые правки

В efactory `data/templates/*` — build artifact `scripts/regenerate-
templates.py`, который зовёт `_build_<name>` функции из
`tests/integration/adapters/schematic_kicad/test_<name>_facade.py`.
**Не редактируй `.kicad_sch` в templates напрямую** — следующий
regen стирает правки. Все ERC-фиксы шаблонов (PWR_FLAG, reconnect,
NoConnect) делаются в builder'ах + `regenerate-templates.py
--template <name>`.

## Что НЕ делает T029

- Авто-фикс ERC violations (нет «починить нарушения» режима).
- DRC (Design Rule Check) на `.kicad_pcb` — это PCB-фаза, отдельная
  задача.
- Custom ERC rules — пользователь настраивает в KiCad GUI на
  `.kicad_pro`, мы honor'им.
- Escape hatch (`--no-erc` / env-флаг для skip'а) — запрещено по
  R6. Сломали схему → чините схему.
- ERC на staged-modifications (T026) — мы гоняем по applied working
  copy. Если есть pending staged `.kicad_sch.staged` → сначала
  `/schematic-apply`, потом `/sim-run` или `/design-check`.

См. также: KB `schematic.staged-modifications` (workflow staged →
applied), `agent.command-routing` (routing для `/design-check`).
