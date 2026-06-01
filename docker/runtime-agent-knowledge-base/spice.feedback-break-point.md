---
topic: spice.feedback-break-point
description: Phase-margin break point convention — Middlebrook V на low-Z driver, не high-Z input
tags: [spice, phase-margin, feedback, middlebrook, op-amp, calibration]
---
# Phase-margin break point convention (T153 Phase C.1)

**Правило.** При вызове `/measure-phase-margin <PROJECT>
--loop-break-node <node> --loop-break-element <ref>` (или их CLI
эквивалентов `bridge measure phase-margin`, `bridge edit-and-resim
--measure phase-margin`) выбор `(node, element)` пары зависит от
**типа схемы** и **injection method**:

| Method | Break topology | Op-amp пример | BJT/MOSFET пример |
|---|---|---|---|
| `middlebrook_voltage` (default) | **low-Z driver output** | `(vout, R_fb)` | `(collector, R_C)` / `(drain, R_D)` |
| `middlebrook_current` | **high-Z current-mode input** | (degenerate на op-amp) | `(base, R_B)` / `(gate, R_G)` |
| `tian` (universal) | Любая breakable edge | `(vout, R_fb)` | `(collector, R_C)` |
| `rosenstark_return_ratio` | Passive interconnect с OC/SC-compatible topology | (degenerate на op-amp) | NFB SE tube amp (high-Z grid) |

**Почему.** Middlebrook 1975 single-injection formula `T = -V_rev/V_fwd`
корректно даёт `T_loop` только когда **driver output impedance** в
break-точке << **load input impedance**. На op-amp output:
op-amp output Z (~50 Ω) << R_fb (~10 kΩ) → V-injection работает. На
op-amp input (in_neg) op-amp input Z = ∞ → virtual ground подавляет
signal swing → `T_v ≈ 1/A ≈ 1e-5` (degenerate).

**Источник.** Phase C.1.1 empirical probe (2026-06-01), формализовано
в ADR-T153f. Verification: `tests/integration/application/
test_measure_phase_margin_calibration.py` на op-amp inverting reference
fixture (`data/templates/op-amp-inverting/`, GENERIC_OPAMP_2POLE).

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

**Auto-detect.** После Phase C.1.5 refinement (prev-first preference,
non-ground skip, MIN_CYCLE_LENGTH=2) auto-detect на op-amp inverting
fixture выбирает `(vout, R_fb)` automatically. Default method =
`middlebrook_voltage`, для него driver-side break и нужен.

**Когда auto-detect недостаточен.**

* User хочет Middlebrook I — нужен явный `--loop-break-node <base>
  --loop-break-element <R_B>` (auto-detect не различает per-method).
* Multi-loop circuits (local + global feedback). User выбирает
  loop явно.
* Open-loop amplifier: auto-detect raises
  `AutoDetectConfidenceTooLowError` (parasitic 2-net cycle через
  ground детектится, но низкая confidence). User должен либо признать
  schema open-loop, либо указать break explicitly.

**See also.** ADR-T153a (4 method strategy pattern), ADR-T153b
(NetlistGraphAnalyzer), ADR-T153f (break point convention C.1).
