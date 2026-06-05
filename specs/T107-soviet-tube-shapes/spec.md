# T107 Phase 1 — Datasheet-accurate symbol shapes для советских ламп

**Status:** Approved (short-form, без отдельной analyze-фазы — clarify
проведён интерактивно с Vladimir 2026-06-05 в чате).

**Branch:** `T107-phase1-soviet-tube-shapes`

**Контекст:** Phase 0 (PR #46, 2026-05-19) реализовал три Soviet snippet'а
(`Tubes_Soviet:GU50/6P45S/6N6P`) как copy-rename базовых форм EL84/ECC81 —
визуально идентичны source, отличаются только `lib_id` и `Value`. Pin
numbers сохранены от source, не соответствуют datasheet pinouts реальных
ламп (Phase 0 footnote: «OK для SPICE через Sim.Pins mapping»). Phase 1
закрывает визуальный долг: рисует **datasheet-accurate** envelope shapes
+ корректные pin numbers/positions.

## Scope (что делаем)

1. **GU50** (Russian Magnoval 9-pin pentode с top-cap anode):
   - Pentode envelope shape (как EL84).
   - **Top-cap anode** — pin сверху envelope, выходит вверх (Y-down:
     `(at 0 -15.24 90)`), отдельный polyline соединяет top envelope
     curve с pin.
   - Pin numbers per datasheet: `2` (G1), `3` (K + g3 internal),
     `5` (G2), `TC` (anode, top cap). Heater pins (1, 4) в unit 1 не
     показываем (как EL84 — heater в unit 2 которое не используем).
   - `_TUBES_SOVIET_GU50` в `facade.py` обновляется: новый pin layout +
     SPICE-mapping (`P→TC, G→2, K→3, G2→5`).

2. **6П45С / 6P45S** (Soviet sweep beam tetrode с top-cap anode):
   - Beam tetrode envelope shape: pentode с двумя короткими толстыми
     вертикальными **beam-forming plates** по обеим сторонам cathode
     (visual marker для beam tetrode vs обычный pentode).
   - **Top-cap anode** — аналогично GU50.
   - Pin numbers per datasheet (Russian Magnoval base): best-effort из
     моей памяти и публичных reference: `2` (G1), `5` (K), `9` (G2),
     `TC` (anode). Pinout зафиксируется в commit-сообщении с reference
     URL; финальный ack — за Vladimir-ом в GUI.
   - `_TUBES_SOVIET_6P45S` обновляется отдельно от GU50 (Phase 0 их
     pin layouts были общими; Phase 1 разделяет).

3. **6Н6П / 6N6P** (Soviet noval 9-pin dual triode):
   - **Multi-unit** symbol с двумя независимыми triode units (по
     советскому ГОСТу принято «две половинки», аналог ECC81 unit 1 +
     unit 2). Каждый unit — single triode shape (envelope circle +
     anode/grid/cathode lines).
   - Pin numbers per datasheet: Unit A — `1` (A1), `2` (G1), `3` (K1);
     Unit B — `6` (A2), `7` (G2), `8` (K2); pin `9` — heater center
     tap, в symbol units не показываем. Pinout совпадает с ECC81 —
     удобно для multi-unit pattern reuse.
   - `_TUBES_SOVIET_6N6P` (unit 1) обновляется + добавляется
     `_TUBES_SOVIET_6N6P_B` (unit 2) в `_SYMBOL_REGISTRY`. Pattern —
     прямой аналог `_VALVE_ECC81` + `_VALVE_ECC81_B`.

## Clarify-ответы (Q1-Q7, 2026-06-05)

- **Q1 — Workflow:** B (self-drawn из памяти / публичных datasheets).
  Vladimir принял scope risk; финальный visual ack за ним в GUI.
- **Q2 — Глубина:** B (full replica — top-cap geometry, beam-plates,
  dual-unit). Best-effort учитывая Q1B.
- **Q3 — Pin numbers:** A (менять под real datasheet). Pin numbers в
  `_TUBES_SOVIET_*` фасада обновляются + sexp файлы перерисовываются.
- **Q4 — Top-cap pin coords:** A (pin сверху envelope, anode wire идёт
  вверх). Pin number — `TC` (alphanumeric, KiCad supports).
- **Q5 — 6Н6П layout:** двумя половинками по советским ГОСТам =
  multi-unit (A + B) с ГОСТ-style envelope (одинаков с EU/US: круг +
  anode/grid/cathode lines).
- **Q6 — Acceptance:** A. Pre-push (1) functional 3 теста gain ≥ 5×
  проходят; (2) новые structural asserts: GU50/6P45S sexp содержат
  `pin <type> line` с `"TC"`; 6N6P sexp содержит две unit definitions
  (`6N6P_1_*` + `6N6P_2_*`). GUI ack от Vladimir-а перед squash.
- **Q7 — Ритуал:** B (короткая 1-page спека, без отдельного analyze).
  Текущий файл — она.

## Out of scope (НЕ делаем в Phase 1)

- Heater (filament) units в symbol — НЕ добавляем (consistent с EL84
  unit 1 / ECC81 unit 1 conventions; filament inactive в headless SPICE).
- Visual regression через SVG export — НЕ добавляем (Q6A: только
  structural asserts на sexp content + GUI ack).
- Новые Soviet tubes (6Н1П, 6Н2П, 6П14П, 6П3С) — НЕ добавляем (Phase 1
  закрывает только три из BACKLOG'а; добавление новых — отдельная задача).
- Симметризация EL84 / ECC81 source sexp — НЕ трогаем (out of scope,
  это Phase 0 artifacts которые остаются как есть).

## Acceptance

**Functional (pre-push, обязательно 100%):**

- `tests/integration/adapters/schematic_kicad/test_soviet_tubes_facade.py` —
  3 existing test'а (`test_gu50_*`, `test_6p45s_*`, `test_6n6p_*`) проходят
  без модификаций (gain ≥ 5× для каждой лампы).
- Pre-push 5/5: `ruff check . && ruff format --check . && mypy <src> &&
  lint-imports && pytest` — все zero failures.

**Structural (pre-push, новый mini-test):**

- `tests/unit/adapters/schematic_kicad/test_soviet_tubes_phase1_shapes.py`:
  - GU50 sexp file содержит `(pin <kind> line` с `(number "TC"`.
  - 6P45S sexp file содержит `(pin <kind> line` с `(number "TC"` +
    ≥2 polyline'а, помеченных как `beam-forming plates` через
    координатный assert (две короткие вертикальные линии вокруг
    cathode position).
  - 6N6P sexp file содержит symbol sub-blocks `6N6P_1_1` и `6N6P_2_1`
    (multi-unit signature).

**Visual (Vladimir, перед squash-merge):**

- GUI ack: открыть три demo schemas сгенерированные `test_soviet_tubes_
  facade.py` (или прямо `Tubes_Soviet.*.sexp` в KiCad Symbol Editor),
  подтвердить «как из датшита» либо запросить правки.

## Реализация (план фаз)

**Фаза 1.1 — Spec freeze + 6Н6П (multi-unit dual triode):**

- Этот файл commit'нут.
- `Tubes_Soviet.6N6P.sexp` переписан как multi-unit (две unit-блока
  `6N6P_1_1` и `6N6P_2_1`), source — копия `Valve.ECC81.sexp` с pin
  renumbering под 6Н6П datasheet (совпадает с ECC81 → нулевые changes
  pin numbers, только symbol rename).
- `facade.py`: `_TUBES_SOVIET_6N6P` обновлён (pin numbers `1/2/3` для
  unit A вместо `6/7/8` от ECC81 — для ясности pinout = real datasheet);
  `_TUBES_SOVIET_6N6P_B` добавлен (pins `6/7/8`); `_SYMBOL_REGISTRY` key
  `'Tubes_Soviet:6N6PB'` добавлен.
- Acceptance test `test_soviet_tubes_phase1_shapes.py::test_6n6p_*` —
  RED → GREEN.

**Фаза 1.2 — GU50 (top-cap pentode):**

- `Tubes_Soviet.GU50.sexp` переписан: pentode envelope + top-cap polyline
  + pin `TC` at `(0 -15.24 90)`. Pin numbers per Russian Magnoval
  datasheet (2/3/5/TC).
- `_TUBES_SOVIET_GU50` в facade.py обновлён (новый pin layout).
- Acceptance test для GU50 — GREEN.

**Фаза 1.3 — 6П45С (top-cap beam tetrode):**

- `Tubes_Soviet.6P45S.sexp` переписан: pentode envelope + top-cap + два
  beam-forming plate polyline'а (короткие вертикальные толстые линии
  по обеим сторонам cathode). Pin numbers per datasheet best-effort.
- `_TUBES_SOVIET_6P45S` обновлён отдельно (больше не shares с GU50).
- Acceptance test для 6P45S — GREEN.

**Фаза 1.4 — Pre-push + PR:**

- Pre-push 5/5 локально, в т.ч. existing functional 3 теста.
- `git push -u origin T107-phase1-soviet-tube-shapes`, `gh pr create`,
  получаем `#N`.
- `BOARD.md` Doing→Done с реальным `[closed YYYY-MM-DD, PR #N]`.
- Self-review (--comment).
- **Stop point:** жду GUI ack от Vladimir-а перед squash-merge.
- KB sync — не требуется (нет нового user-facing API; symbol drawing
  changes invisible to agent).
