---
topic: design.export-publication
description: T035 publication workflow — `/export-schematic-publication` и `/export-sim-report` для научно-технических статей.
tags: [publication, schematic, sim-report, t035, lang-ru-en, dpi-300]
---
# Publication workflow (T035) — slash-команды для статей

`/export-schematic-publication` и `/export-sim-report` формируют
готовые к публикации артефакты в `<project>/out/publications/<ts>/`
для прямой вставки в LaTeX / Word / Markdown статью.

## `/export-schematic-publication <PROJECT_SLUG>` — схема

Создаёт **три формата** × **две цветовые версии** = 6 файлов на
лист:

- **SVG** (vector, kicad-cli sch export svg) — для editor'ов с
  vector-paste либо для post-processing.
- **PDF** (vector, kicad-cli sch export pdf) — `\includegraphics`
  в LaTeX, embed в Word.
- **PNG @ 300 DPI** (raster, rsvg-convert) — print-publication
  стандарт; универсально, fallback когда vector не работает.

Цветовые версии: **color** (KiCad default theme) + **bw**
(`--black-and-white`) — для журналов без цветной печати.

Структура output:

```
<project>/out/publications/<ts>/
  README.md
  schematic/
    color/per-sheet/<sheet>.{svg,pdf,png}
    bw/per-sheet/<sheet>.{svg,pdf,png}
    color/combined/<project>.pdf    (только при --multi-sheet-mode=combined)
    bw/combined/<project>.pdf
```

### Multi-sheet mode

- **`--multi-sheet-mode per-sheet`** (default) — по одному файлу
  на лист в каждом формате. PDF — N штук.
- **`--multi-sheet-mode combined`** — дополнительно создаётся
  multi-page PDF в `combined/<project>.pdf` (vector, все листы).
  Per-sheet файлы тоже создаются (на случай если нужны
  индивидуальные).

SVG/PNG combined невозможен (форматы single-page). README в
`<ts>`-каталоге упомянет это явно.

### Language (`--lang ru|en`)

Влияет на:
- Заголовки секций README (`# Публикация` vs `# Publication`);
- Подписи в таблице файлов (`Лист | SVG | PDF | PNG` vs `Sheet | SVG | PDF`).

Sheet names и формат-агностичная информация (DPI, формат) не
переводятся.

### Exit codes

- `0` — успех, README + все файлы созданы.
- `1` — project не найден / manifest повреждён.
- `2` — kicad-cli не установлен / упал, rsvg-convert отсутствует
  (`apt install librsvg2-bin`), schematic не найден, ambiguous
  multi-sheet (`--schematic <path>` уточняет).

## `/export-sim-report <PROJECT_SLUG>` — sim-report

⚠️ **Текущее состояние MVP (T035 Phase 4.2):** команда формирует
только metadata-секцию + magnetics-missing notice в `report.md`.

**TRAN/AC/parametric плоты ОТСУТСТВУЮТ** — заблокировано двумя
follow-up задачами в `BACKLOG.md`:

- **T190** — Persistence raw SPICE waveforms. Сейчас `sim_run`
  пишет только `SimResult` JSON snapshot (summary metadata), без
  raw `time`/`traces` массивов. Значит TRAN/AC plot rendering от
  existing results невозможен.
- **T191** — `--rerun` integration. После закрытия T190, добавить
  `--rerun` флаг + флаги для analysis params + сборка
  `SimulationResultsBundle` из реальных результатов.

### Текущий workflow до T190+T191

Для production-grade статей с plots:

1. `/sim-run <project>` — прогон симуляции (или `/bridge plot
   {ac,tran} --output <abs.png>` для PNG @ 120 DPI preview).
2. Открой PNG в `eog`, сделай скриншот / используй preview.
3. Руками вставь в статью.

После T190+T191 этот manual workflow заменится одной командой
`/export-sim-report <project> --rerun`.

### Что MVP всё-таки делает

Команда полезна **сейчас** для:

- Test placeholder в publication tree (правильная структура
  каталогов + README ссылки).
- Documentation проекта (metadata + версия efactory).
- Magnetics graceful skip notice → подсказывает запустить
  `/mag-verify` для FEM-валидации.

### Exit codes

- `0` — успех.
- `1` — project не найден / manifest повреждён.
- `2` — writer fail (IO error).

## Когда какая команда

- Финализация **схемы** для submission (vector + raster, color +
  bw) → `/export-schematic-publication`.
- Сборка **draft статьи целиком** с графиками симуляции → пока
  manual (см. workaround выше), после T190+T191 — `/export-sim-report
  --rerun`.

## Общие принципы

- **Read-only вывод.** Команды не мутируют входную схему, шаблоны,
  результаты симуляции.
- **`<ts>` collision-safe** (spec W-4): если два вызова в одну
  секунду — второй получит суффикс `-1`, `-2`.
- **Локализация label'ов осей графиков** (после T190+T191):
  `--lang ru` → «частота, Гц (лог.)», «магнитуда, дБ», «время, с»;
  `--lang en` → «frequency, Hz (log)», «magnitude, dB», «time, s».
- **OUT OF SCOPE:** PDF composing статьи (`\documentclass`,
  abstract, references) — это работа автора, не efactory. Команды
  дают только **building blocks**.
- **`--multi-sheet-mode=combined`** не зависит от количества
  листов в проекте (single-sheet → combined PDF == per-sheet PDF
  по содержанию, но разные filenames + dirs).

## Pitfall'ы и заметки

- **rsvg-convert на host:** на dev-машине Vladimir-а отсутствует
  (`librsvg2-bin` ставится только в `efactory:linux` контейнере).
  E2E тест `/export-schematic-publication` на host skip'ается; в
  контейнере работает.
- **kicad-cli `--pages` semantics:** PDF без `--pages` → один
  combined multi-page PDF; PDF с `--pages I` → отдельный single-
  page PDF (используется adapter'ом для per-sheet PDF цикла).
- **Page-to-sheet-name mapping для multi-sheet PDF:** adapter
  делает glob sorted-by-name SVG files, и map'ит page index → sheet
  filename по этой sorted order. Если KiCad's page ordering
  расходится с alphabetical SVG sorting — per-sheet PDFs могут
  получить «не свои» имена. Edge case для multi-sheet проектов с
  hierarchical sheets; single-sheet проекты не задеты. SC-6
  acceptance test in Phase 5 (synthetic multi-sheet) проверит.
