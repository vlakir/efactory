# active-lpf-sallen-key template

**2nd-order Butterworth low-pass filter** в classic Sallen-Key
voltage-controlled voltage-source (VCVS) topology с unity-gain
op-amp follower (TL072).

## Component values

**Equal-R, unequal-C** (per spec Analyze W1 — exact Butterworth
Q=0.707 требует C1/C2=2 strict, не achievable с equal-C/equal-R):

- R1 = R2 = 10 kΩ (filter resistors)
- C1 = 22 nF (mid → vout feedback path)
- C2 = 11 nF (in_p → GND shunt) — *NOT standard E12, BOM = 10n + 1n parallel*
- R_load = 100 kΩ (assumed next-stage input impedance)
- TL072 op-amp (unity-gain follower: IN- tied to OUT)

## Filter parameters

- **Cutoff f₀** = 1/(2π·R·√(C1·C2)) = 1/(2π·10k·15.56n)
  = **1024 Hz** ≈ 1 kHz
- **Q** = 0.5·√(C1/C2) = 0.5·√2 = **0.707** (Butterworth ideal)
- Rolloff: **-40 dB/decade** above f_c (2nd-order)
- Passband: **unity gain** (0 dB), monotonic (no peaking)

## Топология

```
  Vin ──[R1 10k]──┬──[R2 10k]──┬── IN+ (TL072)
                  │             │
                  C1 22n        C2 11n
                  │             │
                 Vout          GND
                  ↑
                  │
   IN-(TL072) ────┤
                  │
   OUT(TL072) ────┴── Vout ──[R_load 100k]── GND
```

IN- tied to OUT — **unity-gain VCVS** (voltage follower).

## Empirical calibration (ngspice baseline)

| Freq    | Measured rel | Butterworth ideal | Error  |
|---------|--------------|-------------------|--------|
| 10 Hz   | 0.000 dB     | 0.000 dB          | 0.000  |
| 100 Hz  | 0.000 dB     | -0.004 dB         | +0.004 |
| 500 Hz  | -0.240 dB    | -0.281 dB         | +0.041 |
| 1024 Hz | -3.018 dB    | -3.010 dB         | -0.008 |
| 2 kHz   | -11.94 dB    | -12.31 dB         | +0.37  |
| 10 kHz  | -39.62 dB    | -39.74 dB         | +0.12  |

**Perfect Butterworth response — within 0.4 dB across все sweep.**

## TL072 macromodel

`models/TL072.lib` — minimal two-pole macromodel matching TL072
datasheet specs (A0=2e5, GBW=3 MHz, fp1=15 Hz, fp2≈5 MHz,
Rout=200 Ω). T027 Phase D bootstrap. Для high-fidelity
production simulation — заменить на full TI macromodel.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — KiCad-схема.
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project.
- `models/TL072.lib` — op-amp macromodel.

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch

## Рекомендованные measurements

    # Single-point gain @ passband (should be ≈ 0 dB):
    efactory bridge measure gain <PROJECT> \
        --schematic <PROJECT>.kicad_sch --frequency 100 --mode small

    # Bandwidth (-3 dB cutoff verification):
    efactory bridge measure bandwidth <PROJECT> \
        --schematic <PROJECT>.kicad_sch --f-low 10 --f-high 100000
