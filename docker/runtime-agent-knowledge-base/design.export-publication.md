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

После закрытия T190 + T191 команда формирует полный publication-grade
отчёт с TRAN/AC plots @ 300 DPI. Два режима:

### Без `--rerun` (default)

Грузит latest TRAN/AC waveforms из persistent sidecar
`<project>/.efactory/sim-results/<TS>-<analysis>.waveform.json` (T190).
Бесплатно после `/sim-run <project>` / `/measure-*` / любого
`design_to_sim` — те уже записали waveforms. Если waveforms нет —
получится metadata-only report с magnetics-missing notice (как
старый MVP).

```
/export-sim-report op-amp-inverting
/export-sim-report op-amp-inverting --lang en
```

### С `--rerun`

Гонит свежие симуляции через `design_to_sim` (потребляет ~10-60s).
Требует `--schematic <path>` (внутрипроектный относительный) +
хотя бы одну пару analysis-флагов:

- TRAN: `--tran-step <step>` + `--tran-stop <stop>` (SPICE notation
  `1u`/`5m`).
- AC: `--ac-points <N>` + `--ac-fstart <f0>` + `--ac-fstop <f1>`
  (+ optional `--ac-sweep dec|lin|oct`, default dec).
- DC (T188): `--dc-source <V/I>` + `--dc-start <V0>` +
  `--dc-stop <V1>` + `--dc-step <dV>` для transfer characteristic.

Каждая симуляция автоматически persist'ится через T190 hook —
следующий вызов без `--rerun` получит plot'ы без повторного запуска
SPICE.

```
/export-sim-report op-amp-inverting --rerun \
  --schematic op-amp-inverting.kicad_sch \
  --tran-step 1u --tran-stop 5m
/export-sim-report se-amp --rerun \
  --schematic se-amp.kicad_sch \
  --tran-step 10n --tran-stop 5m \
  --ac-points 20 --ac-fstart 1 --ac-fstop 100k
```

### Фильтрация сигналов

`--tran-signals v(out),v(in)` / `--ac-signals v(out)` — comma-
separated trace-имена. По умолчанию рендерятся **все** traces из
TRAN/AC waveform.

### 🚫 Anti-pattern (не делай так)

- НЕ пиши custom matplotlib скрипт типа `from spicelib.raw import
  RawRead; ...; fig.savefig(dpi=300)`. Это **изобретение
  велосипеда** — `/export-sim-report --rerun` уже делает 300 DPI
  PNG @ ru/en labels. Custom script — extra dependency,
  extra maintenance, не интегрирован с T025 / T035.
- НЕ запускай `ngspice -b -r out.raw netlist.cir` руками —
  оркестрация лежит в `/sim-run`, `/measure-*`, `/export-sim-report
  --rerun`.
- НЕ предлагай юзеру скачать matplotlib / spicelib — efactory
  всё содержит, у юзера не должно быть extra setup.

### Что команда делает

- `report.md` с metadata + TRAN-секция (плоты + подписи) + AC-секция
  + magnetics-секция (если есть FEM summary) + measurement summary.
- `sim-report/plots/tran-<signal>.png`,
  `sim-report/plots/ac-<signal>.png` @ 300 DPI с ru/en подписями.
- `README.md` с описанием артефактов.

### Exit codes

- `0` — успех.
- `1` — project не найден / manifest повреждён.
- `2` — writer fail (IO error).

## Когда какая команда

- Финализация **схемы** для submission (vector + raster, color +
  bw) → `/export-schematic-publication`.
- Сборка **draft статьи целиком** с графиками симуляции →
  `/export-sim-report --rerun` (T191): свежий прогон TRAN+AC +
  300 DPI публикационные плоты с локализованными подписями.
- Повторный экспорт без свежей симуляции → `/export-sim-report`
  (без `--rerun`): load из persistent sidecar (T190), за секунды
  получаем тот же report.md.

## Общие принципы

- **Read-only вывод.** Команды не мутируют входную схему, шаблоны,
  результаты симуляции.
- **`<ts>` collision-safe** (spec W-4): если два вызова в одну
  секунду — второй получит суффикс `-1`, `-2`.
- **Локализация label'ов осей графиков:**
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
