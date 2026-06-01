# op-amp-inverting template

Reference inverting-amp фикстура для **calibration** четырёх phase-
margin injection methods (Middlebrook V/I, Tian, Rosenstark) в
рамках T153 Phase C.

## Топология

```
Vin ──[R_in 1k]── in_neg ──┬── INN OPAMP OUT ── vout ──[R_load 1M]── GND
                           │                     │
                           └──[R_fb 10k]─────────┘
INP OPAMP → GND
```

Op-amp model `GENERIC_OPAMP_2POLE` (см. `models/`): A0=1e5,
fp1=10 Hz, fp2≈66 kHz, Rout=50 Ω.

## Analytical reference

* β = R_in / (R_in + R_fb) = 1 / 11
* T_loop_DC = A0 · β ≈ **9091** (79.2 dB)
* Unity-gain crossover `f_c` ≈ **64 kHz**
* **Phase margin ≈ 45°** (± 2° rounding для C2 = 24 pF)

## Файлы

* `{{PROJECT_NAME}}.kicad_sch` — KiCad-схема.
* `{{PROJECT_NAME}}.kicad_pro` — KiCad project (для GUI Simulator).
* `models/GENERIC_OPAMP_2POLE.lib` — SPICE subckt op-amp.

## Phase margin measurement

    # Explicit (правильный break point — на op-amp output side):
    efactory bridge measure phase-margin <PROJECT> \
        --schematic <PROJECT>.kicad_sch \
        --loop-break-node vout --loop-break-element R_fb

Ожидаемый результат: `PM ≈ 45° ± 2°, crossover ≈ 64 kHz ± 5%`.
