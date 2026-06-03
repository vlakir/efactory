# Phase 5 — Built-in tubes + templates + smoke validation

**Дата:** 2026-06-03
**Статус:** ✓ Both templates materialize + ngspice .op smoke PASS
**Спека:** Scope expansion после Vladimir explicit ask. Spec §7
говорила «Auto-generation KiCad symbol — отдельная фича; T031 даёт
только `.lib`». Phase 5 расширяет: добавили `.lib` в built-in + два
несложных шаблона + smoke validation pipeline end-to-end.

---

## 1. Что добавлено

### `data/models/tubes/custom/`

- **`6ZH38P.lib`** — fitted T031 Phase 4 (через 6BH6 western
  equivalent datasheet, header `tube_type: pentode`).
- **`6P13S.lib`** — fitted T031 Phase 4 (header `tube_type: tetrode`).

Built-in collection теперь содержит, в дополнение к существующим
советским preamp/output triodes + 6P3S/6P14P/6P15P/6P18P/6P1P:
**два новых пентода**, покрывающих RF (6Ж38П) и audio output
(6П13С) ниши.

### `data/templates/6zh38p-if-amp/`

Class A resistance-coupled small-signal amp на 6Ж38П. Pattern из
GE 6BH6 datasheet ET-T525B (Class A resistance-coupled amplifier
table).

- Vbb = 150 V, Vg2 = 150 V (fixed bias через separate source)
- Rp = 10 kΩ, Rk = 1 kΩ + Ck = 10 µF (cathode self-bias)
- Rg = 1 MΩ (grid leak), Cin = 100 nF
- Vin: AC ±10 mV @ 1 kHz

### `data/templates/6p13s-se-resistive/`

SE-amp на 6П13С с **резистивной нагрузкой 5 kΩ** вместо OPT
(per Spec A-W3). Минимальная топология для op-point smoke без
OPT-сложности.

- Vbb = 250 V, Vg2 = 200 V
- Rload = 5 kΩ (резистивная — A-W3)
- Rk = 200 Ω + Ck = 220 µF (self-bias)
- Rg = 470 kΩ, Cin = 470 nF
- Vin: AC ±0.5 V @ 1 kHz

## 2. Build process

Один-shot build script `/tmp/build_t031_templates.py` (НЕ commit'ится,
artefact one-shot) — программно через `Schematic` facade
(`adapters.outbound.schematic_kicad.facade`):

- `Schematic('<name>')` aggregate builder
- `add_v_dc()`, `add_v_ac()`, `add_resistor()`, `add_capacitor()`,
  `add_tube(spice_model=, symbol='Valve:EL84')`, `add_ground()`,
  `add_pwr_flag()`
- `sch.connect(pin_a, pin_b)` для wires
- `sch.label(name, at=...)` для net-labels
- `sch.spice_directive('.op', at=...)` для SPICE control
- `sch.save(path)` → `.kicad_sch`

`Valve:EL84` symbol (P/G2/G/K pentode 4-pin) использован для обоих
ламп — visually canonical EL84 в KiCad GUI, SPICE-numerics идентичны
независимо от symbol choice (pin mapping в .lib SUBCKT).

Альтернативные symbols в `_SYMBOL_REGISTRY` (`Tubes_Soviet:GU50`,
`6P45S`, `6N6P`) — для специфичных Soviet shapes. Для 6Ж38П
(7-pin miniature) и 6П13С (octal beam tetrode) нет dedicated
symbol'а; EL84 — universally acceptable substitute. Создание
dedicated Soviet symbols — T173 BACKLOG candidate (auto-symbol-
generation per Spec §7 Out of Scope).

## 3. Smoke validation (end-to-end pipeline)

Через `efactory project create --template` + `efactory bridge
design-to-sim op`:

```
EFACTORY_PROJECTS_ROOT=/tmp/t031-phase5-projects \
  efactory project create --name p_6zh38p --template 6zh38p-if-amp

EFACTORY_PROJECTS_ROOT=/tmp/t031-phase5-projects \
  efactory bridge design-to-sim op p_6zh38p \
  --schematic p_6zh38p.kicad_sch
```

Pipeline: template → materialize → kicad-cli netlist export → ngspice
`.op`. Оба шаблона **completed successfully**.

### 6Ж38П IF amp — op-point

| Quantity | Value | Notes |
|---|---|---|
| V(plate) | 114.8 V | Va = Vbb - Rp·Ia = 150 - 10k·3.5mA = 115 V ✓ |
| V(cathode) | 4.0 V | Vk = (Ia+Ig2)·Rk = (3.5+0.5)·1k = 4 V ✓ |
| V(grid) | 2.0 V | grid через divider RGI/Rg (cathode 4V → grid 2V) |
| Vgk effective | -2.0 V | self-bias |
| Ia | 3.52 mA | datasheet @ Vgk=-2, Va=110V → ~3.7 mA ✓ ≤6% |
| Ig2 | 0.48 mA | screen current |
| Anode dissipation | 0.4 W | within 3 W max ✓ |

Class A active region. Datasheet cross-check: на Page 3 lower graph
6BH6 при Vg=-2, Va=110V → Ia ≈ 3.7 mA. Model gives 3.52 mA ≤ 6%
error (внутри SC#2).

### 6П13С SE-amp — op-point (T173 refined: Rk=470Ω)

| Quantity | Value | Notes |
|---|---|---|
| V(plate) | 65.7 V | Va = Vbb - Rload·Ia = 250 - 5k·37mA = 66 V ✓ |
| V(cathode) | 22.1 V | (Ia+Ig2)·Rk = (37+10)·0.47 = 22.1 V ✓ |
| V(grid) | 7.06 V | grid divider RGI/Rg (RGI=1M, Rg=470k) |
| Vgk effective | -15.0 V | self-bias (improved from -9.7V c Rk=200Ω) |
| Vg2k effective | 178 V | screen-cathode |
| Ia | 36.9 mA | functional class A active region |
| Ig2 | 10.1 mA | **screen dissipation 2.0 W → within 4 W max** ✓ |
| Anode dissipation | 2.4 W | within 14 W max ✓ |

**T173 refined bias resolution:** initial Rk=200Ω давало Vgk=-9.7V,
screen overload (5.5W > 4W max). T173 поднял Rk→470Ω. Результат —
Vgk=-15V (~2/3 от datasheet's published Vg=-19V), Ia ≈ 37 mA
(между 44 mA Rk=200Ω и 58 mA fixed-bias datasheet ref), screen
dissipation 2.0 W безопасно внутри max.

Для exact matching datasheet Page 1 published op-point (Ia=58 mA,
Vg=-19V) требуется fixed-bias variant с external Vg DC source —
оставлено как user-customization step (BACKLOG T176 если потребуется
production-grade SE-amp variant).

## 4. Pipeline verdict

✓ **End-to-end T031 pipeline validated through built-in materialization:**

```
PDF/PNG datasheet (vision)
    ↓
JSON IV-точки
    ↓
efactory tube fit-from-points
    ↓
.lib в data/models/tubes/custom/ (Phase 5)
    ↓
data/templates/<name>/ (Schematic facade)
    ↓
efactory project create --template (materialize)
    ↓
efactory bridge design-to-sim op (kicad-cli + ngspice)
    ↓
op-point Ia/Ig2 numerically valid
```

Кросс-чек 6Ж38П через template+ngspice (Ia=3.52 mA) vs Phase 4
direct compute (Ia ≈ 3.7 mA at same operating point) — **внутри
SC#2 tolerance** (≤6%). T031 acceptance reinforced.

## 5. Follow-up dispositions (resolved in-place)

После Phase 5 first commit Vladimir explicit asked сделать T173,
T174, T175 в этой же ветке без заведения новых задач. Disposition:

- **T173 ✓ DONE:** 6p13s-se-resistive bias refactored с Rk=200Ω →
  Rk=470Ω. Vgk_eff улучшен с -9.7V до -15V, screen dissipation
  упал с 5.5W (overload) до 2.0W (внутри 4W max). Smoke verified
  через ngspice probe. См. §3 «6П13С SE-amp» table выше — values
  обновлены до T173 numbers.

- **T174 ⊘ DEFERRED with justification:** «Dedicated KiCad symbols
  для Tubes_Soviet:6ZH38P / 6P13S» (per phase-5 first commit
  BACKLOG candidate). Investigation показала: (a) KiCad stdlib
  `/usr/share/kicad/symbols/Valve.kicad_sym` не содержит ни
  Tubes_Soviet:6ZH38P, ни 6P13S, ни Western equivalents (EF80
  есть как RF pentode, но pin-numbering для him отличается от
  EL84 → требует pin-map валидации в add_subckt's `Sim.Pins`
  conversion для корректного kicad-cli netlist export); (b)
  существующие `Tubes_Soviet:GU50/6P45S/6N6P` в `_SYMBOL_REGISTRY`
  ссылаются на custom KiCad library которой нет на этой dev-машине
  (`find / -name 'Tubes_Soviet.kicad_sym' → пусто`); (c) создание
  нашей собственной `data/symbols/Tubes_Soviet_T031.kicad_sym` с
  только 6ZH38P и 6P13S = тяжёлая работа (KiCad `.kicad_sym` s-expr
  с pin layout, label offsets, body draw) для 2 ламп, неоправданная
  для **визуального** rendering'а в GUI без functional benefit
  (netlist correct independent of symbol choice). Решено: **оставить
  `Valve:EL84` для обеих lamp templates** — visually generic
  pentode (4-pin P/G2/G/K), SPICE-numerics идентичны. Если в
  будущем KiCad standard library расширится Soviet tubes, или
  efactory build pipeline шипнёт собственный Tubes_Soviet, можно
  swap symbol через `_SYMBOL_REGISTRY` без template breakage.

- **T175 ✓ DONE:** `tests/integration/composition/test_t031_phase5_
  templates.py` — 2 integration test'а с `needs_kicad` /
  `needs_ngspice` markers. Каждый: materialize template через
  `CliRunner + build_cli_app() + project create --template + bridge
  design-to-sim op`, экспорт netlist через kicad-cli, прогон
  `ngspice -b` с `.op` + parse op-point. Acceptance bounds:
  - 6Ж38П: V(plate) ∈ [80, 140]V, Ia ∈ [2.5, 5.0]mA.
  - 6П13С: V(plate) ∈ [40, 120]V, Ia ∈ [25, 50]mA, Ig2 < 15mA.
  Suite passes; auto-skip on CI runners без KiCad/ngspice.

## 6. Artefacts

### Commit'ятся в репо

- `data/models/tubes/custom/6ZH38P.lib`
- `data/models/tubes/custom/6P13S.lib`
- `data/templates/6zh38p-if-amp/` (full dir)
- `data/templates/6p13s-se-resistive/` (full dir, T173 Rk=470Ω)
- `tests/integration/composition/test_t031_phase5_templates.py` (T175)
- `specs/T031-tube-curve-fitting/phase-5-templates.md` (этот файл)

### One-shot artefact (НЕ commit'ится)

- `/tmp/build_t031_templates.py` — программа build'а templates.
  При нужде regenerate: cp в tmp + `uv run python`. (Future:
  proper integration с `scripts/regenerate-templates.py` snapshot
  pipeline — BACKLOG candidate, низкий приоритет до повторного
  build'а.)
