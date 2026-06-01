---
description: Измерить phase margin замкнутой петли (loop-gain crossover через AC injection).
argument-hint: '[NETLIST] [--loop-break-node <node> --loop-break-element <ref>] [--injection-method ...] [--no-confirm]'
allowed-tools: Bash
---

Пользователь хочет измерить запас по фазе через `efactory bridge
measure phase-margin` на готовом SPICE-netlist'е с замкнутой петлёй
обратной связи.

Args от пользователя: `$ARGUMENTS` (всё опционально; netlist —
позиционный или auto-detect; по умолчанию — auto-detect break edge +
Middlebrook voltage injection).

1. Определи `NETLIST`:
   - Если `$ARGUMENTS` содержит позиционный аргумент (не флаг `--*`) —
     это путь к netlist'у.
   - Иначе — auto-detect: `find . -maxdepth 2 -name '*.cir' -not -path
     '*/.*'`.
     - Один match → используй.
     - Ноль — сообщи: «Не найдено `.cir` в `pwd` (top-level + 1).
       Сгенерируй netlist через `/sim-run` или `efactory bridge
       design-to-netlist <PROJECT> --schematic <path>.kicad_sch`, потом
       вернись.» и остановись.
     - Несколько — список + попроси выбрать.

2. **Loop break edge — два режима.**
   - Если пользователь явно указал `--loop-break-node <X>` И
     `--loop-break-element <Y>` (оба!) — передай как есть. Половинчатый
     вариант (только один из флагов) → exit 2; обязательно показывай
     это сообщение пользователю и подскажи передать оба.
   - Иначе — auto-detect (default). Передай `--no-confirm` в
     неинтерактивном контексте agent'а — иначе CLI будет ждать
     `typer.confirm`. По умолчанию `--confidence-threshold 0.8`; если
     auto-detect отклонит edge с низкой confidence (exit 2 +
     `AutoDetectRejectedError`) — предложи пользователю передать пару
     `--loop-break-node` + `--loop-break-element` явно.

3. **Injection method**. По умолчанию `middlebrook-voltage` (один AC
   sweep, fastest). Если ngspice вернул `NoUnityGainCrossover` или
   `LoopGainAlwaysAboveUnity` — это calibration issue Middlebrook V
   single-injection (`T_v ≠ T_loop` в общем случае; см. KB
   `agent.command-routing` Special case). Можно попробовать:
   - `--injection-method tian` (двойная voltage+current injection,
     symmetric Cadence Spectre default);
   - `--injection-method rosenstark-return-ratio` (open + short break,
     independent cross-check).

4. Запусти: `efactory bridge measure phase-margin <NETLIST> [... флаги
   из $ARGUMENTS]`. Если включён auto-detect и agent НЕ под TTY —
   обязательно добавь `--no-confirm`.

5. Покажи stdout. Text формат: `Phase margin: <deg>° @ <Hz> [<class>,
   method=<m>, node=<node>]` + опциональный `auto-detect:` блок.
   `<class>` — `high` (> 60°) / `adequate` (45-60°) / `marginal`
   (30-45°) / `risky` (≤ 30°). На non-zero rc — stderr.

6. **Out-of-scope reminder.** Tool НЕ предлагает компенсацию (это
   будущая T029/T032 advisor). Не подменяй closed-loop transient
   stability check'ом (step response) — это другая задача.
