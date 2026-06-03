---
topic: tubes.curve-fitting
description: Fit Koren triode / Ayumi pentode params из IV-точек datasheet'а — pipeline T031, gotcha'и, KG2 fallback.
tags: [tubes, fitting, koren, ayumi, spice, models, datasheet]
---

# Tube-curve-fitting — Koren / Ayumi из datasheet через `/tube-add-from-datasheet`

efactory T031 даёт путь «PDF/PNG datasheet редкой лампы → Koren-
triode / Ayumi-pentode `.lib` в user overlay» через vision-extract
+ собственный scipy-fitter (без wrap'а Заславского, ADR-T031a).

## CLI и slash

- `/tube-add-from-datasheet <part>` — agent-driven workflow
  (vision-extract → CLI → KB topic + опц. smoke).
- `efactory tube fit-from-points <SPICE_ID> --type {triode|pentode}
  --points <iv.json>` — pure compute (готовый JSON → `.lib`).

CLI **не трогает KB**: KB topic создаётся slash-командой
отдельным шагом (Clarify C7 — clear boundary). Это чтобы CLI
оставался pure-compute и легко testable.

## Когда fit `triode` vs `pentode` vs `tetrode`

- **triode** — pins P/G/K, нет screen grid, обычно preamp/line/
  signal triode (12AX7, 6Н2П, 12AT7). Koren-formula с
  `sqrt(KVB + Va²)` denominator.
- **pentode** — pins P/G2/G/K, со screen grid. Output curves
  обычно при фиксированном Vg2 = 150 / 200 / 250 V. Koren-pentode
  form (один член + atan plate-term).
- **beam tetrode** — структурно как пентод (KT88, 6L6, 6П3С); fit
  под `--type pentode`, в `.lib` header пишется `--header-type
  tetrode`. Spec C2: отдельного fitter-режима не вводим — Ayumi-
  формула покрывает обе семьи.

## Канонический Koren — 2× множитель в формуле

В built-in `data/models/tubes/*.lib` `G1`/`G2` source видишь:

```
G1 P K VALUE={(sgn(V(7))*pwr(abs(V(7)),EX)
              +sgn(V(7))*pwr(abs(V(7)),EX))/KG1 * ...}
```

Два одинаковых члена → эффективно `2 * E1^EX / KG1`. Это **не
ngspice artefact** — это часть оригинальной публикации Norman
Koren'а («Improved vacuum tube models for SPICE simulations»).
T031 Phase 1 fitter использует ту же форму с 2× для совместимости
параметров KG1/KG2 с built-in значениями.

## KG2 не identifiable из Ia (важно!)

В Ayumi/Koren-pentode формулировке Ig2 (screen current) имеет
**свой** scaling KG2, не входящий в Ia. Если ты vision-extract'ил
только output Ia curves (большинство datasheet'ов рисуют их
solid line; Ig2 как dashed line часто игнорируется), KG2 fit'ом
**не идентифицируется** — scipy сходится в произвольное значение
в bounds, без сигнала из data.

Два режима:

- **Ia-only** (`screen_curves` пуст в JSON, default): T031 CLI
  применяет typical ratio `KG2 = kg2_ratio * KG1`, default
  `kg2_ratio=5.0`. В built-in EL34 это даёт 4500/650 = 6.92,
  в 6V6_AYUMI = 4200/1672 = 2.51 — диапазон правдоподобный.
  Stdout summary покажет `kg2: overridden = ratio * kg1 = X`.
- **Joint Ia+Ig2** (расширь JSON массивом `screen_curves`):
  fitter использует joint loss, KG2 становится identifiable per
  SC#1 (≤5%). Stdout: `mode: joint Ia+Ig2 (KG2 identifiable)`.

**Когда важна точность Ig2-моделирования** (class-AB2 dynamic
screen current, например) — собирай Ig2 точки тоже. Для plain
Ia-simulation typical ratio достаточен.

## Knee region — known model limit

Mullard / Philips / etc. datasheet'ы показывают резкий knee при
low Va (curve почти вертикальна в районе Va ≈ KVB). Koren-formula
с `atan(Va/KVB)` или `sqrt(KVB+Va²)` даёт **более пологий** rise
→ systematic gap в knee region до 30-70% по Ia.

Practical implication: при выборе control-точек для acceptance
бери **plateau** (Va ≥ 150-200 V), там Koren-fit точен в ±15% per
SC#2 (Spec T031 §4). Knee — диагностика, не acceptance metric.

Phase 0 probe (2026-06-03, Mullard EL34 + built-in koren/EL34.lib
параметры) подтвердил: на published reference op-point
(Va=250, Vg2=250, Vg=-12.2 → 100 mA Mullard) Koren-fit error
+13.4%; vision-extract → fit improves до ~4%.

## Vision feasibility (A-W5)

Claude vision способен прочитать output characteristics с
точностью **±4-5% на plateau region** для quality scan'ов
(Mullard 1962, Philips 1960, RCA HB-3) — Phase 0 cross-check
с published Mullard op-point это подтвердил.

При плохом scan'е (low-res советский datasheet, OCR-degraded):
gap может вырасти до ±15-20%. Fallback **не** «GUI picker» (Spec
§7 Out of Scope) — попроси пользователя дать более качественный
скан или вручную выгрузить JSON в S2-сценарии (`efactory tube
fit-from-points` напрямую).

## JSON schema (важные validation rules)

- `tube_type='pentode'` → `screen_voltage_v` **required**.
- `tube_type='triode'` → `screen_voltage_v` **запрещено**.
- `screen_curves` **только** для pentode; для triode reject.
- Минимум 1 curve, минимум 1 точка на curve. Реалистично — 4-5
  curves по Vg, 7-10 точек на curve (на pentode).
- Все Va > 0, Ia ≥ 0 (cutoff допускается).

## Транслитерация имён

Кириллица → латиница (Spec T031 §5). Особый случай:
- «Ж» → `Zh` (нет precedent'а в built-in `custom/`, дефолт).
- Финальный SPICE id показывай пользователю **перед** записью
  JSON, спрашивай подтверждение.
- Reject (без транслитерации) — нет: всегда даём предложение.

Built-in примеры: `6N1P` (6Н1П), `6P14P` (6П14П), `GU50` (ГУ50),
`5S3S` (5Ц3С), `6P45S` (6П45С).

## Anti-pattern (NE делай)

- **Не fit'и через ad-hoc scipy.curve_fit без bounds.** Без
  `method='trf', bounds=...` (A-C1) LM-default молча игнорирует
  bounds и сходится в нефизичные значения. T031 fitter это уже
  делает; не дублируй и не «упрощай».
- **Не пиши `.lib` руками с `tube_type:` отсутствующим в header.**
  `FilesystemSpiceModelLibrary` (T006) использует этот marker
  для tube-type detection. T031 writer проставляет
  автоматически — не убирай.
- **Не используй `--include-vct --type pentode`.** Vct (cathode
  contact potential) — параметр **только** Koren-triode, для
  Ayumi-pentode не определён. CLI argparse + use case оба ловят
  эту комбинацию (A-W1).
- **Не подменяй existing built-in `.lib` без `--force`.** Default
  out_dir — user overlay (`$XDG_DATA_HOME/efactory/models/tubes/
  custom/`), он перекрывает built-in. Если хочешь явно
  override'нуть built-in 12AX7 под свою партию ECC83 Sovtek —
  имя должно быть `12AX7_SOVTEK.lib` (S3 use case), built-in
  остаётся нетронутым.

## См. также

- Spec `specs/T031-tube-curve-fitting/spec.md` (полная
  специфика — клэрифай + analyze).
- `phase-0-probe.md` — vision feasibility check на Mullard EL34.
- ADR-T031a в `DECISIONS.md` — почему свой fitter, не wrap
  Заславского.
- `/kb-search tubes.6p14p`, `tubes.6n2p` — built-in tube models
  Phase 5/6.
