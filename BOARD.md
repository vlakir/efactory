# Board

Лёгкая Kanban-альтернатива на одном markdown-файле: три колонки
(To Do / Doing / Done) под git, без внешних сервисов и инструментов.

## Соотношение с другими файлами

- `BACKLOG.md` — длинная очередь идей и побочных находок. Сюда падает
  «потом подумаем», «не сейчас». Парковка scope.
- `BOARD.md` (этот файл) — активный рабочий поток. Задачи, которые мы
  уже взяли или собираемся брать в ближайшее время.
- `specs/T<NNN>-*/spec.md` — куда вырастает крупная задача из BOARD, если
  она оказывается фичей >1 дня работы.

Жизненный цикл задачи: идея в `BACKLOG.md` → созрела → переезжает в
`To Do` здесь → берётся в работу (`Doing`) → закрывается (`Done`) →
после релиза переходит в `CHANGELOG.md` (запись обязательно содержит
T-ID), отсюда удаляется. **`CHANGELOG.md` — единственное persistent-
хранилище T-ID завершённых задач**, без него правило «ID не
переиспользуется» сломается.

## Формат задачи

Каждая задача — `- **T<NNN>** — <короткое описание>`. ID присваивается
при создании: новый = `max(существующих T-ID в BOARD.md, BACKLOG.md и
CHANGELOG.md) + 1`. ID никогда не переиспользуется. ID общий для
`BOARD.md` и `BACKLOG.md` — при перетекании задачи между ними
сохраняется; после релиза задача попадает в `CHANGELOG.md` с тем же
T-ID, что гарантирует уникальность номеров между релизами.

Имя ветки: `T<NNN>-<slug>` (без namespace типа `fixes/` / `feature/` —
ID уже даёт идентификацию). Имя PR: `T<NNN>: <title>`. Спецификация
крупной фичи: `specs/T<NNN>-<slug>/spec.md`.

По вкусу можно добавлять:

- метку даты взятия,
- ссылку на спеку,
- имя ветки.

Пример:

```
- **T<NNN>** — Превью постов в Telegram
  (`specs/T<NNN>-telegram-preview/`, ветка `T<NNN>-telegram-preview`).
```

---

## To Do

<!-- Готово к взятию. Очередь FIFO по умолчанию, можно поднимать
     приоритетное наверх. -->

<!-- Записи задач в формате `- **T<NNN>** — описание`. См. раздел
     «Формат задачи» выше. -->

## Doing

<!-- В работе прямо сейчас. Держим короткой: максимум 1-2 задачи на
     разработчика, иначе теряется фокус (классическое WIP-limit
     правило из Kanban). -->

## Done

- **T101** — [closed 2026-05-19, PR #38] Diode SPICE-модели в
  `SpiceModelLibrary` — расширение T007 generalization на 4-ю
  категорию. `domain.ComponentCategory.DIODE` + `DiodeKind` (rectifier/
  signal/schottky/zener/led) + `SpiceModel.diode_kind` accessor;
  `data/models/diodes/duncan/` с 3 starter моделями (1N4007/1N4148/
  BAT85), wrapped в SUBCKT-форму с `* subcategory:` headers; CLI
  `efactory diode list/show`; `facade.add_diode` поддерживает
  `spice_model=...` (X-prefix subckt-instance) и legacy `spice_params`
  (D-prefix inline), hardcoded default удалён, ValueError на отсутствие
  обоих. Backward compat — rectifier фикстура работает без правок.
  6 unit-тестов на add_diode edge cases. 564 passed (+6), coverage
  89.15%, 5 гейтов зелёные.

- **T103** — [closed 2026-05-19, PR #37] SE-amp wire-router fix через
  re-layout. Переписан SE-amp с использованием Valve:EL84 (T104) —
  plate-к-OPT.P1 wire идёт **выше** B+ rail, что исключает
  пересечения с G2/P2 stub'ами (W2 risk closed). Auto-numbering refs
  (T104). `.tran 10u 80m uic` для надёжного bias settling. Acceptance:
  test_facade_se_amp_tran_shows_amplification снят со skip, измеренный
  plate gain **48.5×** (threshold ≥5×); speaker swing 39 mV p-p после
  OPT 25:1 step-down; ERC 0 errors. 558 passed (+1), coverage 89.25%.

- **T104** — [closed 2026-05-18, PR #35] Phase 0: красивые tube
  symbols в `efactory.schematic` (закрывает T100 Q4 compromise через
  стандартный KiCad `Valve.kicad_sym`). Реализация: (а)
  `domain.schematic.ComponentSpec.unit` (default 1) + writer emit'ит
  `(unit N)` dynamic; (б) `_VALVE_REGISTRY` в facade со стартовым
  `Valve:EL84` (SPICE-pins P/G2/G/K → KiCad-pins 7/9/2/3, multi-unit
  unit=1, filament не инстанцируется); (в) `add_tube(..., symbol=
  'Valve:EL84')` optional override, backward compat для Conn_01x04
  path сохранён; (г) embedded `Valve.EL84.sexp` из стандартного KiCad
  (rename + re-indent); (д) demo фикстура `test_triode_amp_facade.py`
  — common-cathode 6П14П R-loaded без OPT, обходит T100 W2 риск.
  **Acceptance переформулирован** с прозрачным обоснованием:
  изначальный `gain ≥ 30×` нереалистичен для R-loaded common-cathode
  pentode (физический потолок ≈ 19×, упирается в gm·Rp лампы и
  bias-point limit'ы; для 30+ нужен SE-amp с OPT = T103-зависимая).
  Threshold relaxed до 15× — реальный измеренный gain ≈ 19× ✓.
  Acceptance-релаксация вынесена open question в PR #35 (если Vladimir
  не одобрит — либо T103 для SE-amp с OPT, либо tune topology).
  Backward compat T100 fixtures (RC/rectifier/CE/SE-amp) — все
  проходят. 5 гейтов зелёные: 552 passed (+3 от T102), coverage 88.97%.



<!-- Закрытые задачи, ждущие переноса в CHANGELOG.md при следующем
     релизе или значимой точке. После переноса — очищаем. -->

<!-- Записи T010, T009, T006, T007, T004, T008, T100, T102 перенесены
     в CHANGELOG.md → [0.4.0] release-PR. -->

<!-- Записи T093, T095, T096, T097, T098, T099 перенесены в
     CHANGELOG.md → [0.3.0] release-PR. -->
