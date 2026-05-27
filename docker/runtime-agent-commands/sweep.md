---
description: Параметрический sweep по 1-2 component values с tabular output + опциональный ASCII plot.
argument-hint: '<PROJECT> --schematic <abs.kicad_sch> --param REF=v1,v2,... [--metric op|gain|bandwidth|thd] [--freq Hz] [--output text|csv|json] [--output-file PATH] [--plot]'
allowed-tools: Bash
---

Пользователь хочет параметрический sweep — посмотреть как
SimulationResult / measure_* метрики меняются при варьировании
1-2 component values.

Args от пользователя: `$ARGUMENTS` (project + flags). Используй
**абсолютные пути** для `--schematic` (cwd-instability T014 A2).

1. Определи `PROJECT` (первый позиционный) и `--schematic`
   (абсолютный путь, обязательный). Если schematic не передан —
   попроси пользователя указать.

2. Определи **metric**:
   - **op** (default) — operating points (DC bias), нужен для
     «как меняется bias при варьировании Rk / B+ / Rg».
   - **gain** — small-signal AC gain в точке `--freq <Hz>` (mode
     small) или large-signal TRAN RMS gain (mode large + `--v-in-peak`).
   - **bandwidth** — `(f_low, f_high, bw)` по `--f-low/--f-high`
     (default 1, 1Meg). Auto-detect midband по max |H|.
   - **thd** — THD% в точке `--freq` + `--v-in-peak`.

3. Запусти: `efactory bridge sweep <PROJECT> --schematic <abs> --param
   REF=v1,v2,... [--metric M --analysis A --freq F ...] [--output
   O --output-file P] [--plot --plot-y Y --plot-x-scale auto|linear|log]`.

4. Покажи stdout (tabular для default, JSON / 1-line summary для
   `--output json` / `--output-file`).

## Pitfalls

- **N > 100 без `--max-combinations` → exit 2** (hard cap). Override
  через `--max-combinations 200`. Soft warn N>20 — продолжает.
- **`--metric op` совместима только с `--analysis op`** (default).
  Любая другая `(metric, analysis)` пара → exit 2 «incompatible».
  Совместимые: (gain+small, ac), (gain+large, tran), (bandwidth, ac),
  (thd, tran). Без `--analysis` — auto-mapping.
- **`--metric gain --mode large` требует `--input-signal v(...)`**
  явно (measure_gain не auto-detect'ит trace name для RMS-вычисления).
- **Multi-V netlist** (e.g. SE amp с B+ и input source): без
  `--input-source <REF>` measure_* auto-detect упадёт с ambiguity.
  Для se-amp-demo: `--input-source V2` (input — V2, B+ — V1).
- **`--plot` для `--metric=op`** требует `--plot-y v(<node>)` явно
  (raw OP не имеет default Y); для metric — auto `gain_db /
  bandwidth_hz / thd_percent`.
- **>2 параметров** → plot disabled (warning в stderr), таблица
  выводится. Сводки 2-param через multi-line (одна линия на значение
  2-го param).
- **`--output csv --output-file <path>`** записывает CSV в файл,
  stdout — 1-line summary `Sweep complete: N rows → <path>`.

## Когда выбирать sweep

- **«Как меняется bias при Rk = ...»** → `--metric op --param Rk=...`.
- **«Зависимость gain от Rk / Rg»** → `--metric gain --freq 1k --param ...`.
- **«Bandwidth vs Cin»** → `--metric bandwidth --param Cin=10n,100n,1u --plot`.
- **«THD vs нагрузки»** → `--metric thd --freq 1k --v-in-peak 0.1 --param R_load=...`.
- **2D-map gain(Rk, Cin)** → `--metric gain --param Rk=... --param Cin=... --plot`
  (2 параметра → multi-line plot, одна линия на Cin).
