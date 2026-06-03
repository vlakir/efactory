# 6zh32p-mic-preamp template

Микрофонный преамп на 6Ж32П (Soviet low-noise audio pentode, аналог EF86).
Single-stage class A common-cathode pentode. T031 Phase 6 — построен и
verified через internal agent end-to-end pipeline (datasheet vision →
SPICE fit → schematic adapt → simulation → measure-gain/bandwidth).

## Целевые / измеренные характеристики

| Спецификация | Цель | Измерено |
|---|---|---|
| Gain @ 1 kHz | ~40 dB (×100) | **40.76 dB (×109)** |
| Bandwidth @ −1 dB | 20 Hz – 20 kHz | **9.5 Hz – 87.5 kHz** (×5+ запас) |
| Flatness 20-20k | ±1 dB | **±0.3 dB** |
| Питание | ~250 V на аноде | V_anode 250 V, V_screen 140 V |

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — схема (после материализации:
  `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project.
- `models/6ZH32P.lib` — fitted Koren-pentode model
  (RMS 0.057 mA over 53 IV-точек, Svetlana EF86 datasheet 10/96).

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run op <netlist>

## Topology / bias

- Vbb = 250 V (anode supply), Vg2 = 140 V (screen)
- Ra = 100 kΩ (plate load)
- Rk = 2.7 kΩ ‖ Ck = 100 µF (cathode self-bias)
- Rg = 1 MΩ (grid leak), Cin = 100 nF (input coupling)
- Vin: small-signal AC test (default ±10 mV @ 1 kHz)
- **Pinout EF86 noval:** 2=K, 3=G, 6=P, 8=G2 (готов к разводке PCB).

## Известные ограничения (deferred до KiCad GUI / разводки)

1. **Output coupling stage.** В шаблоне выход берётся прямо с
   `/plate`. Перед PCB разводкой добавь через KiCad GUI:
   - `C_out` 1 µF (на 100k нагрузку → fLF ≈ 1.6 Hz);
   - `R_load` 100 kΩ к ground;
   - `R_gridstop` 470 Ω – 1 kΩ последовательно (защита следующего
     каскада / RFI).
2. **B+ filtering + screen-dropping R + bypass** — добавь при
   реализации железа на 250 V rail.
3. **Noise modeling** — fitted `.lib` не моделирует thermal /
   shot / flicker noise (out of scope T031). 6Ж32П = EF86 known
   low-noise; реальный уровень драйвится подбором экземпляра и
   чистотой питания.
4. **Symbol** — Valve:EL84 (4-pin pentode P/G2/G/K — visually
   generic). Cosmetic upgrade на Valve:EF86 — отдельный refactor;
   pinout уже EF86-correct.

## Provenance

Создан агентом в `efactory:linux` контейнере как live smoke test
T031 KB-sync pipeline (Phase 6). Agent самостоятельно:
- нашёл `6zh38p-if-amp` как baseline через KB topic
  `spice.tube-rf-amp-6zh38p`;
- обнаружил datasheet Svetlana EF86 10/96 через WebSearch;
- vision-extracted 53 IV-точки в JSON;
- запустил `efactory tube fit-from-points` для SPICE-модели;
- адаптировал schematic под EF86 noval pinout;
- iterated bias resistors до достижения 40.76 dB gain;
- запустил `/measure-gain` / `/measure-bandwidth` для verification.

Host-side promotion в built-in (data/templates/ + data/models/) —
T031 Phase 6 close-out by human user.

## См. также

- KB topic `spice.tube-mic-preamp-6zh32p`.
- `data/templates/6zh38p-if-amp/` — baseline RF/IF amp (предок).
- `specs/T031-tube-curve-fitting/phase-6-agent-smoke-test.md` —
  полный live test transcript.
