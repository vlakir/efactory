---
description: Off-grid endpoint diagnostic для .kicad_sch (KiCad connection grid 1.27 mm).
argument-hint: '[SCHEMATIC|PROJECT_DIR]'
allowed-tools: Bash
---

Пользователь хочет проверить `.kicad_sch` на off-grid endpoints
(`endpoint_off_grid` warning, KiCad-cli ERC) через `efactory design
check-grid` (T187) — read-only диагностика, не gate, не блокирует
симуляцию.

Args от пользователя: `$ARGUMENTS` (может быть пусто, либо путь к
`.kicad_sch`, либо путь к директории проекта).

1. Определи `TARGET`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`):
     - оканчивается на `.kicad_sch` → путь к схеме;
     - иначе считаем директорией проекта (CLI сам найдёт `.kicad_sch`).
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.kicad_sch' -not
     -path '*/.*'` (top-level + 1 subdir, исключая dot-каталоги).
     - Ровно один match → используй его.
     - Ноль — напечатай: «Не найдено `.kicad_sch` в `pwd` (top-level
       + 1). Передай путь явно: `/grid-check path/to/schematic.kicad_sch`.»
       и остановись.
     - Два или больше — напечатай список найденных файлов и попроси
       выбрать.

2. Запусти: `efactory design check-grid <TARGET>`.

3. Покажи stdout полностью.

4. **Exit-code семантика (T187 F10):**
   - `0` → grid-check clean: 0 off-grid endpoints. `.kicad_sch`
     полностью на 1.27 mm connection grid. Никаких действий.
   - `1` → есть off-grid endpoints. Markdown-отчёт записан в
     `<project_root>/out/grid-check/<ts>/report.md` с локализацией
     каждой точки (kind, description, pos, nearest grid, Δ, uuid).
     Endpoints отсортированы по |Δ| убывая — top entries сначала.
     **Это не блокирует симуляцию** — netlist генерится по uuid'ам,
     SPICE работает. Off-grid — визуально-косметическая проблема в
     KiCad GUI («компонент чуть-чуть не довинчен», любая ручная
     правка имеет шанс развалить connectivity). Предложи
     пользователю: открыть `.kicad_sch` в KiCad GUI, прочитать
     report.md, drag-snap-to-grid каждый endpoint по списку.
   - `2` → инфраструктурная ошибка (`kicad-cli` отсутствует, malformed
     `.kicad_sch`, timeout). Не off-grid issue — проверь окружение.

5. **Когда использовать `/grid-check` vs `/design-check`:**
   - `/design-check` — ERC quality gate (T029): hard-блокировка
     симуляции при errors (unconnected pins, unrouted nets), warnings
     visible. Используется до `/sim-run` для fail-fast.
   - `/grid-check` — narrow off-grid diagnostic (T187). Не блокирует
     ничего; для пользовательских / hand-edited schematics, где
     compositors могли сместить компоненты с grid. Built-in templates
     ship'ятся on-grid (T187 snap-fix + builder enforcement).

См. KB topic `design.grid-check` (anatomy off-grid issue; почему snap
не auto-apply; built-in templates vs user schematics; relation to
`design.erc-quality-gate`).
