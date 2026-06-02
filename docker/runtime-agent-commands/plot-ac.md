---
description: График АЧХ (AC sweep) — ASCII в чате + PNG в окне через eog.
argument-hint: '[NETLIST] [--signal v(...)] [--f-start Hz --f-stop Hz]'
allowed-tools: Bash
---

Пользователь хочет визуализировать АЧХ схемы через `efactory bridge
plot ac`. T025: ASCII + PNG dual-mode.

Args от пользователя: `$ARGUMENTS` (всё опционально; netlist —
позиционный или auto-detect; default `--f-start 1 --f-stop 1Meg
--n-points 10 --signal v(load) --width 80 --height 20`).

1. Определи `NETLIST`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`) —
     это путь к netlist'у.
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.cir' -not -path
     '*/.*'`. Один match → используй; ноль / много → сообщи пользователю.

2. Запусти: `efactory bridge plot ac <NETLIST> --output
   /tmp/plot-ac-$$.png [... флаги из $ARGUMENTS]`.

   **Всегда передавай `--output <abs path>`** — это даёт PNG для
   T025 auto-show в eog. Префикс `/tmp/plot-ac-$$.png` (PID-suffix)
   уникален для каждого вызова; если хочешь persist'нуть в проекте —
   `/workspace/<proj>/.efactory/plots/ac-<TS>.png`.

3. Покажи stdout пользователю (ASCII-график + строка
   `plot-render: <abs path>`). На ошибке — stderr.

4. **T025 graphical auto-show.** Распарси из stdout строку
   `plot-render: <abs path>` и запусти **`eog <abs path> &`** через
   Bash — окно с PNG откроется на host через X11 forwarding.
   **Не пиши** ad-hoc Python / matplotlib скрипт, **не вызывай**
   `xdg-open` — `bridge plot ac --output` + `eog` уже даёт
   graphical вывод.

5. График интерпретируется так: x — частота (логарифмическая шкала),
   y — магнитуда в dB. По форме можно определить полосу пропускания
   (-3 dB от midband), low-side и high-side roll-off, резонансы.
