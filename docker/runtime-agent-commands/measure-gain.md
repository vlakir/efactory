---
description: Измерить gain в точке частоты (small AC или large TRAN RMS).
argument-hint: '[NETLIST] --freq <Hz> [--mode small|large] [--v-in-peak V]'
allowed-tools: Bash
---

Пользователь хочет измерить gain через `efactory bridge measure gain`
на готовом SPICE-netlist'е.

Args от пользователя: `$ARGUMENTS` (минимум `--freq`; netlist —
позиционный аргумент или auto-detect).

1. Определи `NETLIST`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`) —
     это путь к netlist'у.
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.cir' -not -path
     '*/.*'` (top-level + 1 subdir, исключая dot-каталоги).
     - Ровно один match → используй его.
     - Ноль — напечатай: «Не найдено `.cir` в `pwd` (top-level + 1).
       Сгенерируй netlist через `/sim-run` или `efactory bridge
       design-to-netlist <PROJECT> --schematic <path>.kicad_sch`, потом
       вернись.» и остановись.
     - Два или больше — список + попроси выбрать.

2. Запусти: `efactory bridge measure gain <NETLIST> --freq <Hz> [...
   остальные флаги из $ARGUMENTS]`.

3. Default `--mode small` (быстро, AC analysis). Если пользователь
   просит реальную крупно-сигнальную проверку — передай `--mode large
   --v-in-peak <V>` и обязательно `--input-signal v(<input_node>)`.

4. Покажи stdout. На non-zero rc — stderr.

5. После успешного измерения упомяни: результат записан в
   `.efactory/sim-results/<TS>-gain.json` (если writer настроен).
