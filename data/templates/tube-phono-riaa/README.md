# tube-phono-riaa template

Двухкаскадный all-triode phono preamp на 12AX7 (Koren
parametrization, `Valve:ECC83` unit 1 + unit 2 = ECC83B) с
**passive RIAA inter-stage EQ network**:

- **Stage 1 (CC):** R_p1=100 kΩ, R_k1=1.5 kΩ ‖ C_k1=100 µF.
- **C_couple_1:** 470 nF Stage 1 plate → RIAA network input.
- **Passive RIAA inter-stage** (Lipshitz-derived values):
  - R_riaa_1 = 68 kΩ (series)
  - C_riaa_1 = 11 nF (direct shunt to GND, τ3 contribution)
  - R_riaa_2 = 9.1 kΩ (series with C_riaa_2)
  - C_riaa_2 = 33 nF (LF/mid τ2 shunt)
  - R_g2 = 1 MΩ (V1B grid leak — safety reference к GND)
- **Stage 2 (CC):** R_p2=100 kΩ, R_k2=1.5 kΩ ‖ C_k2=100 µF.
- **C_out:** 0.47 µF к assumed 47 kΩ line-amp Rin.

**Mid-band reference gain @ 1 kHz: ≈ 180 V/V (≈ 45 dB)** — для
MM cartridge 5 mV → 900 mV line level.

## RIAA Compliance

Empirical AC sweep (ngspice 44, Koren 12AX7 patched к ngspice
syntax — T027 Phase C), worst error 0.65 dB @ 50 Hz:

| Freq    | Inverse RIAA target | Empirical relative | Error  |
|---------|---------------------|--------------------|--------|
| 20 Hz   | +19.27 dB           | +19.82 dB          | +0.55  |
| 50 Hz   | +16.95 dB           | +17.60 dB          | +0.65  |
| 100 Hz  | +13.09 dB           | +13.52 dB          | +0.43  |
| 200 Hz  | +8.22 dB            | +8.51 dB           | +0.29  |
| 500 Hz  | +2.65 dB            | +2.74 dB           | +0.09  |
| 1 kHz   | 0 dB (reference)    | 0 dB               | 0      |
| 2 kHz   | -2.59 dB            | -2.53 dB           | +0.06  |
| 5 kHz   | -8.22 dB            | -7.99 dB           | +0.23  |
| 10 kHz  | -13.74 dB           | -13.46 dB          | +0.28  |
| 20 kHz  | -19.62 dB           | -19.33 dB          | +0.29  |

**Compliance ±1 dB в 20 Hz – 20 kHz audio band ✓** (per spec §4).

## Lipshitz design math

Для inverse RIAA transfer function `H(s) = (1+sτ2)/((1+sτ1)(1+sτ3))`
на series-shunt topology (R1 series + (R2+C2)‖C1 shunt to GND):

- τ2 = R2·C2 = 318 µs
- τ_X = R1·(C1+C2) = τ1 + τ3 - τ2 = 2937 µs
- τb = R2·C1·C2/(C1+C2) = τ1·τ3/τ_X = 81.2 µs
- Solving: C1/C2 = 0.343, R1 = 66.3 kΩ

E12 nearest values: R1=68k, R2=9.1k, C1=11n, C2=33n. Resulting
effective τ1=3222 µs (target 3180, +1.3%), τ3=69.7 µs (target 75,
-7%). Within ±1 dB compliance budget.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — KiCad-схема.
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project (для GUI Simulator).
- `models/12AX7.lib` — Koren parametrization (ngspice-syntax
  patched T027 Phase C 2026-06-02, original HSPICE `PWRS()` →
  `sgn·pwr·abs` equivalent).

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch

## Рекомендованные measurements

    # Mid-band reference gain (target ≈ 180 V/V = 45 dB):
    efactory bridge measure gain <PROJECT> \
        --schematic <PROJECT>.kicad_sch --frequency 1000 --mode small

    # Bandwidth + RIAA compliance check (AC sweep 20Hz-20kHz):
    efactory bridge measure bandwidth <PROJECT> \
        --schematic <PROJECT>.kicad_sch --f-low 20 --f-high 20000
