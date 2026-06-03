---
topic: spice.tube-mic-preamp-6zh32p
description: Микрофонный преамп на 6Ж32П (Soviet low-noise EF86-аналог) — gain 40 dB / BW 20-20k Hz / T031 Phase 6 agent-built template.
tags: [spice, tube, pentode, microphone, preamp, audio, 6zh32p, ef86, low-noise]
---
# 6Ж32П микрофонный preamp template

## Когда смотреть в этот topic

- User просит «микрофонный преамп», «mic preamp tube», «6Ж32П
  preamp», «EF86 preamp», «low-noise pentode preamp», «динамический
  микрофон + ламповый preamp».
- `efactory project create` хочет шаблон `6zh32p-mic-preamp`.
- Нужен small-signal pentode amp с gain ≈40 dB одним каскадом.

## Что есть в efactory

Шаблон **`6zh32p-mic-preamp`** (T031 Phase 6) — single-stage class A
common-cathode pentode preamp. Построен и verified через internal
agent end-to-end pipeline.

- **Tube:** 6Ж32П (= EF86 western eq.) — Soviet low-noise audio
  pentode, μ≈22, sharp-cutoff, классика микрофонных и phono
  preamp'ов 1960-х.
- **Topology:** common-cathode + self-bias + RC-coupled output:
  - Vbb = 250 V (anode supply), Vg2 = 140 V (screen, fixed bias)
  - Ra = 100 kΩ (plate load)
  - Rk = 2.7 kΩ ‖ Ck = 100 µF (cathode self-bias)
  - Rg = 1 MΩ (grid leak), Cin = 100 nF (input coupling)
  - Vin: AC ±10 mV @ 1 kHz default test signal
- **Symbol:** Valve:EL84 (visually generic 4-pin pentode);
  **pinout EF86 noval** (2=K, 3=G, 6=P, 8=G2) — готов к разводке.

## Достигнутые характеристики (T175-style smoke verified)

| Спецификация | Цель | Измерено |
|---|---|---|
| Gain @ 1 kHz | ~40 dB | **40.76 dB (×109)** |
| Bandwidth @ −1 dB | 20 Hz – 20 kHz | **9.5 Hz – 87.5 kHz** |
| Flatness 20-20k | ±1 dB | **±0.3 dB** |
| V_anode op-point | ~125 V | 125 V (Ia ≈ 1.25 mA) |

Для динамического микрофона (SM57 / ~600 Ω): gain 40 dB поднимает
типичный mic-level −50 dBu до line-level −10 dBu — целевой сценарий.

## Model provenance

`data/models/tubes/custom/6ZH32P.lib` — fitted T031 Phase 6 agent
на Svetlana EF86 datasheet 10/96 (drtube.com/datasheets/ef86-
sed1996.pdf). 53 IV-точки vision-extracted, fit RMS 0.057 mA —
excellent. Header `tube_type: pentode`.

## Известные deferred items (документировано в template README)

1. **Output coupling stage** — C_out 1µF + R_load 100k + R_gridstop
   470Ω-1k. Добавляются в KiCad GUI перед PCB разводкой (placement
   важен).
2. **B+ filter network + screen-dropping R + bypass** — при
   реализации железа.
3. **Noise modeling** — не покрывается fit-pipeline; реальный шум
   драйвится подбором экземпляра.

## Anti-pattern (NE делай)

- **Не путай с 6Ж38П** (`6zh38p-if-amp` template) — другая лампа:
  μ≈334 sharp-cutoff RF/IF, gain ниже у 6Ж38П, оптимальна для
  широкополосных IF stage, не для audio preamp.
- **Не используй `se-amp`** template для микрофонного preamp —
  он на 6П14П output с OPT 5k:8Ω для динамика, не для line-out.

## Provenance: agent live smoke test

Шаблон создан внутри `efactory:linux` контейнера через slash + CLI
chain полностью автономно. Vladimir-tested 2026-06-04 как live
acceptance T031 Phase 6 KB-sync pipeline. Полный transcript:
`specs/T031-tube-curve-fitting/phase-6-agent-smoke-test.md`.

## См. также

- KB `tubes.curve-fitting` — pipeline rationale, fit gotcha'и.
- KB `spice.tube-rf-amp-6zh38p` — родственный pentode template.
- KB `spice.tube-line-preamp` — двухкаскадный triode preamp.
- KB `spice.tube-phono-riaa` — RIAA preamp для phono.
