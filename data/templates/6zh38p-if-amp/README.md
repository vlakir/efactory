# 6zh38p-if-amp template

Class A resistance-coupled amp на 6Ж38П (frame-grid sharp-cutoff pentode,
~13 mA Imax, Mu≈330). Шаблон T031 Phase 5.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — схема (после материализации:
  `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project.
- `models/6ZH38P.lib` — fitted Koren-pentode model (T031 Phase 4 acceptance).

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run op <netlist>

## Bias

- Vbb = 150V (anode supply)
- Vg2 = 150V (screen, fixed bias через separate source)
- Rp = 10kΩ (plate load)
- Rk = 1kΩ ‖ Ck = 10µF (cathode self-bias)
- Rg = 1MΩ (grid leak)
- Cin = 100nF (input coupling)
- Vin: small-signal AC ±10 mV @ 1 kHz

## См. также

- KB topic `tubes.curve-fitting` — T031 pipeline rationale.
- `specs/T031-tube-curve-fitting/phase-5-templates.md`.
