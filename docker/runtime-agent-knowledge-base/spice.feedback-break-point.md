---
topic: spice.feedback-break-point
description: Phase-margin break point convention — per-topology × per-method matrix (op-amp, tube NFB, BJT)
tags: [spice, phase-margin, feedback, middlebrook, tian, rosenstark, op-amp, tube, calibration]
---
# Phase-margin break point convention (T153 Phase C.1 + C.3)

**Правило.** При вызове `/measure-phase-margin <PROJECT>
--loop-break-node <node> --loop-break-element <ref>` (или их CLI
эквивалентов `bridge measure phase-margin`, `bridge edit-and-resim
--measure phase-margin`) выбор `(node, element)` пары зависит от
**типа схемы** и **injection method**.

## Per-topology × per-method applicability matrix (empirical)

| Topology              | V  | I  | Tian | Rosenstark | Canonical break point         |
|-----------------------|----|----|------|------------|-------------------------------|
| Op-amp inverting NFB  | ✓  | ✗  | ✓    | ✗          | `(vout, R_fb)` — low-Z output |
| Tube SE NFB           | ✓  | ✗  | ✗    | ✗          | `(sec_a, C_fb)` — OPT sec     |
| BJT CE NFB            | ?  | ?  | ?    | ?          | (future calibration fixture)  |

- ✓ = strict validation (PM within ±5° expected); use confidently.
- ✗ = empirically degenerate (NoUnityGainCrossover / always-above-unity /
  PM out-of-range); use Middlebrook V instead.
- ? = not yet calibrated; use V as default, validate manually.

## Per-method physics

**Middlebrook V** (`T = -V_rev/V_fwd`, default) — корректно даёт
`T_loop` когда break — на **low-Z driver** стороне: driver output
impedance в break-точке << load input impedance. Низко-импедансные
break points:
* op-amp output (Z ~50 Ω) → R_fb (Z ~10 kΩ).
* OPT secondary (Z ~8 Ω) → C_fb/R_fb feedback chain (Z ~kΩ).
* BJT collector (Z ~kΩ) → R_C (Z ~10 kΩ).

**Middlebrook I** требует current-mode break (BJT base, MOSFET gate).
Tubes имеют нулевой grid current → I-injection не возбуждает forward
loop на tube circuits. На op-amp output break impedance ratio
reversed → degenerate.

**Tian** (`T = (T_v·T_i − 1) / (T_v + T_i + 2)`) — universal claim
holds только когда T_v и T_i одновременно well-defined на одном
break. Op-amp output break удовлетворяет; tube NFB at OPT secondary
— нет (I degenerate → Tian degenerate).

**Rosenstark** (`T = (T_oc·T_sc + T_oc + T_sc) / (T_oc·T_sc − 1)`)
требует bidirectional two-port OC/SC compatible break. Tube
unilateral (plate ≠ generator of feedback signal) → нет такого
break point на NFB SE. Op-amp low-Z output dominates pulldown /
short → degenerate `T = 1`.

## Tube NFB amplifier ОБЯЗАТЕЛЬНО требует explicit break

Auto-detect heuristic на multi-loop tube topology (local cathode
degeneration + global NFB через OPT) детектится ~72 cycles, все
confidence < 0.5 (best candidate sec_b/R_load — load junction, не
feedback!) → `AutoDetectConfidenceTooLowError` на default threshold
0.8. **User должен передать break explicitly:**

```
# Tube NFB SE — canonical break (sec_a, C_fb)
bridge measure phase-margin nfb-se-amp/<sch> \
    --loop-break-node sec_a --loop-break-element C_fb
# → PM ≈ 115°, crossover ≈ 47.5 kHz (very stable outer NFB loop)
```

PM=115° на NFB SE отражает **global NFB outer loop stability** —
сильное демпфирование, типичное для tube NFB amps с консервативным
дизайном. Local cathode degeneration (R_k1 unbypassed) добавляет
дополнительный stability margin к global loop.

## Op-amp inverting amplifier — auto-detect работает после C.1.5

Auto-detect выбирает `(vout, R_fb)` automatically (prev-first
preference + non-ground skip + MIN_CYCLE_LENGTH=2). Default method
= `middlebrook_voltage`, для него driver-side break и нужен.

**Anti-pattern.**

```
# WRONG: break на op-amp input (in_neg) — degenerate T_v
bridge measure phase-margin op-amp-inverting/<sch> \
    --loop-break-node in_neg --loop-break-element R_fb
# → NoUnityGainCrossoverError или PM ≈ 0° (физически бессмысленно)
```

**Правильно.**

```
# RIGHT: break на op-amp output (vout) — driver low-Z side
bridge measure phase-margin op-amp-inverting/<sch> \
    --loop-break-node vout --loop-break-element R_fb
# → PM ≈ 45°, crossover ≈ 64 kHz (для GENERIC_OPAMP_2POLE)
```

## Источники

* C.1 op-amp empirical probe (2026-06-01) — ADR-T153f + tests/
  integration/application/test_measure_phase_margin_calibration.py.
* C.3 tube NFB empirical probe (2026-06-01) — ADR-T153g + tests/
  integration/application/test_measure_phase_margin_calibration_nfb_se.py.

## See also

ADR-T153a (4 method strategy pattern), ADR-T153b (NetlistGraphAnalyzer),
ADR-T153f (op-amp break convention), ADR-T153g (per-topology matrix +
tube NFB calibration).
