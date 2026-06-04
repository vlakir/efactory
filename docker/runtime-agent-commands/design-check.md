---
description: ERC проверка schematic'а через kicad-cli (без SPICE-симуляции).
argument-hint: '[SCHEMATIC|PROJECT_DIR] [--severity error|warning|all]'
allowed-tools: Bash
---

Пользователь хочет проверить `.kicad_sch` на ERC violations через
`efactory design check` (T029) — standalone-gate без вызова ngspice.

Args от пользователя: `$ARGUMENTS` (может быть пусто, либо путь к
`.kicad_sch`, либо путь к директории проекта, либо `--severity TYPE`,
либо сочетание).

1. Определи `TARGET`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`):
     - оканчивается на `.kicad_sch` → путь к схеме;
     - иначе считаем директорией проекта (CLI сам найдёт `.kicad_sch`).
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.kicad_sch' -not
     -path '*/.*'` (top-level + 1 subdir, исключая dot-каталоги вроде
     `.efactory/`, `.git/`).
     - Ровно один match → используй его.
     - Ноль — напечатай: «Не найдено `.kicad_sch` в `pwd` (top-level
       + 1). Передай путь явно: `/design-check path/to/schematic.kicad_sch`.»
       и остановись.
     - Два или больше — напечатай список найденных файлов и попроси
       выбрать.

2. Запусти: `efactory design check <TARGET> [--severity TYPE если
   передан в $ARGUMENTS]`.

3. Покажи stdout полностью (summary-строка `ERC: N errors, M warnings
   → out/erc/<ts>/report.md`). На ошибке — stderr.

4. **Exit-code семантика (T029 R6):**
   - `0` → ERC чист (errors == 0). Markdown-отчёт записан рядом со
     схемой (`<project_root>/out/erc/<ts>/report.md`).
   - `1` → ERC errors > 0. Симуляция блокирована, пользователь
     должен починить схему. Markdown-отчёт содержит локализацию
     каждого нарушения (symbol, pos, uuid). Предложи пользователю:
     открыть `.kicad_sch` в KiCad GUI, прочитать report.md, исправить.
   - `2` → инфраструктурная ошибка (`kicad-cli` отсутствует,
     malformed `.kicad_sch`, timeout). Это не ERC issue —
     проверь, что KiCad установлен / что schematic не корявый.

5. **Когда использовать `/design-check` vs `/sim-run`:**
   - `/design-check` — проверка целостности дизайна без расходов на
     ngspice (~3-5 секунд). Полезно после ручного редактирования
     `.kicad_sch` в KiCad GUI до коммита.
   - `/sim-run` — `design_to_sim` pipeline, который **уже** включает
     ERC gate перед netlist export. Если хочешь сразу симуляцию —
     `/sim-run` сам поймает ERC errors и не запустит ngspice.

См. KB topic `design.erc-quality-gate` (когда и зачем ERC; список
типов violations; типичные fix-ы).
