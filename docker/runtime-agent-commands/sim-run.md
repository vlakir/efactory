---
description: Запустить SPICE-симуляцию (auto-detect schematic если не указан).
argument-hint: '[SCHEMATIC] [--analysis op|tran|ac]'
allowed-tools: Bash
---

Пользователь хочет запустить SPICE-симуляцию через `efactory bridge
sim-run` для текущего проекта (cwd).

Args от пользователя: `$ARGUMENTS` (может быть пусто, либо путь к
`.kicad_sch`, либо `--analysis TYPE`, либо сочетание).

1. Определи `SCHEMATIC`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`) —
     это путь к схеме.
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.kicad_sch' -not
     -path '*/.*'` (top-level + 1 subdir, исключая dot-каталоги вроде
     `.efactory/`, `.git/`).
     - Ровно один match → используй его.
     - Ноль — напечатай: «Не найдено `.kicad_sch` в `pwd` (top-level
       + 1). Передай путь явно: `/sim-run path/to/schematic.kicad_sch`.»
       и остановись.
     - Два или больше — напечатай список найденных файлов и попроси
       выбрать.

2. Запусти: `efactory bridge sim-run --schematic <SCHEMATIC>
   [--analysis TYPE если передан в $ARGUMENTS]`.

3. Покажи stdout (op-point / измерения / duration). На ошибке —
   stderr.

4. Если sim успешен, упомяни что результат записан в
   `.efactory/sim-results/<TS>-<analysis>.json` (если writer
   настроен — следующая сессия увидит запись через SessionStart hook).

5. **T025 auto-show схемы.** Просканируй stdout на строки вида
   `schematic-render: <abs path to PNG>` (по одной на лист схемы).
   Для каждой такой строки выполни **обе** операции в этом порядке:
   - **`chafa <abs path>`** через Bash — печатает ANSI-block
     render в terminal, пользователь видит силуэт схемы прямо в
     чате. Размер chafa определяет по `$COLUMNS`/`$LINES` автоматом;
     если terminal очень широкий и render узковат — можно явно
     задать `--size=200x` (200 col wide, высота по aspect ratio).
   - **`Read <abs path>`** — multimodal LLM «видит» PNG, ты можешь
     описать топологию своими словами (gain stage / feedback /
     loading) перед обсуждением sim-результатов.

   Если в stderr вместо этого `Warning: schematic render failed: ...` —
   упомяни warning одной строкой и продолжай с sim-результатами
   (render fail-soft не блокирует симуляцию).
