---
description: Применить edits к схеме и сравнить выбранные метрики до/после (delta).
argument-hint: '<PROJECT> --schematic <abs.kicad_sch> --set REF=VALUE [...] --measure gain|bandwidth|thd [...] [--freq Hz] [--v-in-peak V] [--f-low Hz] [--f-high Hz] [--mode small|large] [--output text|json] [--output-file PATH]'
allowed-tools: Bash
---

Пользователь хочет «what-if» эксперимент: изменить один-несколько
компонентов в schematic и сразу увидеть, как это сказалось на ключевых
метриках (gain / bandwidth / thd) — без ручного цикла measure → edit
→ measure → diff.

Args от пользователя: `$ARGUMENTS` (project + flags). Используй
**абсолютные пути** для `--schematic` (cwd-instability T014 A2).

1. Определи `PROJECT` (первый позиционный) и `--schematic`
   (абсолютный путь, обязательный). Если schematic не передан —
   попроси пользователя указать.

2. Определи **edits**: один или несколько `--set REF=VALUE`
   (повторяемый). Минимум один; обычно 1–5 на one-shot эксперимент.
   Больше 10 — soft warn в stderr (continue).

3. Определи **метрики**: один или несколько `--measure {gain,
   bandwidth, thd}` (повторяемый). Дубликаты silently дедуплицируются.

4. Передай те же measure-флаги, что и в одноимённых `bridge measure`
   командах — `--freq`, `--v-in-peak`, `--f-low`/`--f-high`,
   `--mode`, `--output-signal`, `--input-signal`, `--input-source`.
   Команда применяет их ко всем метрикам, которым они нужны
   (gain/thd берут `--freq`; gain-large/thd берут `--v-in-peak`;
   bandwidth берёт `--f-low/--f-high`).

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

## Когда НЕ выбирать

- Sweep по диапазону значений (хочу узнать оптимум) → `/sweep` (T022).
- Просто измерение без правок → `/measure-gain` / `/measure-bandwidth`
  / `/measure-thd`.
- Просто правка без измерения → `/edit` (T004b).
