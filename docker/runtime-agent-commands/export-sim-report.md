---
description: Publication-grade sim-report (Markdown + plots @ 300 DPI). MVP — metadata only до T190+T191.
argument-hint: '<PROJECT_SLUG> [--lang ru|en]'
allowed-tools: Bash
---

Пользователь хочет получить публикационный отчёт о симуляции
(Markdown с подписанными графиками для вставки в статью) через
`efactory publication export-sim-report` (T035).

Args от пользователя: `$ARGUMENTS` (первый позиционный — slug проекта,
далее optional `--lang`).

1. **Извлеки project slug.** Первый позиционный (не флаг). Если
   отсутствует — напиши: «Передай slug проекта первым аргументом:
   `/export-sim-report se-amp`», остановись.

2. **Запусти:** `efactory publication export-sim-report <slug>
   $ARGUMENTS_REST` — `$ARGUMENTS_REST` это `--lang ru|en` если
   передан.

3. **Покажи stdout полностью.** Команда отчитывается каскадным echo:
   - `publication-export: <abs_path_to_<ts>_dir>` — корень публикации.

4. **Структура output**'а:
   - `README.md` — описание файлов на `--lang`.
   - `sim-report/report.md` — главный документ публикации.
   - `sim-report/plots/*.png` — графики (300 DPI). В текущем MVP
     отсутствуют (см. п.6).

5. **Exit-code:**
   - `0` → успех. report.md создан с метаданными + magnetics
     graceful-skip notice.
   - `1` → проект не найден / manifest повреждён.
   - `2` → infrastructure fail (writer error).

6. **⚠️ Текущее ограничение MVP (T035 Phase 4.2):**
   - Команда формирует **только метаданные** в `report.md`:
     проект, дата публикации, версия efactory, язык, magnetics-
     missing notice.
   - **TRAN/AC/parametric sweep секции отсутствуют** — заблокировано
     T190 (raw waveform persistence) и T191 (`--rerun` integration)
     в `BACKLOG.md`. После закрытия этих задач команда получит
     `--rerun` флаг и сможет наполнять отчёт реальными графиками
     симуляции @ 300 DPI с ru/en подписями.
   - **Workaround сейчас:** для production-grade документов
     запускай `/sim-run` отдельно, забирай terminal plot через
     `/bridge plot` (preview @ 120 DPI), и руками вставляй в
     статью. После T190+T191 эта команда заменит ручной workflow.

7. **Когда `--lang`:**
   - `ru` (default) — `# Отчёт о симуляции — <project>` + кириллица.
   - `en` — `# Simulation Report — <project>` + английский.

См. KB topic `design.export-publication` (workflow целиком; T190/T191
roadmap; рекомендации по post-merge сборке статьи).
