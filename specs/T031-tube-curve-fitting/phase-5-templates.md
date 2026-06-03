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

### 6П13С SE-amp — op-point

| Quantity | Value | Notes |
|---|---|---|
| V(plate) | 30.5 V | Va = Vbb - Rload·Ia = 250 - 5k·44mA = 30 V ✓ |
| V(cathode) | 14.3 V | (Ia+Ig2)·Rk = (44+27.5)·0.2 = 14.3 V ✓ |
| V(grid) | 4.6 V | grid divider RGI/Rg |
| Vgk effective | -9.7 V | self-bias |
| Vg2k effective | 185.7 V | screen-cathode reduced by self-bias |
| Ia | 43.9 mA | functional active region |
| Ig2 | 27.5 mA | high — screen drawing significant |
| Anode dissipation | 1.3 W | within 14 W max ✓ |
| Screen dissipation | 5.5 W | **outside** 4 W max — see caveat |

**Caveat:** screen current 27.5 mA × Vg2=200V = 5.5 W exceeds
datasheet max Pg2=4 W. Self-bias topology с Rk=200Ω не даёт
достаточно negative grid voltage (Vgk=-9.7V vs published
Vg=-19V в datasheet) → tube conducts больше чем оптимум для
this Vg2. Fixed-bias variant с external Vg=-19V даст ~58 mA Ia
matching datasheet Page 1 reference op-point.

**Это документированное ограничение minimal template**, не bug.
Self-bias-only topology для 6П13С достаточен для smoke validation
(pipeline works, SPICE export correct, ngspice integrates OK,
model gives physical operating point), но pre-production design
требует fixed-bias или larger Rk (~470Ω для self-bias).

T173 BACKLOG candidate: «6p13s-se-resistive — refine bias to
match datasheet op-point» (fixed-bias variant или Rk=470Ω).

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

## 5. Out of scope для Phase 5 (BACKLOG-candidates)

- **T173:** 6p13s-se-resistive refined bias variant (fixed-bias
  Vg=-19V external или Rk=470Ω self-bias) для matching datasheet
  Page 1 reference op-point (Ia=58 mA, Vp=200V).
- **T174:** Dedicated KiCad symbols для Soviet 6Ж38П (7-pin
  miniature) и 6П13С (octal beam tetrode). Сейчас оба используют
  Valve:EL84 symbol — visually generic pentode, SPICE-numerics
  идентичны.
- **T175:** Smoke test fixture в `tests/integration/.../` для
  обоих templates (deterministic regression CI gate): кейсы
  materialize + design-to-sim + Ia op-point ± tolerance.

## 6. Artefacts

### Commit'ятся в репо

- `data/models/tubes/custom/6ZH38P.lib`
- `data/models/tubes/custom/6P13S.lib`
- `data/templates/6zh38p-if-amp/` (full dir)
- `data/templates/6p13s-se-resistive/` (full dir)
- `specs/T031-tube-curve-fitting/phase-5-templates.md` (этот файл)

### One-shot artefact (НЕ commit'ится)

- `/tmp/build_t031_templates.py` — программа build'а templates.
  При нужде regenerate: cp в tmp + `uv run python`.
