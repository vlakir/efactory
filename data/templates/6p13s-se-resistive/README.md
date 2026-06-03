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
- Rk = 470Ω ‖ Ck = 220µF (cathode self-bias, T173 refined)
- Rg = 470kΩ (grid leak)
- Cin = 470nF (input coupling)
- Vin: AC ±0.5V @ 1 kHz

## Smoke verification (T173 refined bias)

Direct ngspice probe на этом topology:
- Rk=470Ω self-bias → Vk ≈ 12-15V → Vgk_eff ≈ -15V
- Ia op-point ≈ 25-30 mA (range зависит от tolerances)
- Vp ≈ 100-130V (well above knee)
- Anode + screen dissipations within max ratings

## См. также

- T031 Spec A-W3: «резистивная нагрузка 5-10 kΩ вместо OPT».
- `specs/T031-tube-curve-fitting/phase-5-templates.md`.
