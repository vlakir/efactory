---
topic: spice.tube-line-preamp
description: Двухкаскадный all-triode line preamp на 6Н2П (CC + CF cascade) — T027 Phase B
tags: [spice, tube, preamp, cathode-follower, common-cathode, audio, 6n2p, ecc83]
---
# Tube line preamp — CC + CF cascade design

## Когда смотреть в этот topic

- User просит «ламповый preamp», «line preamp», «6Н2П preamp», «ECC83
  buffer / line stage».
- `efactory project create` хочет шаблон `tube-line-preamp`.
- Появилась задача добавить tone stack, NFB, или EQ network к baseline
  CC+CF cascade.

## Что есть в efactory

Шаблон **`tube-line-preamp`** (T027 Phase B) — двухкаскадный fixture:
- **Stage 1 (CC voltage amp):** V1A = ECC83 unit 1 (одна половина 6Н2П),
  R_p1=100 kΩ, R_k1=1.5 kΩ ‖ C_k1=22 µF bypass auto-bias, C_in=100 nF.
- **Stage 1-2 coupling:** C_couple=47 nF.
- **Stage 2 (CF cathode follower):** V1B = ECC83 unit 2 (= ECC83B, та
  же лампа, вторая половина), V1B.P → directly к B+ (NO plate load),
  R_k2=33 kΩ cathode load **без bypass**, C_out=0.47 µF к assumed
  100 kΩ next-stage load.
- **Calibration baseline:** |A_v| @ 1 kHz mid-band ≈ **64 V/V (36 dB)**.
- **Output Z (CF advantage):** ≈ r_a/(μ+1) ≈ 800 Ω (low — драйвит
  кабель + power amp grid leak без HF roll-off).

## Pitfalls + design discipline

### CF defining property — NO plate load

**Cathode Follower** (CF, common-anode topology) — V1B.P должен быть
**directly connected к B+ rail без plate-load resistor**. Это NOT
bug — это defining feature CF stage. AC signal output is taken **от
cathode**, not plate.

Если ошибочно добавить R_p2 (plate load на V1B), то схема превращается
в two-stage CC (CC + CC) — gain выше, но output Z тоже выше (тот же
порядок как Stage 1, ~100 kΩ instead of ~800 Ω). Теряется CF advantage.

Acceptance test `test_facade_tube_line_preamp_topology` явно проверяет
что V1B.P node = B+ rail node в netlist.

### CF cathode resistor R_k — NO bypass

R_k2 (cathode load of CF) **без C_k bypass cap** — это **intentional
design**. CF inherently degenerative — exactly это и даёт CF свойства:
- gain ≈ 1 (slightly less);
- low output impedance;
- low distortion (high local NFB via 100% cathode degeneration).

Если по ошибке добавить C_k2 bypass — CF превращается в "leaky-cathode
buffer" с gain > 1, but теряется output impedance benefit и distortion
suppression.

### R_k2 choice — высокое значение для high impedance load

R_k2 = 33 kΩ выбран как **трade-off**:
- слишком маленький R_k → CF не достигает gain ≈ 1 (μ·R_k не >> r_a);
- слишком большой R_k → Q-point V_GK shifts слишком позитивно → tube
  saturation.

R_k2 = 33 kΩ при I_a ≈ 1 mA даёт V_K ≈ 33 V, V_GK ≈ -V_K + V_grid_DC =
-33 + ~30 = ~-3V (плюс some drift through capacitor coupling). Active
region OK.

### Output coupling cap value

C_out = 0.47 µF coupled to 100 kΩ assumed load:
- f_HP_corner = 1/(2π·R·C) = 1/(2π·100k·0.47µ) ≈ 3.4 Hz.
- Вне audio band (>20 Hz), no LF roll-off issue.

Альтернативы (parked):
- 1.0 µF (даже больше LF margin, но physically крупнее cap).
- 0.1 µF (corner @ 16 Hz — на границе audio band, riskier).

## Mid-band gain — analytical vs empirical

**Analytical hand-calc:**
- Stage 1 (CC) gain ≈ μ·R_p / (R_p + r_a) = 100·100/(100+80) ≈ 55 V/V.
- Stage 2 (CF) gain ≈ +(μ+1)·R_k / ((μ+1)·R_k + R_p + r_a) ≈ 0.98.
- Total ≈ 55 · 0.98 ≈ 54 V/V (≈ 34.6 dB).

**Ngspice empirical:** 64 V/V (36 dB) — на 16% выше analytical.
Причина: Koren-style 6Н2П model даёт g_m_eff выше nominal datasheet
g_m=1.6 mA/V при typical bias point (V_a≈150V, I_a≈1mA). Acceptable
в model parameter uncertainty.

**Calibration regression** test fails if drift > ±15% от 64 V/V
baseline.

## Reference

- `tests/integration/adapters/schematic_kicad/test_tube_line_preamp_facade.py`
  — builder + 3 acceptance tests (model includes, topology, OP-point).
- `tests/integration/application/test_measure_gain_calibration_tube_line_preamp.py`
  — mid-band Av calibration regression (±15% от baseline 64 V/V).
- `data/templates/tube-line-preamp/` — materialized template (README,
  schema, model 6N2P.lib).
- `scripts/regenerate-templates.py::_bake_tube_line_preamp` — bake-hook.
