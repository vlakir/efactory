---
description: Применить edits к схеме и сравнить выбранные метрики до/после (delta).
argument-hint: '<PROJECT> --schematic <abs.kicad_sch> --set REF=VALUE [...] --measure gain|bandwidth|thd|phase-margin [...] [--freq Hz] [--v-in-peak V] [--f-low Hz] [--f-high Hz] [--mode small|large] [--loop-break-node N] [--loop-break-element REF] [--injection-method METHOD] [--output text|json] [--output-file PATH]'
allowed-tools: Bash
---

Пользователь хочет «what-if» эксперимент: изменить один-несколько
компонентов в schematic и сразу увидеть, как это сказалось на ключевых
метриках (gain / bandwidth / thd / phase-margin) — без ручного цикла
measure → edit → measure → diff.

Args от пользователя: `$ARGUMENTS` (project + flags). Используй
**абсолютные пути** для `--schematic` (cwd-instability T014 A2).

1. Определи `PROJECT` (первый позиционный) и `--schematic`
   (абсолютный путь, обязательный). Если schematic не передан —
   попроси пользователя указать.

2. Определи **edits**: один или несколько `--set REF=VALUE`
   (повторяемый). Минимум один; обычно 1–5 на one-shot эксперимент.
   Больше 10 — soft warn в stderr (continue).

3. Определи **метрики**: один или несколько `--measure {gain,
   bandwidth, thd, phase-margin}` (повторяемый). Дубликаты silently
   дедуплицируются.

4. Передай те же measure-флаги, что и в одноимённых `bridge measure`
   командах — `--freq`, `--v-in-peak`, `--f-low`/`--f-high`,
   `--mode`, `--output-signal`, `--input-signal`, `--input-source`.
   Команда применяет их ко всем метрикам, которым они нужны
   (gain/thd берут `--freq`; gain-large/thd берут `--v-in-peak`;
   bandwidth и phase-margin берут `--f-low/--f-high`).

   Для `phase-margin` дополнительно:
   - `--loop-break-node <NET>` + `--loop-break-element <REF>` —
     edge-pair, в котором режется петля. Обе опции вместе ИЛИ ни
     одной (auto-detect через graph analyzer).
   - `--injection-method {middlebrook-voltage,middlebrook-current,tian,
     rosenstark-return-ratio}` — метод инжекции (default
     middlebrook-voltage).
   - `--confidence-threshold 0..1` (default 0.8) — порог auto-detect.
   - `--no-confirm` — не спрашивать подтверждение в TTY.
   - `--pm-n-points-per-decade N` (default 100) — разрешение AC sweep.

5. Запусти: `efactory bridge edit-and-resim <PROJECT> --schematic
   <abs> --set REF=V [...] --measure M [...] [...]`.

6. Покажи stdout: aligned table «Metric / Field / Before / After /
   Δ / Δ%» (text) или structured JSON (`--output json`). Failed-
   метрика помечается `FAILED` + sub-row с причиной.

## Pitfalls

- **`--measure gain` требует `--freq`** (явно). Без частоты —
  EditAndResimConfig validation падает exit 2.
- **`--measure thd` требует `--freq` И `--v-in-peak`** (caller знает
  нужную мощность входа).
- **`--measure gain --mode large`** дополнительно требует
  `--v-in-peak` и `--input-signal v(...)` (RMS-computation).
- **Multi-V netlist** (e.g. SE amp с B+ и input source): без
  `--input-source <REF>` measure_* auto-detect упадёт с ambiguity.
- **`--measure phase-margin`** требует либо пары `--loop-break-node
  + --loop-break-element` (explicit edge, ADR-T153d), либо auto-detect
  через graph analyzer (без обоих опций). Half-explicit (только одна
  из двух) → exit 2.
- **`--measure phase-margin` в non-TTY без `--no-confirm`**: callback
  возвращает True при confidence ≥ threshold (стандартное поведение
  для batch-режима). В TTY будет prompt.
- **Baseline failure → exit 1, schematic не тронут** (strict policy:
  если baseline-измерение упало, edit'ы не применяются — нечего
  сравнивать). Сообщение: `baseline <metric> measurement failed: ...
  Edits NOT applied; schematic unchanged.`
- **Edit failure → exit 1 + SchematicSnapshot rollback** (исходный
  `.kicad_sch` восстановлен).
- **After-measure failure → schematic уже изменён**, but the
  per-metric `failed_reason` будет в результате; exit 1. Если хочется
  откатить — `bridge edit <PROJECT> --set REF=<old>` вручную.
- **`--output json`** содержит полные before/after VO-объекты +
  delta_absolute + delta_relative_percent + failed_reason +
  edits + project — fundament для программной обработки.

## Когда выбирать edit-and-resim

- **«Если поменять Rk на 1.5k, как изменится THD?»** →
  `--set Rk=1.5k --measure thd --freq 1k --v-in-peak 0.1`.
- **«Эффект замены OPT на OPT_3K5 — gain и bandwidth»** →
  `--set X1=OPT_SE_3K5_8 --measure gain --measure bandwidth
  --freq 1k --f-low 20 --f-high 20k`.
- **«Подкорректировал R5 и C3 одновременно — как полоса?»** →
  `--set R5=2k --set C3=470n --measure bandwidth`.
- **«Если уменьшу R_fb до 47k, как изменится запас по фазе?»** →
  `--set R_fb=47k --measure phase-margin --loop-break-node in_neg
  --loop-break-element R_fb --f-low 1 --f-high 1Meg`.
- **«До и после: gain + phase-margin одной командой»** →
  `--set R5=2k --measure gain --measure phase-margin --freq 1k
  --loop-break-node in_neg --loop-break-element R_fb`.

## Когда НЕ выбирать

- Sweep по диапазону значений (хочу узнать оптимум) → `/sweep` (T022).
- Просто измерение без правок → `/measure-gain` / `/measure-bandwidth`
  / `/measure-thd`.
- Просто правка без измерения → `/edit` (T004b).
