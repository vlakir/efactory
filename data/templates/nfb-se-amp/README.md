# nfb-se-amp template

Двухкаскадный single-ended audio amp с global voltage NFB:
6Н1П (driver, triode) → 6П14П (output, pentode) → OPT 5kΩ:8Ω →
нагрузка 8 Ω. Feedback (R_fb 4.7 kΩ + C_fb_block 10 µF) из
вторички OPT в катод 1-го каскада. Target phase margin ~45-60°
(analytical estimate, validate в Phase B PM-tool).

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — схема
  (после материализации: `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project (нужен для
  GUI Simulator).
- `models/6N1P.lib` — driver tube.
- `models/6P14P.lib` — output tube.
- `models/OPT_SE_5K_8.lib` — выходной трансформатор.

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch

## Phase margin (T153 Phase B+, planned)

    /measure-phase-margin --loop-break-node /sec_a
    # break node — auto-detect heuristic выберет global loop
