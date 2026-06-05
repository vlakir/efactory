---
topic: design.grid-check
description: Off-grid endpoint diagnostic в efactory (T187) — что это, exit-codes, когда применять
tags: [design, grid, kicad, off-grid, diagnostic]
---

# Off-grid endpoint diagnostic (T187)

`efactory design check-grid` (slash `/grid-check`) — **read-only**
диагностика: ищет в `.kicad_sch` pins / wire endpoints, не лежащие
на KiCad connection grid (1.27 mm = 50 mil), и пишет markdown-отчёт
с локализацией (kind, pos, nearest grid, Δ, uuid).

**Не gate.** Не блокирует `/sim-run` / `design_to_sim`. Netlist
генерируется по uuid'ам, а не координатам, поэтому SPICE работает
независимо от grid alignment.

## Зачем off-grid это проблема

- **Визуально:** «компонент чуть-чуть не довинчен» в KiCad GUI —
  пиксельный glitch на изоляции pin-to-wire (KiCad рисует connection
  dot только при exact геометрическом совпадении).
- **Ручная правка опасна:** при drag компонента в GUI snap-to-grid
  активен только если компонент уже на grid; иначе snap «прыгает» к
  ближайшей grid точке и **разрывает connectivity** (см. BACKLOG
  T187 rationale: разные элементы прыгают в разные стороны).

## Origin off-grid endpoint'ов

1. **Builder без snap-on-write** (исторически): builder писал raw
   координаты вроде `at=(80.5, 100.0)` — 80.5/1.27 = 63.39 off-grid.
   T187 fix: `_to_position` в `Schematic` facade теперь snap'ит к
   1.27 mm grid. Built-in templates ship'ятся on-grid.
2. **Hand-edit в KiCad GUI** на схеме с custom drawing grid.
   Пользователь поставил компонент visually красиво, но не на
   connection grid.
3. **Импорт legacy .kicad_sch** (KiCad 8 → 10 migration, custom
   library symbols с off-grid pins).

## Exit-code контракт (F10)

| Code | Значение | Что делать |
|---|---|---|
| `0` | Clean: 0 off-grid endpoints | Никаких действий. |
| `1` | Найдено N off-grid endpoints | Markdown в `out/grid-check/<ts>/report.md`. Не блокер для `/sim-run`. Для исправления — открыть KiCad GUI, drag-snap-to-grid каждый item из отчёта (sorted by |Δ| descending — большие drift'ы сверху). |
| `2` | Infrastructure (kicad-cli не в PATH, malformed schematic, timeout) | Не off-grid; проверь окружение. |

## Когда применять

- **После hand-edit в KiCad GUI** — sanity check, что drag'ом не съехал
  компонент с grid (особенно при custom drawing-grid настройках).
- **При импорте legacy `.kicad_sch`** — что KiCad 8 → 10 migration не
  оставила off-grid артефактов.
- **CI / pre-push (потенциально)** — protect against regression. Не в
  scope T187 ship; следующий milestone candidate.

## Когда НЕ применять

- На built-in templates (`data/templates/*/`) — T187 sealed их
  on-grid через snap-on-write + Phase 4 builder regeneration. Запуск
  всё равно даст 0 endpoints, но это noise.
- Перед `/sim-run` как «пред-проверка» — для этого есть `/design-check`
  (ERC quality gate). Off-grid не блокирует sim.

## Подробно: layered snap fix (T187)

efactory защищается от off-grid в **двух слоях**:

### Layer 1 — preventive (snap-on-write в facade)

`adapters/outbound/schematic_kicad/facade.py` — все `Schematic.add_*`
/ `connect` / `label` / `junction` / `no_connect` / `spice_directive`
silently snap координаты к 1.27 mm grid через
`domain.grid.snap_to_grid`. Builder'ам не нужно знать об этом —
random off-grid координаты автоматически приводятся к grid.

При `EFACTORY_STRICT_GRID=1` env-var silent snap заменяется на
`OffGridPositionError` с диагностикой (component name, requested vs
snapped, Δ). Полезно при разработке новых builders для catch-it-
early.

### Layer 2 — diagnostic (этот CLI)

`efactory design check-grid` сканирует существующий `.kicad_sch` (не
важно как создан) и показывает off-grid endpoints. Read-only —
никогда не модифицирует файл.

## Связь с `design.erc-quality-gate`

`design check-grid` использует **тот же** `KicadCliErcRunner` что и
T029 ERC quality gate — фильтрует violations по `type ==
"endpoint_off_grid"`, маппит в `OffGridReport`. Separation of concerns
по Plan B (one tool one job): ERC gate hard-blocks at design-time;
grid check — диагностика для visual cleanup.

## См. также

- `design.erc-quality-gate` — T029 ERC quality gate (parent topic).
- `schematic.staged-modifications` — T026 staged-mod workflow (grid
  check работает с applied working copy, не staged-диффом).
