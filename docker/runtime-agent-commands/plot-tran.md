---
description: График waveform (TRAN) — ASCII в чате + PNG в окне через eog.
argument-hint: '[NETLIST] --t-step <step> --t-stop <stop> [--signal v(...)]'
allowed-tools: Bash
---

Пользователь хочет визуализировать waveform через `efactory bridge
plot tran`. T025: ASCII + PNG dual-mode.

Args от пользователя: `$ARGUMENTS` (минимум `--t-step` и `--t-stop`;
netlist — позиционный или auto-detect; default `--signal v(load)
--width 80 --height 20`).

1. Определи `NETLIST` (тот же auto-detect pattern, что `/plot-ac`).

2. Запусти: `efactory bridge plot tran <NETLIST> --t-step <step>
   --t-stop <stop> --output /tmp/plot-tran-$$.png [... остальные флаги]`.

   **Всегда передавай `--output <abs path>`** — это даёт PNG для
   T025 auto-show в eog. Префикс `/tmp/plot-tran-$$.png` (PID-suffix)
   уникален для каждого вызова; если хочешь persist'нуть в проекте —
   `/workspace/<proj>/.efactory/plots/tran-<TS>.png`.

3. Покажи stdout пользователю (ASCII-график + строка
   `plot-render: <abs path>`). На ошибке — stderr.

4. **T025 graphical auto-show.** Распарси из stdout строку
   `plot-render: <abs path>` и запусти **`eog <abs path> &`** через
   Bash — окно с PNG откроется на host через X11 forwarding.
   **Не пиши** ad-hoc Python / matplotlib скрипт, **не вызывай**
   `xdg-open` — `bridge plot tran --output` + `eog` уже даёт
   graphical вывод.

5. Типичные параметры:
   - Для аудио на 1 кГц: `--t-step 1u --t-stop 5m` (5 циклов, 5000
     samples — достаточная резолюция).
   - Для power supply ripple на 50 Гц: `--t-step 100u --t-stop 100m`.
   - Если waveform не стабилизировался — увеличь `--t-stop` (большее
     settle).
