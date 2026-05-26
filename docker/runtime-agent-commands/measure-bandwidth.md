---
description: Измерить полосу пропускания по `-N dB` от midband (AC sweep).
argument-hint: '[NETLIST] [--f-low Hz] [--f-high Hz] [--ref-db dB]'
allowed-tools: Bash
---

Пользователь хочет измерить полосу пропускания через `efactory bridge
measure bandwidth` на готовом SPICE-netlist'е.

Args от пользователя: `$ARGUMENTS` (все опционально; netlist —
позиционный или auto-detect; default `--f-low 1`, `--f-high 1Meg`,
`--ref-db -3`).

1. Определи `NETLIST`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`) —
     это путь к netlist'у.
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.cir' -not -path
     '*/.*'`.
     - Один match → используй.
     - Ноль / много — сообщение пользователю (по тому же паттерну, что
       `/measure-gain`).

2. Запусти: `efactory bridge measure bandwidth <NETLIST> [... флаги
   из $ARGUMENTS]`.

3. Default reference — `auto` (midband = max|H|). Если у пользователя
   bumpy АЧХ (гитарный усилитель и т.п.) — предложи передать
   `--midpoint-source ref_freq --ref-freq 1k` для классической
   audio-конвенции.

4. Покажи stdout (`f_low … f_high`, `bandwidth_hz`, `midpoint_db`).
   На ошибке — stderr.

5. После успеха упомяни запись в `.efactory/sim-results/
   <TS>-bandwidth.json`.
