---
topic: spice.tube-push-pull
description: Топология tube PP amp — LTP splitter, center-tap OPT, проектные ловушки (T027 Phase A)
tags: [spice, tube, push-pull, opt, ltp, concertina, audio]
---
# Tube push-pull power amp — design discipline

## Когда смотреть в этот topic

- User просит «ламповый PP», «push-pull amp», «двухтактный усилитель»,
  «PP на 6П14П / EL84 / KT88».
- `efactory project create` хочет шаблон `tube-pp-amp`.
- Появилась задача расширить open-loop PP NFB-обвязкой, или разобраться
  с calibration drift.

## Что есть в efactory

Шаблон **`tube-pp-amp`** (T027 Phase A) — open-loop fixture:
- **Phase splitter:** long-tail-pair (LTP) на обеих половинах 6Н2П
  (Valve:ECC83 unit 1 + unit 2 = ECC83B). R_p1A = R_p1B = 47 kΩ,
  R_tail = 4.7 kΩ shared cathode.
- **Output stage:** пара 6П14П (Valve:EL84) в push-pull, per-tube
  auto-bias R_k = 270 Ω ‖ C_k = 220 µF.
- **OPT:** `OPT_PP_6K6_8.lib` (6.6 kΩ p-p : 8 Ω, center-tapped primary
  P1/PC/P2). Symbol — custom `Device:Transformer_2P_1S` (T027 Phase A
  расширил `_SYMBOL_REGISTRY` facade'а).
- **Calibration baseline:** |A_v| @ 1 kHz mid-band ≈ **16.5 V/V (24.4 dB)**.

## ADR-T027a — phase splitter: LTP, не concertina

Spec Round 2 Q3 изначально одобрил concertina (split-load) на одной
половине 6Н2П (Ra=Rk=47 kΩ, без катодного bypass) как «простейший
splitter, 1 tube, perfect AC balance». **Empirical-валидация на
Koren-style 6N2P model показала**, что equal-resistance concertina:

- biases tube near cutoff (I_a quiescent ≈ 0.15 mA, V_GK ≈ -3.3 V);
- plate-output gain атрофирует до ≈ 0.05 V/V (вместо ожидаемого ~1);
- cathode-output gain ≈ 0.92 V/V (cathode-follower работает, plate-
  output нет);
- PP transformer драйвится только single-ended (от cathode-output),
  итоговый mid-band gain ≈ **0.77 V/V** (24 dB **затухания**).

**Concertina с grid voltage divider** (pull-up grid bias через R_top
от B+) теоретически решает bias point, но добавляет 3 компонента и
parameter sensitivity (V_grid_bias drift при tolerance R_top/R_bot).

**LTP — textbook standard** для tube PP (Williamson 1947, Marshall
Plexi PI, Hammond DAW). Использует обе половины double-triode, shared
cathode через R_tail к GND. Differential drive обоих 6П14П anti-phase.
Robust к 6Н2П model parameter drift, не требует grid voltage divider.

**Trade-off acknowledged:** LTP добавляет +1 6Н2П половину + 1
резистор (R_tail вместо R_k1 concertina) + 1 grid leak R_g1B. Total
component count +2 vs concertina. Acceptable для starter template.

## Pitfalls + design discipline

### Center-tap OPT routing

`OPT_PP_6K6_8` имеет 5 SUBCKT pins (`P1 PC P2 S1 S2`), отличается от
SE OPT (4 pins `P1 P2 S1 S2`). **PC (primary center-tap) ОБЯЗАТЕЛЬНО**
roуted к B+ rail — это DC supply path для обеих outputs.

В efactory facade — symbol `Device:Transformer_2P_1S` (custom, T027
Phase A). См. `src/adapters/outbound/schematic_kicad/lib_symbols/
Device.Transformer_2P_1S.sexp` и registry в `facade.py`. Маппинг
KiCad pin → SUBCKT name: pin 1=P1 (top primary), 2=PC (center), 3=P2
(bottom primary), 4=S1, 5=S2.

Если OPT.PC окажется не на B+ rail — output tubes не получают DC supply,
amp не conducts. Acceptance test `test_facade_tube_pp_amp_topology` ловит
это явным assertion `pc_net == bplus_net`.

### LTP cathode rail vs grid-leak GND placement

Subtle layout bug, всплыл в T027 Phase A iteration 2: GND symbol для
R_g1B (placed @ X=99.06, Y=101.6) **попадал ровно на cathode rail**
(Y=101.6 — общий cathode wire V1A.K + V1B.K). Результат: R_tail.pin_b
и cathode-of-tubes шортятся к GND через GND symbol's pin. Splitter
не conducts.

**Правило:** GND symbols для grid-leak resistors **не должны лежать
на Y-координате shared cathode rail**. Использовать Y=99.06 (между
resistor.pin_a Y=97.79 и rail Y=101.6) или другую безопасную Y.

### 6П14П в PP vs SE

В PP topology 6П14П **biased на higher V_a** (близко к B+, ~300 V) чем
в SE (~250 V после plate-load drop). Quiescent V_a ≈ B+ - I_a·R_DCR_OPT
(per-half DCR ≈ 120 Ω · 30 mA ≈ 4 V drop). При V_a=300V и V_GK=-7V,
I_a ≈ 30-40 mA per tube, dissipation ≈ 10-12 W (близко к 6П14П max
12 W class A).

**Не использовать SE OPT для PP** — `OPT_SE_5K_8` (4 pins, no center-
tap) физически не подходит. Будут shorts plate↔B+ direct.

### Open-loop vs NFB

T027 Phase A — **open-loop** (без global NFB). NFB-вариант (по аналогии
с `nfb-se-amp`) — отдельная T-задача в BACKLOG. Реализация global
voltage NFB на PP: ставить feedback path от OPT.S1 (sec_a) обратно к
splitter input (V1A.K через C_fb + R_fb DC-block). Loop-break point —
канонический `(sec_a, C_fb)` per ADR-T153g (см. KB
`spice.feedback-break-point`).

## Reference

- `tests/integration/adapters/schematic_kicad/test_tube_pp_amp_facade.py`
  — builder + acceptance tests (model includes, topology, OP-point).
- `tests/integration/application/test_measure_gain_calibration_tube_pp_amp.py`
  — mid-band Av calibration regression (±15% от baseline 16.5 V/V).
- `data/templates/tube-pp-amp/` — materialized template (README, schema,
  models).
- `scripts/regenerate-templates.py::_bake_tube_pp_amp` — bake-hook.
