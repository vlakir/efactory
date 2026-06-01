# tube-pp-amp template

Двухкаскадный push-pull power amp с **long-tail-pair (LTP)**
phase splitter: обе половины 6Н2П (Valve:ECC83 unit 1 + unit 2),
shared cathode через R_tail=4.7 kΩ → пара 6П14П (Valve:EL84) в
push-pull с per-tube auto-bias (R_k=270 Ω ‖ C_k=220 µF) → выходной
трансформатор OPT_PP_6K6_8 (6.6 kΩ p-p : 8 Ω, center-tapped primary)
→ 8 Ω load. **Open-loop** (без global NFB) — NFB вариант остаётся
в BACKLOG отдельной задачей по аналогии с `se-amp` → `nfb-se-amp`.

**Phase splitter choice (ADR-T027a).** Изначальный план Round 2 был
concertina (split-load) на одной половине 6Н2П, но empirical-
валидация на Koren-style 6N2P model показала, что equal-resistance
concertina (Ra=Rk=47kΩ) biases tube near cutoff (I_a≈0.15 mA), и
plate-output gain атрофирует до 0.05 V/V. LTP — textbook-standard
для PP (Williamson 1947), robust к model parameter drift.

## Топология

```
                       ┌─[R_p1A 47k]─ B+ ─[R_p1B 47k]─┐
                       │                                │
  Vin ─[C_in]─[R_g 1M]─G                                G─[R_g 1M]─ GND
                       │  V1A         V1B  │
                       │ (6Н2П unit 1) (unit 2) │
                       K                       K
                        └──────┬────────┘ (common cathode rail)
                               R_tail 4.7k → GND
                       │                       │
                       P                       P (anti-phase outputs)
                       │                       │
              [C_couple_a 47n]            [C_couple_b 47n]
                       │                       │
                  G (V2a 6П14П)         G (V2b 6П14П)
                       G2 → B+                 G2 → B+
                       K ‖ R_k_C_k → GND       K ‖ R_k_C_k → GND
                       P                       P
                       │ ┌── PC center-tap → B+ ──┐ │
                       ├─[OPT.P1]               [OPT.P2]─┤
                       │                                  │
                     OPT.S1 ── [R_load 8Ω] ── OPT.S2 ── GND
```

## Q-point (DC operating, validated в op-point regression test)

* V_BB = 300 V; OPT.PC → B+ rail (DC primary impedance ≈ 0).
* V_plate_q (V2a, V2b) ≈ B+ (≈ 300 V — OPT primary DCR не critical).
* V_cathode_q (V2a, V2b) ≈ 10 V (auto-bias I_a · R_k = 37 mA · 270 Ω).
* I_a_q per output tube ≈ 37 mA (близко к 6П14П PP 12 W class A diss).
* LTP cathode tail ≈ 1-3 V (R_tail · 2·I_a_v1).
* Plate balance |V_plate_a − V_plate_b| / mean < 10% (PP symmetry).

## Mid-band gain (analytical hand-calc + ngspice empirical)

**Analytical estimate per stage:**

* LTP per-output: |A_v1| ≈ μ·R_p/(R_p+r_a) ≈ 100·47/(47+80) ≈ 37 V/V.
  Реально ~12 V/V — model parameter drift + downstream loading через
  C_couple + R_g2 (470k grid leak).
* 6П14П per-tube pentode gain: |A_v2| ≈ g_m·Z_a_per = 11mA/V · 1.65k
  ≈ 18 V/V. Реально ~28 V/V (g_m выше при V_a=300V, I_a=30mA).
* OPT step-down: V_sec/V_diff_prim = 1/N, N = √(R_aa/R_load) =
  √(6600/8) = 28.7 → 1/N = 0.035.
* Total: |A_v_open-loop| ≈ 12 · 28 · 0.035 ≈ 12 V/V (нижняя граница).

**Ngspice empirical (baseline):** |A_v| @ 1 kHz ≈ **16.5 V/V (24.4 dB)**.
Calibration regression test fails если drift > ±15%.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — KiCad-схема
  (после материализации: `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project (для GUI Simulator).
- `models/6N2P.lib` — splitter tubes (LTP pair, same SUBCKT).
- `models/6P14P.lib` — PP output tubes (pair, same model).
- `models/OPT_PP_6K6_8.lib` — center-tap PP output transformer.

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch

## Рекомендованные measurements

    # Mid-band voltage gain (open-loop, target ≈ 16.5 V/V):
    efactory bridge measure gain <PROJECT> \
        --schematic <PROJECT>.kicad_sch --frequency 1000 --mode small

    # THD spectrum (PP топология cancels even-order distortion):
    efactory bridge measure thd <PROJECT> \
        --schematic <PROJECT>.kicad_sch
