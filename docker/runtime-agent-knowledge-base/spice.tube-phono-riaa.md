---
topic: spice.tube-phono-riaa
description: 12AX7 phono preamp с passive RIAA inter-stage EQ (Lipshitz design) — T027 Phase C
tags: [spice, tube, phono, riaa, equalizer, passive, lipshitz, mm-cartridge, koren, audio]
---
# Tube phono preamp с passive RIAA — design discipline

## Когда смотреть в этот topic

- User просит «phono preamp», «RIAA preamp», «винил preamp», «MM
  cartridge amp», «12AX7 phono».
- `efactory project create` хочет шаблон `tube-phono-riaa`.
- Появилась задача добавить MC head amp, custom RIAA modification, или
  оптимизировать compliance.

## Что есть в efactory

Шаблон **`tube-phono-riaa`** (T027 Phase C) — двухкаскадный all-triode
fixture с **passive RIAA inter-stage**:

- **Stage 1 (CC, 12AX7 unit 1):** R_p=100 kΩ, R_k=1.5 kΩ ‖ C_k=100 µF.
- **C_couple_1:** 470 nF (Stage 1 plate → RIAA network input).
- **Passive RIAA inter-stage (Lipshitz-derived):**
  - R_riaa_1 = 68 kΩ (series)
  - C_riaa_1 = 11 nF (HF τ3 contribution)
  - R_riaa_2 = 9.1 kΩ
  - C_riaa_2 = 33 nF
  - R_g2 = 1 MΩ grid leak (safety reference)
- **Stage 2 (CC, 12AX7 unit 2):** R_p=100 kΩ, R_k=1.5 kΩ ‖ C_k=100 µF.
- **C_out:** 0.47 µF к assumed 47 kΩ line-amp input.

**Mid-band reference gain @ 1 kHz: ≈ 180 V/V (45 dB)** — MM cartridge
5 mV → 900 mV line level.

**RIAA compliance @ 20 Hz – 20 kHz: ±1 dB** (worst 0.65 dB @ 50 Hz).

## ADR-T027c: Koren 12AX7 model ngspice-syntax patch

Original Koren 12AX7.lib (и все 15 Koren tube models в efactory)
содержал `PWRS()` — HSPICE convention. **ngspice 44 не поддерживает
PWRS** (вернёт `Error: no such function 'pwrs'`).

Phase C первое реальное использование Koren tube model в ngspice
simulation (раньше использовались только `custom/6N2P.lib`,
`custom/6P14P.lib`, которые имели ngspice-compatible `sgn·pwr·abs`
syntax). Bug surfaced.

**Fix:** все 15 Koren models patched к syntax-equivalent:
```
PWRS(x, y)  →  sgn(x)*pwr(abs(x),y)
```

Functionally identical для V(7) > 0 (tube conducting region).
См. `data/models/tubes/koren/*.lib` git history T027 Phase C 2026-06-02.

**Spec Q6 rationale revision:** initial Vladimir's reasoning for
choosing 12AX7 Koren over custom 6N2P («Koren модель точнее на AC
sweep») was based on incorrect assumption. **12AX7.lib и custom
6N2P.lib используют identical Koren parameters** (`MU=100 EX=1.4
KG1=1060 KP=600 KVB=300`) — functionally same model, только syntax
(один работал, другой broken). Choice 12AX7 retained per textbook
convention (Morgan Jones / Allen Wright phono designs reference
12AX7/ECC83 explicitly).

## Pitfalls + design discipline

### Lipshitz design constraints для passive RIAA inter-stage

Для inverse RIAA transfer function:
```
H(s) = (1 + sτ2) / ((1 + sτ1)(1 + sτ3))
```
с canonical time constants τ1=3180 µs, τ2=318 µs, τ3=75 µs.

В series-shunt topology (R1 series + Z_shunt parallel к GND, где
Z_shunt = (R2+C2) ‖ C1):

- **τ2 = R2·C2** — direct mapping.
- **τ_X = R1·(C1+C2) = τ1 + τ3 - τ2 = 2937 µs.**
- **τb = R2·C1·C2/(C1+C2) = τ1·τ3/τ_X = 81.2 µs.**

Solving system:
- C1/C2 = 0.343 (Lipshitz cross-coupling ratio).
- C2 chosen (e.g., 33 nF E12) → C1 = 11 nF.
- R2 = τ2/C2 = 9.6 kΩ ≈ 9.1 kΩ (E12).
- R1 = τ_X/(C1+C2) = 66 kΩ ≈ 68 kΩ (E12).

**Common pitfall:** **«Reference values из textbook»** часто рассчитаны
для **другой topology** (e.g., 2-stage cascade с buffer). Reference book
saying «R1=91k C1=820p R2=9.1k C2=33n» от "Practical Audio Tube Preamps"
in Phase C iteration 1 gave **-16 dB error @ 20 kHz** because
relationship C1/C2 = 0.025 (not 0.343) — wrong topology constraint.

**Always re-derive Lipshitz constraints для exact topology** before
choosing values.

### LF rolloff — несколько источников

20 Hz RIAA boost compliance требует:
- C_couple cap достаточно large (≥ 470 nF, корнер < 5 Hz). 100 nF → -2 dB @ 20 Hz LF deficit.
- Cathode bypass caps C_k достаточно large (≥ 100 µF). 22 µF → ~1.5 dB Stage 1 LF gain droop @ 20 Hz.

В Phase C iteration 1 mistakes: C_k1/C_k2 были 22 µF, C_couple 100 nF
— total LF deficit ~3 dB @ 20 Hz. Fix: bump к 100 µF + 470 nF.

### MM cartridge level

Шаблон assumes MM cartridge: input 5 mV @ 1 kHz nominal. Output
≈ 900 mV ≈ line level.

**Для MC (moving coil) cartridge** (typical 0.2-0.5 mV output) — нужен
**отдельный head amplifier OR step-up transformer** (SUT) перед этим
preamp. Не в scope tube-phono-riaa. Парковать в BACKLOG как отдельный
T-task.

### RIAA compliance vs component tolerance

Calibration test использует **ideal nominal values** в ngspice
netlist. Реальные компоненты:
- Resistors ±5% → ±0.4 dB drift в τ1 (50 Hz knee).
- Ceramic caps ±10% → ±0.8 dB drift в τ2 (500 Hz knee), τ3 (2122 Hz knee).

Real-world ±1 dB compliance требует:
- 1% (E96) resistors.
- Polypropylene/silver mica caps ±2-5%.
- Possibly trim cap для τ3 calibration.

Component sensitivity analysis — отдельная задача (T029+), не Phase C scope.

## Reference

- `tests/integration/adapters/schematic_kicad/test_tube_phono_riaa_facade.py`
  — builder + 3 acceptance tests (model includes, RIAA components,
  OP-point).
- `tests/integration/application/test_measure_gain_calibration_tube_phono_riaa.py`
  — RIAA compliance calibration regression (10-point AC sweep vs
  inverse RIAA, ±1 dB tolerance).
- `data/templates/tube-phono-riaa/` — materialized template (README
  с RIAA compliance table, schema, patched 12AX7.lib).
- `scripts/regenerate-templates.py::_bake_tube_phono_riaa` — bake-hook.
- `data/models/tubes/koren/*.lib` — all 15 Koren models patched
  (T027 Phase C, PWRS → sgn·pwr·abs).
