---
description: ASCII-график АЧХ (магнитуда vs log-частота) через AC sweep.
argument-hint: '[NETLIST] [--signal v(...)] [--f-start Hz --f-stop Hz]'
allowed-tools: Bash
---

Пользователь хочет визуализировать АЧХ схемы через `efactory bridge
plot ac` — ASCII-график через plotext.

Args от пользователя: `$ARGUMENTS` (всё опционально; netlist —
позиционный или auto-detect; default `--f-start 1 --f-stop 1Meg
--n-points 10 --signal v(load) --width 80 --height 20`).

1. Определи `NETLIST`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`) —
     это путь к netlist'у.
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.cir' -not -path
     '*/.*'`. Один match → используй; ноль / много → сообщи пользователю.

2. Запусти: `efactory bridge plot ac <NETLIST> [... флаги из $ARGUMENTS]`.

3. Покажи stdout (ASCII-график). На ошибке — stderr.

4. График интерпретируется так: x — частота (логарифмическая шкала),
   y — магнитуда в dB. По форме можно определить полосу пропускания
   (-3 dB от midband), low-side и high-side roll-off, резонансы.
