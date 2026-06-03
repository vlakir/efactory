# 6p13s-se-resistive template

Single-ended amp на 6П13С с резистивной нагрузкой 5 kΩ (без OPT).
Pattern T031 Spec A-W3 — резистивный nullload op-point smoke без
OPT-сложности. Шаблон T031 Phase 5.

## Файлы

- `{{PROJECT_NAME}}.kicad_sch` — схема (после материализации:
  `<имя_проекта>.kicad_sch`).
- `{{PROJECT_NAME}}.kicad_pro` — KiCad project.
- `models/6P13S.lib` — fitted Koren-pentode model (header `tube_type:
  tetrode`, T031 Phase 4 acceptance).

## Запуск симуляции

    /sim-run
    # или напрямую:
    efactory bridge sim-run op <netlist>

## Bias

- Vbb = 250V (anode supply)
- Vg2 = 200V (screen)
- Rload = 5kΩ (резистивная нагрузка — A-W3)
- Rk = 200Ω ‖ Ck = 220µF (cathode self-bias → Vg ≈ -4V auto)
- Rg = 470kΩ (grid leak)
- Cin = 470nF (input coupling)
- Vin: AC ±0.5V @ 1 kHz

## Производное Phase 4 acceptance smoke

Direct ngspice probe на этом topology (Phase 5 smoke verification):
- Ia op-point ≈ 18.7 mA
- Ig2 op-point ≈ 3.0 mA
- Vp ≈ 156V
- Anode dissipation 3W (within 14W max)

## См. также

- T031 Spec A-W3: «резистивная нагрузка 5-10 kΩ вместо OPT».
- `specs/T031-tube-curve-fitting/phase-5-templates.md`.
