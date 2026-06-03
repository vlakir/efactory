---
topic: spice.tube-rf-amp-6zh38p
description: Класс A resistance-coupled small-signal amp на 6Ж38П (frame-grid sharp-cutoff RF/IF pentode, T031 Phase 5 template).
tags: [spice, tube, pentode, rf, if, preamp, 6zh38p, 6bh6, ef190, audio]
---
# 6Ж38П resistance-coupled small-signal amp

## Когда смотреть в этот topic

- User просит «RF preamp на 6Ж38П / 6BH6 / EF190», «IF amp на
  sharp-cutoff pentode», «audio preamp на frame-grid pentode».
- `efactory project create` хочет шаблон `6zh38p-if-amp`.
- Нужен compact single-stage pentode amp без OPT для measurement-
  grade signal preamp / RF IF stage.

## Что есть в efactory

Шаблон **`6zh38p-if-amp`** (T031 Phase 5) — single-pentode class A
resistance-coupled stage:

- **Tube:** 6Ж38П (= 6BH6 / 6J38P / EF190 western eq.) — frame-grid
  sharp-cutoff RF pentode, μ≈334, 13 mA Imax, ~3W max anode.
- **Topology:** classic class A resistance-coupled (pattern GE 6BH6
  datasheet ET-T525B):
  - Vbb = 150 V (anode supply), Vg2 = 150 V (screen, fixed bias)
  - Rp = 10 kΩ (plate load)
  - Rk = 1 kΩ ‖ Ck = 10 µF (cathode self-bias)
  - Rg = 1 MΩ (grid leak), Cin = 100 nF (input coupling)
  - Vin: AC ±10 mV @ 1 kHz default test signal
- **Symbol:** Valve:EL84 (canonical 4-pin pentode P/G2/G/K — visually
  generic; dedicated 6Ж38П symbol deferred per T174, см.
  `tubes.curve-fitting`).
- **Default op-point (T175 smoke verified):** V(plate) ≈ 115 V,
  V(cathode) ≈ 4 V, Vgk_eff ≈ −2 V (self-bias через RGI/Rg divider),
  **Ia ≈ 3.5 mA**, Ig2 ≈ 0.5 mA, anode dissipation 0.4 W.

## Model provenance

`data/models/tubes/custom/6ZH38P.lib` — fitted T031 Phase 4 на GE
6BH6 datasheet Page 3 lower graph (Vg2=150V). Fit RMS 0.283 mA на
26 IV-точках; control-point verification +/- 7.6% max (внутри SC#2
±15%). Published reference cross-check: Va=250, Vg=−1.0 → datasheet
7.4 mA, model 7.37 mA = **−0.4%** (Phase 4 acceptance).

## Известные ограничения / quirks

- **`ex=1.05` lower bound hit** в fit (T031 Phase 4 §3): bounds
  `(1.05, 2.95)` were active. Sharp-cutoff RF pentode часто имеют
  low effective exponent; numerically fit отличный, но physical
  param интерпретация approximate.
- **Symbol Valve:EL84** (не dedicated 6Ж38П). Visually generic 4-pin
  pentode; SPICE netlist correct independent of symbol (T174 docs
  why dedicated Soviet symbol deferred).
- **Grid bias quirk:** RGI=1MΩ внутри .lib SUBCKT + Rg=1MΩ external
  → grid potential plays voltage divider, V(grid) ≈ V(cathode)/2.
  Это accepted behavior для standard ngspice tube model, не bug.

## См. также

- `tubes.curve-fitting` — T031 pipeline rationale, KG2 fallback.
- `specs/T031-tube-curve-fitting/phase-5-templates.md` §3 — full
  op-point verification table.
- `data/templates/6p13s-se-resistive/` — output stage аналог для
  power amp на резистивной нагрузке без OPT.
