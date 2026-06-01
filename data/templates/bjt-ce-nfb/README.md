# bjt-ce-nfb template

Single-stage common-emitter NPN amp (2N3904) с voltage-divider
bias (R_B1=100k / R_B2=10k), emitter degeneration (R_E=470Ω +
C_E=47µF bypass), и shunt-shunt AC-only feedback (R_F=47kΩ +
C_F=1µF DC-block, collector→base). Reference fixture для **T153
phase-margin 4-method calibration matrix** (ADR-T153g BJT CE row).

## Топология

```
Vin ──[R_S 50]── C_in ──┬── base
                        │           Q1 (2N3904)
         V_CC ──[R_B1 100k]┤    B          C ── vout
                       R_B2 10k        E
                          │            │
                        GND        [R_E 470] ‖ [C_E 47µ] → GND
         V_CC ──[R_C 4.7k]── vout ──[C_out 10µ]── vload
                                        │              │
              base ──[R_F 47k]──[C_F 1µ]┘          [R_L 10k] → GND
```

## Q-point (analytical / op-point validated)

* V_B ≈ 1.03 V, V_E ≈ 0.38 V, V_BE ≈ 0.66 V
* I_C ≈ 0.8-1.0 mA (active region)
* V_C ≈ 8.2 V, V_CE ≈ 7.8 V

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — KiCad-схема
  (после материализации: `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project (для GUI Simulator).
- `models/Q2N3904.lib` — SPICE model card (ON Semi Gummel-Poon).

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch

## Phase margin (T153 4-method matrix)

    # Canonical break for V single — collector side (vout, C_F):
    efactory bridge measure phase-margin <PROJECT> \
        --schematic <PROJECT>.kicad_sch \
        --loop-break-node vout --loop-break-element C_F
