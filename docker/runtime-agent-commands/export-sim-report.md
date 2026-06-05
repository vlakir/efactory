---
description: Publication-grade sim-report (Markdown + plots @ 300 DPI). Поддерживает --rerun для свежей симуляции.
argument-hint: '<PROJECT_SLUG> [--lang ru|en] [--rerun --schematic PATH] [--tran-step Xu --tran-stop Yms] [--ac-points N --ac-fstart F0 --ac-fstop F1]'
allowed-tools: Bash
---

Пользователь хочет получить публикационный отчёт о симуляции
(Markdown с подписанными графиками для вставки в статью) через
`efactory publication export-sim-report` (T035 + T191).

Args от пользователя: `$ARGUMENTS` (первый позиционный — slug проекта,
далее optional флаги).

## 1. Извлеки project slug

Первый позиционный (не флаг). Если отсутствует — напиши: «Передай
slug проекта первым аргументом: `/export-sim-report se-amp`»,
остановись.

## 2. Определи режим

**Без `--rerun` (default)** — `/export-sim-report <slug>` пытается
загрузить latest persistent TRAN/AC waveforms из
`<project>/.efactory/sim-results/<TS>-<analysis>.waveform.json` (T190).
Если waveforms на месте — отчёт получит полные секции с публикационными
plot'ами @ 300 DPI. Если их нет (новый проект, не было /sim-run /
design-to-sim) — отчёт будет metadata-only с notice про missing
данные.

**С `--rerun`** — гонит свежие симуляции через `design_to_sim`
(потребляет ~10-60s на schematic + ngspice + parse). Требует
`--schematic <path>` (путь к `.kicad_sch` относительно проекта) и
хотя бы одну группу analysis-флагов:

- TRAN: `--tran-step <step>` + `--tran-stop <stop>` (SPICE notation: `1u`, `5m`).
- AC: `--ac-points <N>` + `--ac-fstart <f0>` + `--ac-fstop <f1>` (+ optional `--ac-sweep dec|lin|oct`, default dec).
- DC (T188): `--dc-source <V/I>` + `--dc-start <V0>` + `--dc-stop <V1>` + `--dc-step <dV>`.

Можно запустить любую комбинацию (только TRAN, только DC, всё сразу).
Каждая симуляция автоматически persist'ится через T190 hook — следующий
вызов без `--rerun` получит plot'ы без повторной симуляции.

## 3. Запусти

`efactory publication export-sim-report <slug> $ARGUMENTS_REST`

Примеры:

- `/export-sim-report op-amp-inverting` — load из persistent, отчёт.
- `/export-sim-report op-amp-inverting --rerun --schematic op-amp-inverting.kicad_sch --tran-step 1u --tran-stop 5m` — свежий TRAN, persist, отчёт.
- `/export-sim-report se-amp --rerun --schematic se-amp.kicad_sch --tran-step 10n --tran-stop 5m --ac-points 20 --ac-fstart 1 --ac-fstop 100k` — TRAN + AC.
- `/export-sim-report bjt-ce-nfb --rerun --schematic bjt-ce-nfb.kicad_sch --dc-source V1 --dc-start 0 --dc-stop 5 --dc-step 0.05` — transfer characteristic.

## 4. Покажи stdout полностью

Команда отчитывается каскадным echo:

- `publication-export: <abs_path_to_<ts>_dir>` — корень публикации.

## 5. Структура output

- `README.md` — описание файлов на `--lang`.
- `sim-report/report.md` — главный документ публикации.
- `sim-report/plots/tran-<signal>.png`, `sim-report/plots/ac-<signal>.png`, `sim-report/plots/dc-<signal>.png` — графики (300 DPI). Появляются только когда соответствующие waveforms доступны (persistent или --rerun).

## 6. Exit-code

- `0` — успех. report.md создан.
- `1` — проект/схема не найдены / SPICE failed / неверные аргументы.
- `2` — infrastructure fail (writer error / lang invalid).

## 7. `--lang`

- `ru` (default) — `# Отчёт о симуляции — <project>` + кириллица.
- `en` — `# Simulation Report — <project>` + английский.

## 8. Фильтрация сигналов

`--tran-signals v(out),v(in)` / `--ac-signals v(out)` / `--dc-signals v(out)` —
comma-separated trace-имена. По умолчанию рендерятся **все** traces из
соответствующего analysis-результата.

См. KB topic `design.export-publication` (workflow целиком + recommended
post-merge сборка статьи).
