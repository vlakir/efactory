---
description: Vision-extract IV-точек анодных характеристик лампы из datasheet PDF/PNG, fit Koren/Ayumi → .lib в user overlay (T031).
argument-hint: '<part> [<path-to-datasheet>]'
allowed-tools: Bash, Read
---

Пользователь хочет добавить SPICE-модель новой лампы (часто
советской / редкой / экзотической, не покрытой built-in collection
из T027) в efactory library, используя datasheet как источник.

Workflow (Spec T031 S1 — vision-driven primary path):

1. **Извлеки `<part>`** из `$ARGUMENTS` — обязательный первый
   позиционный аргумент. Если его нет — спроси: «Какая лампа?
   (`/tube-add-from-datasheet <part>`)».

2. **Найди datasheet файл.**
   - Если `$ARGUMENTS` содержит второй аргумент `<path>` —
     используй его.
   - Иначе сканируй последние user-сообщения чата на PDF/PNG
     attachment. Если **один** image attachment — используй его.
   - Если **несколько** images / **ни одного** — **спроси
     пользователя путь явно**, не угадывай. Пример: «Не вижу
     datasheet в последних сообщениях. Приложи PDF/PNG или укажи
     путь: `/tube-add-from-datasheet 6Ж38П /tmp/6zh38p.pdf`».

3. **Открой datasheet через `Read`.** Для PDF — `pages=...`
   диапазон. Найди страницу с **output characteristics**: «Anode
   current plotted against anode voltage with control-grid voltage
   as parameter» или подобная (Ia vs Va при разных Vg, на одном
   фиксированном Vg2 для пентода).

4. **Определи тип лампы.**
   - **triode** — pins P/G/K, нет screen grid; обычно «preamp /
     line / signal triode» (12AX7, 6Н2П, 12AT7).
   - **pentode** — pins P/G2/G/K, есть screen grid; output curves
     при фиксированном Vg2 = 150 / 200 / 250 V обычно.
   - **beam tetrode** — структурно как пентод, fit'им под тип
     `pentode`, в `.lib` выставим `--header-type tetrode` (6L6,
     KT88, 6П3С).

5. **Extract IV-точек в JSON** (схема Spec T031 §5). Для каждой
   curve constant-Vg прочитай 5-10 точек (Va, Ia) равномерно по
   диапазону, акцент на **plateau region** (Va ≥ 100-150 V) — там
   Koren-формула наиболее адекватна datasheet'у. Knee region
   (Va < knee) можно дать 1-2 точки опционально; **не** трать
   усилия на «точный knee» — Koren-формула там систематически
   отстаёт (см. KB `tubes.curve-fitting`).

   Структура (пентод EL34 example, Vg2 = 250 V):
   ```json
   {
     "tube_name": "6Ж38П",
     "tube_type": "pentode",
     "source": "datasheet: <ref>",
     "date_extracted": "<YYYY-MM-DD>",
     "screen_voltage_v": 150,
     "curves": [
       {"vg": -1.0, "points": [[50, 5.2], [100, 7.1], ...]},
       {"vg": -2.0, "points": [[50, 2.4], [100, 4.3], ...]}
     ]
   }
   ```

   Для triode — поле `screen_voltage_v` **не** ставится.

   **Опционально:** если datasheet рисует пунктирные curves Ig2
   (screen current) — extract их в `screen_curves` той же формы.
   Тогда KG2 станет identifiable из fit (см. T031 Phase 1+
   rationale). Если их нет — fitter применит typical KG2 ≈ 5·KG1.

6. **Транслитерируй `<part>` в slash-safe SPICE id.** Таблица
   из Spec T031 §5:

   | Кириллица | Латиница |
   |-----------|----------|
   | А→A, Б→B, В→V, Г→G, Д→D, Е→E, Ж→Zh, З→Z, И→I, К→K | |
   | Л→L, М→M, Н→N, О→O, П→P, Р→R, С→S, Т→T, У→U, Ф→F | |
   | Х→Kh, Ц→Ts, Ч→Ch, Ш→Sh, Щ→Sch, Ъ→\_, Ы→Y, Э→E, Ю→Yu, Я→Ya | |

   Spice id format: `[A-Z0-9][A-Z0-9_]+`. Примеры:
   - «6Ж38П» → `6ZH38P` (для file/SPICE) + display name `6Ж38П`
     сохраняется в `tube_name` JSON.
   - «6П13С» → `6P13S`.
   - «EL34» → `EL34`.
   - «12AX7» → `12AX7`.

   **Покажи пользователю предлагаемое имя перед записью JSON** и
   спроси подтверждение, особенно если оригинальное имя содержит
   букву Ж/Щ/Ч/Ш (для них транслитерация неоднозначна).

7. **Сохрани JSON в `/tmp/<spice_id>_iv.json`.** Пиши через
   `Write` tool, форматируй с indent=2 для читаемости.

8. **Запусти fit:**
   ```
   efactory tube fit-from-points <SPICE_ID> --type {triode|pentode}
     --points /tmp/<spice_id>_iv.json
     [--header-type tetrode]
     [--kg2-ratio 5.0]
   ```

   Default `--out` — user overlay
   (`$XDG_DATA_HOME/efactory/models/tubes/custom/<SPICE_ID>.lib`).
   Перезапись existing — `--force`.

   Stdout summary (T031 SC#3) даст:
   - `lib: <path>` — где лежит `.lib`.
   - `fit: n_points=N rms=X mA` — качество fit.
   - `params: {...}` — финальные Koren / Ayumi параметры.
   - `mode: joint Ia+Ig2 (KG2 identifiable)` — если screen_curves
     был передан.
   - `kg2: overridden = ratio * kg1 = X` — если Ia-only fallback.

9. **Создай KB topic `tubes.<spice_id_lowercase>`** через
   `/kb-add`. Тело — короткое summary:

   ```
   # <SPICE_ID> (display: <tube_name>) — fitted T031 pipeline

   Type: <triode|pentode|tetrode>
   Source: <source from JSON>
   Date fitted: <date>
   RMS: <X> mA over N points
   KG2: <identifiable from Ig2 | typical ratio fallback>
   .lib: <path>

   Применение: ...  (1-2 строки — preamp / output / RF / ...)
   ```

10. **Smoke-симуляция типового включения.** Опционально, если
    пользователь явно просит acceptance. Spec T031 §3:
    - **Pentode RF** (6Ж38П): `.op` в типичной bias-точке,
      сравнение Ia с datasheet reference op-point.
    - **Pentode audio output** (6П13С): SE-amp на основе template
      `data/templates/se-amp/` (копируем, в `.kicad_sch` подменяем
      `.SUBCKT 6P14P` на `<SPICE_ID>`, **резистивная нагрузка
      5-10 kΩ** на анод вместо OPT), `.op` + проверка анодного
      тока. Запуск — `/sim-run` или `efactory bridge sim-run op`.

11. **Доклад пользователю.** Шаблон:
    ```
    ✓ Лампа <display_name> добавлена.
      .lib: <path>
      RMS: <X> mA over N points (fit accuracy)
      KB topic: tubes.<spice_id_lowercase>
      [Smoke @ Va=..., Vg=...: Ia_model=... mA vs datasheet=... mA → Δ=...%]
    ```

**См. также:** `/kb-search tubes.curve-fitting` для pitfall'ов
(KG2 identifiability, knee region accuracy, vision feasibility).
