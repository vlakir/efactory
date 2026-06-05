---
description: Publication-grade экспорт схемы (SVG + PDF + PNG @ 300 DPI) в color и bw.
argument-hint: '<PROJECT_SLUG> [--schematic PATH] [--multi-sheet-mode per-sheet|combined] [--lang ru|en]'
allowed-tools: Bash
---

Пользователь хочет получить публикационные артефакты схемы (для
вставки в LaTeX / Word / Markdown статью) через `efactory publication
export-schematic` (T035).

Args от пользователя: `$ARGUMENTS` (первый позиционный — slug проекта в
`data/projects/`, далее optional флаги).

1. **Извлеки project slug.** Это первый позиционный (не начинается с
   `--`). Если отсутствует — напиши: «Передай slug проекта первым
   аргументом: `/export-schematic-publication se-amp`», остановись.

2. **Запусти:** `efactory publication export-schematic <slug>
   $ARGUMENTS_REST` — `$ARGUMENTS_REST` это всё после slug
   (`--schematic`, `--multi-sheet-mode`, `--lang`).

3. **Покажи stdout полностью.** Команда отчитывается каскадным echo:
   - `publication-export: <abs_path_to_<ts>_dir>` — корень публикации.

4. **Структура output**'а (под указанным `<ts>`-каталогом):
   - `README.md` — описание всех файлов на `--lang`.
   - `schematic/color/per-sheet/<sheet>.{svg,pdf,png}` — на лист.
   - `schematic/bw/per-sheet/<sheet>.{svg,pdf,png}` — то же b&w.
   - `schematic/<color|bw>/combined/<project>.pdf` — только при
     `--multi-sheet-mode=combined`.

5. **Exit-code семантика:**
   - `0` → успех. Все файлы созданы, README ссылается на них
     относительными путями.
   - `1` → domain-level fail: проект не найден (`Project ... not
     found`), manifest повреждён. **Что делать:** проверь
     `efactory project list`; проверь `<project>/project.yaml`.
   - `2` → infrastructure fail: kicad-cli отсутствует / падает,
     rsvg-convert не установлен (для PNG @ 300), не найден root
     `.kicad_sch`, ambiguous multi-sheet. Сообщение в stderr
     подскажет конкретный fix (типично `apt install librsvg2-bin`
     либо `--schematic <path>`).

6. **Когда `--multi-sheet-mode`:**
   - `per-sheet` (default) — по одному SVG/PDF/PNG на каждый лист
     схемы. PDF получается N штук (по числу листов).
   - `combined` — дополнительно создаётся multi-page PDF в
     `combined/<project>.pdf` (vector, все листы в одном файле).
     Per-sheet файлы тоже создаются.

7. **Когда `--lang`:**
   - `ru` (default) — заголовки секций README на русском.
   - `en` — на английском (для international submission).

8. **Когда `--schematic <path>`:**
   - Override auto-detection root `.kicad_sch` (default —
     `<project_root>/<project_name>.kicad_sch` либо единственный
     `*.kicad_sch` в корне). Полезно если в проекте несколько
     схем и нужно указать конкретную.

См. KB topic `design.export-publication` (когда какой формат для
какого пайплайна; рекомендации по dpi/format для разных стандартов
публикации).
