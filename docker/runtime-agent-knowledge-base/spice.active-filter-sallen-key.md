---
topic: spice.active-filter-sallen-key
description: Sallen-Key 2nd-order active filter design (Butterworth Q=0.707) — T027 Phase D
tags: [spice, opamp, sallen-key, active-filter, butterworth, vcvs, low-pass, audio]
---
# Active Sallen-Key 2nd-order filter — design discipline

## Когда смотреть в этот topic

- User просит «active filter», «Sallen-Key», «low-pass filter», «LPF»,
  «activated filter», «op-amp filter».
- `efactory project create` хочет шаблон `active-lpf-sallen-key`.
- Появилась задача добавить high-pass, band-pass или high-order
  (cascaded) variants.

## Что есть в efactory

Шаблон **`active-lpf-sallen-key`** (T027 Phase D) — 2nd-order
Butterworth low-pass filter в classic Sallen-Key voltage-controlled
voltage-source (VCVS) topology с unity-gain TL072 op-amp follower.

- **R1 = R2 = 10 kΩ** (equal-R filter resistors).
- **C1 = 22 nF** (mid → vout feedback path).
- **C2 = 11 nF** (in_p → GND shunt) — **NOT standard E12**, BOM
  realization: 10n + 1n parallel film caps.
- **R_load = 100 kΩ** (high-Z next-stage input — minimal loading на
  op-amp output).
- TL072 op-amp (unity-gain follower: IN- tied to OUT).

**Filter parameters:**
- f₀ = 1/(2π·R·√(C1·C2)) = **1024 Hz** (≈ 1 kHz target).
- Q = 0.5·√(C1/C2) = **0.707** (Butterworth ideal).
- Rolloff -40 dB/decade above f_c.
- Passband unity gain, monotonic (no peaking).

**TL072 macromodel** bootstrap'нут в Phase D (`data/models/opamps/
generic/TL072.lib`): A0=2e5, GBW=3 MHz, fp1=15 Hz, fp2≈5 MHz,
Rout=200 Ω.

## ADR-T027d: equal-R unequal-C choice (Analyze W1)

Spec Round 2 Q10 (одобрено Vladimir) suggested **equal-R/equal-C**
choice (R=10kΩ, C=15.9nF):
- f_c = 1/(2π·R·C) = 1001 Hz ≈ 1 kHz ✓
- **НО:** classic Sallen-Key с unity-gain VCVS + equal-R/equal-C
  gives Q=0.5 (overdamped), **не** Butterworth Q=0.707.

Phase D Analyze W1 (Гвидо self-review) noted incompatibility:
- For Q=0.707 (Butterworth), нужно **либо** unity gain VCVS с
  **unequal C** (C1=2·C2 strict), **либо** equal-R/equal-C с
  **non-unity gain VCVS** (K=1.586 для Butterworth).

**Choice (Phase D Section 2):** equal-R, **unequal-C** (C1=2·C2).
Rationale:
- Simpler topology (unity-gain follower, no additional resistors для
  gain set).
- Robust к op-amp non-idealities (less gain-bandwidth pressure).
- BOM cost: 1 extra cap pair (10n + 1n parallel = 11nF) vs alternative
  K=1.586 needs 2 extra precision resistors.

**Trade-off:** C2=11nF не E12 standard. Production BOM uses
**10nF + 1nF film cap parallel** (E12 both, ±2% tolerance achievable).

## Pitfalls + design discipline

### Sallen-Key Q formula sanity check

Для Sallen-Key low-pass unity-gain VCVS с equal-R:

```
H(s) = 1/(1 + 2sRC2 + s²·R²·C1·C2)
```

→ ω₀ = 1/(R·√(C1·C2)),  Q = 0.5·√(C1/C2)

**Common mistake:** assume Q=0.707 для equal-R/equal-C. **Wrong** —
that gives Q=0.5. For Butterworth need C1/C2=2.

### Op-amp GBW требование

Filter f_c должна быть **≪ op-amp GBW** для clean filter response.
Phase D: TL072 GBW=3 MHz, f_c=1 kHz → ratio 3000× — plenty of margin,
filter behaves ideally.

**При GBW недостаточном** (например GBW < 100×f_c) op-amp gain
rolloff intermingles с filter rolloff — shifts effective f_c lower,
ломает Q. Phase D iteration 2 hit this: initial macromodel имел
typo `C1 53.05u` (instead of `53.05n`) — actual GBW=3 kHz, не 3 MHz.
Filter shifted f_c=1024Hz → -3dB at 889 Hz (-13%). Fixed C1 → exact
Butterworth restored.

### Component tolerance impact (production BOM)

Calibration test uses **ideal nominal values** в ngspice netlist.
Real-world components:
- Resistor ±5% (E96 1% available) → ±5% drift в f_c.
- Film cap ±2% (polypropylene MKP) → ±2% drift в f_c, ±5% in Q.
- 10n + 1n parallel (для C2=11n) → 11n ±10% если оба ±5%.

Real-world ±10% tolerance в f_c, ±10-15% в Q. Strict ±10% spec
calibration achievable только с 1% resistors + 2% film caps.

### R_load loading effect

При R_load слишком низком (e.g., 10kΩ) loaded op-amp output → finite
output impedance dominantly attenuates **higher** frequencies, shifting
f_c down. Phase D iteration 1 hit this: R_load=10kΩ → -3 dB at 889 Hz
(13% off analytical 1024 Hz). Fix: R_load=100kΩ (typical high-Z load
для next stage).

**Rule of thumb:** R_load ≥ 10× max(R1, R2) для negligible loading.

### Higher-order LPF (cascaded Sallen-Key)

For Butterworth 4th-order (cascaded 2× Sallen-Key sections), Q values
differ per section:
- Stage 1: Q1 = 0.541 → C1/C2 = (2·0.541)² = 1.171
- Stage 2: Q2 = 1.307 → C1/C2 = (2·1.307)² = 6.83

Each section has its own component values. Spec Round 2 explicitly
out-of-scope для Phase D (only 2nd-order single section).

## Reference

- `tests/integration/adapters/schematic_kicad/test_active_lpf_sallen_key_facade.py`
  — builder + 2 acceptance tests (model includes, topology +
  unity-gain VCVS verification).
- `tests/integration/application/test_measure_gain_calibration_active_lpf_sallen_key.py`
  — Sallen-Key calibration regression (3 tests: passband unity,
  -3 dB at f_c ±10%, monotonic Butterworth Q=0.707).
- `data/templates/active-lpf-sallen-key/` — materialized template
  (README с empirical calibration table, schema, TL072 macromodel).
- `data/models/opamps/generic/TL072.lib` — bootstrap TL072 macromodel
  (T027 Phase D).
- `scripts/regenerate-templates.py::_bake_active_lpf_sallen_key` —
  bake-hook.
