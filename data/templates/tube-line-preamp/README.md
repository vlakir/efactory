# tube-line-preamp template

Двухкаскадный all-triode line preamp на 6Н2П (обе половины
`Valve:ECC83` unit 1 + unit 2 = `Valve:ECC83B`):

- **Stage 1 (CC, common-cathode voltage amplifier):** V1A,
  R_p1=100 kΩ plate load, R_k1=1.5 kΩ ‖ C_k1=22 µF (standard
  auto-bias с bypass), C_in=100 nF input coupling.
- **Stage 1-2 coupling:** C_couple=47 nF inter-stage cap.
- **Stage 2 (CF, cathode follower):** V1B, V1B.P → directly
  к B+ (CF defining feature: NO plate load), R_k2=33 kΩ
  cathode load **без bypass** (CF inherently degenerative
  by design — gain ≈ 1, low output impedance).
- **Output:** C_out=0.47 µF к assumed next-stage 100 kΩ load
  (e.g., power amp grid leak).

## Топология

```
        ┌─[R_p1 100k]─ B+ ────────────────────────┐
        │                                          │
  Vin ─[C_in 100n]─[R_g1 1M]─G                     │
                              │ V1A (6Н2П unit 1)  │
                              K → R_k1 1.5k ‖ C_k1 22µ → GND
                              │
                              P (= V_plate1)
                              │
                       [C_couple 47n]
                              │
                       [R_g2 470k]──G
                                    │ V1B (6Н2П unit 2 — Cathode Follower)
                                    K (= V_cath2)
                                    │
                              [R_k2 33k] → GND (no bypass)
                                    │
                             [C_out 0.47µ]
                                    │
                            [R_load 100k] → GND
```

## Q-point (DC operating, validated в op-point regression test)

* V_BB = 250 V.
* Stage 1: V_plate1 ≈ 100-200 V (Stage 1 CC active region:
  V_a = V_BB - I_a·R_p1, I_a ≈ 0.5-1.5 mA).
* Stage 1: V_cathode1 ≈ 1-3 V (auto-bias через R_k1=1.5 kΩ).
* Stage 2: V_plate2 ≈ B+ (CF — direct supply, без plate load).
* Stage 2: V_cathode2 ≈ 30-100 V (CF auto-bias через R_k2=33 kΩ;
  large для high impedance, gain → 1).

## Mid-band gain (analytical + ngspice empirical)

**Analytical estimate (datasheet μ=100, r_a=80 kΩ):**

* Stage 1 (CC, R_k bypassed): A_v1 ≈ μ·R_p / (R_p + r_a) ≈
  100·100/(100+80) ≈ 55 V/V (≈ 34.8 dB).
* Stage 2 (CF): A_v2 ≈ (μ+1)·R_k2 / ((μ+1)·R_k2 + R_p + r_a)
  ≈ 0.98 (close to unity, large R_k2).
* Total: A_v_open-loop ≈ 55 · 0.98 ≈ 54 V/V (≈ 34.6 dB).

**Ngspice empirical:** |A_v| @ 1 kHz mid-band ≈ **64 V/V (36 dB)**
— на 16% выше analytical (Koren-style 6Н2П model gives g_m_eff
выше nominal datasheet g_m=1.6 mA/V). Calibration regression
fails если drift > ±15% к 64 V/V.

## Output impedance (преимущество CF stage)

Z_out_cf ≈ r_a / (μ+1) ≈ 80k / 101 ≈ **800 Ω** — низкий
output Z, способный драйвить кабель / power amp grid leak
(typical 100-470 kΩ) без HF roll-off.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — KiCad-схема.
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project (для GUI Simulator).
- `models/6N2P.lib` — оба stages (one tube, both halves).

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch

## Рекомендованные measurements

    # Mid-band voltage gain (target ≈ 64 V/V):
    efactory bridge measure gain <PROJECT> \
        --schematic <PROJECT>.kicad_sch --frequency 1000 --mode small

    # Bandwidth (-3 dB points для CC+CF cascade):
    efactory bridge measure bandwidth <PROJECT> \
        --schematic <PROJECT>.kicad_sch
