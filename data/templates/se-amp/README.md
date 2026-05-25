# se-amp template

Single-ended pentode amplifier на 6П14П (EL84-аналог), выходной
трансформатор 5kΩ:8Ω, нагрузка 8 Ω.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — схема
  (после материализации: `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project (нужен для
  GUI Simulator).
- `models/6P14P.lib` — лампа.
- `models/OPT_SE_5K_8.lib` — выходной трансформатор.

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch
