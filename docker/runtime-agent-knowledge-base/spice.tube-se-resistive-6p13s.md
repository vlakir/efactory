---
topic: spice.tube-se-resistive-6p13s
description: SE-amp на 6П13С с резистивной нагрузкой 5kΩ вместо OPT (T031 Phase 5 template, A-W3 pattern).
tags: [spice, tube, pentode, tetrode, se-amp, output, 6p13s, resistive, audio]
---
# 6П13С single-ended output amp на резистивной нагрузке

## Когда смотреть в этот topic

- User просит «SE amp на 6П13С», «output stage без OPT», «резистивная
  нагрузка на пентод», «beam tetrode SE без трансформатора».
- `efactory project create` хочет шаблон `6p13s-se-resistive`.
- Smoke-сим output stage без OPT-сложности (A-W3 pattern из T031 spec).

## Что есть в efactory

Шаблон **`6p13s-se-resistive`** (T031 Phase 5, T173 refined bias) —
single-ended output stage на резистивной нагрузке вместо OPT:

- **Tube:** 6П13С — Soviet beam tetrode 14 W Pa, designed для TV
  line scan output. Mu ≈ 6, S = 9.5 mA/V, Vbb max = 450V.
- **Topology:** minimal SE output (no OPT, A-W3 pattern):
  - Vbb = 250 V (anode supply), Vg2 = 200 V (screen, fixed)
  - **Rload = 5 kΩ резистор** (вместо OPT — A-W3 explicit choice)
  - Rk = 470 Ω ‖ Ck = 220 µF (cathode self-bias, T173 refined из
    initial 200 Ω которое давало screen overload)
  - Rg = 470 kΩ (grid leak), Cin = 470 nF
  - Vin: AC ±0.5 V @ 1 kHz default test signal
- **Symbol:** Valve:EL84 (canonical 4-pin pentode P/G2/G/K). Dedicated
  beam tetrode symbol deferred per T174.
- **Default op-point (T175 smoke verified):** V(plate) ≈ 66 V,
  V(cathode) ≈ 22 V, Vgk_eff ≈ −15 V, **Ia ≈ 37 mA**, Ig2 ≈ 10 mA,
  anode dissipation 2.4 W, screen dissipation 2.0 W (внутри 4 W max).

## Почему резистивная нагрузка, не OPT (A-W3)

T031 spec §3 A-W3: для smoke validation Ia op-point и cathode
self-bias достаточно резистивной нагрузки. OPT добавляет:
- reactive impedance свыше DC R → AC sweep complication;
- saturation modeling (T007 transformer machinery) → лишний
  dependency для simple op-point check.

Резистивный nullload (R = 5-10 kΩ) даёт ту же DC op-point оценку
без OPT complexity. Идеален для:
- Fit-validation tube model;
- Cathode bias engineering iteration;
- Static class A bias sanity check.

**Не идеален для:**
- Real audio amp design — OPT match impedance + reactive load
  shape для output power. Для production audio см. `se-amp`
  (6П14П + 5k:8Ω OPT) или `nfb-se-amp` (with global NFB).

## T173 bias refinement

Initial template (Phase 5 first commit) использовал Rk=200Ω →
self-bias Vgk_eff=−9.7V → tube conducts больше чем оптимум →
screen dissipation 5.5W (overload, > 4W max).

T173 fix: Rk=470Ω → Vgk_eff=−15V → Ia=37 mA, Ig2=10 mA, screen
dissipation 2.0W (внутри bounds).

Exact-match published Page 1 op-point (Vg=-19V → Ia=58mA) требует
fixed-bias external Vg DC source — оставлено user customization.

## Model provenance

`data/models/tubes/custom/6P13S.lib` — fitted T031 Phase 4 на pocnet
6П13С datasheet Page 3 left graph (Vg2=150V). Fit RMS 21.5 mA на 19
IV-точках (~10% relative); control mean 4.5%, max 6.2% — внутри SC#2.

Header `tube_type: tetrode` (A-W1) — fitted под единый pentode mode,
header выбирается CLI флагом `--header-type tetrode`.

## См. также

- `tubes.curve-fitting` — T031 pipeline rationale, KG2 fallback.
- `specs/T031-tube-curve-fitting/phase-5-templates.md` §3 — full
  op-point verification + T173 refinement notes.
- `data/templates/6zh38p-if-amp/` — small-signal preamp аналог.
- `data/templates/se-amp/` — production-grade SE с OPT на 6П14П.
