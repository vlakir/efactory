---
description: ASCII-график waveform (signal vs time) через TRAN.
argument-hint: '[NETLIST] --t-step <step> --t-stop <stop> [--signal v(...)]'
allowed-tools: Bash
---

Пользователь хочет визуализировать waveform через `efactory bridge
plot tran` — ASCII-график через plotext.

Args от пользователя: `$ARGUMENTS` (минимум `--t-step` и `--t-stop`;
netlist — позиционный или auto-detect; default `--signal v(load)
--width 80 --height 20`).

1. Определи `NETLIST` (тот же auto-detect pattern, что `/plot-ac`).

2. Запусти: `efactory bridge plot tran <NETLIST> --t-step <step>
   --t-stop <stop> [... остальные флаги]`.

3. Покажи stdout (ASCII-график). На ошибке — stderr.

4. Типичные параметры:
   - Для аудио на 1 кГц: `--t-step 1u --t-stop 5m` (5 циклов, 5000
     samples — достаточная резолюция).
   - Для power supply ripple на 50 Гц: `--t-step 100u --t-stop 100m`.
   - Если waveform не стабилизировался — увеличь `--t-stop` (большее
     settle).
