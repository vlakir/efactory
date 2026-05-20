# T113 — FEM-solver pilot + integration

**Phase 3 контейнеризации** (см. `specs/T110-containerization/spec.md`
§Phase 3). Заменяет FEMM (Wine) на Linux-native стек.

## Цель

Дать efactory-агенту **полноценный magnetic toolkit** — для дизайна
трансформаторов, дросселей, SMPS-компонентов и им подобного. Включает:

1. **Analytical engine** — быстрый расчёт по характеристикам сердечника,
   обмоток, материала (PyOpenMagnetics).
2. **FEM solver** — точный расчёт магнитного поля с учётом 3D-геометрии,
   leakage, fringing (выбирается в pilot между Elmer FEM и GetDP+Gmsh).
3. **Adapter-слой** в hex-архитектуре: два `outbound` port'а,
   агент через MCP может вызвать analytical (для design sweep)
   или FEM (для validation) — в зависимости от задачи.

## Структура задачи

**Один PR** с phase-коммитами на ветке `T113-fem` (Vladimir clarify
2026-05-20). Перед merge — squash в один коммит.

| Phase | Содержание | Acceptance |
|---|---|---|
| Phase 0 (Setup) | Downgrade Python 3.14→3.13 (см. ADR `DECISIONS.md` 2026-05-20). `uv add pyopenmagnetics`. ADR analytical toolkit. Spec (этот документ). T111 BACKLOG-маркер chore. | 4 gates ✅; venv 215 MB. |
| Phase 1 (Pilot) | `pilot.Dockerfile` (одноразовый, py 3.13 + Elmer + GetDP + Gmsh + PyOpenMagnetics). Геометрия OPT 6П14П SE. Прогон трёх «точек»: PyOpenMagnetics analytical, Elmer FEM, GetDP+Gmsh FEM. Заполнить сравнительную таблицу (§Pilot table). ADR с выбором FEM-solver'а. | Таблица заполнена; ADR в `DECISIONS.md`. |
| Phase 2 (Integration) | apt-install выбранного solver'а в `Dockerfile` (base stage, рядом с KiCad / FreeCAD). `src/ports/outbound/magnetic_analytics_port.py` (Protocol для PyOpenMagnetics). `src/ports/outbound/magnetic_field_solver_port.py` (Protocol для FEM-solver'а). Adapter'ы в `src/adapters/outbound/`. Use case `mag_verify_field` в `src/application/`. | OPT 6П14П: analytical inductance совпадает с FEM ±10%; integration test зелёный; solver в efactory:linux runtime. |

## Pilot fixture: OPT 6П14П SE

Single-ended output transformer для лампового усилителя на 6П14П
(EL84). Известны параметры из data/models:

- **Primary inductance Lp**: 5–7 H (typical для SE OPT 6П14П).
- **Turns ratio**: ~5000:8 Ω → N₁/N₂ ≈ 25.
- **Core**: EI ferrite или silicon-steel laminated (выбираем EI
  под референсный 6П14П SE — детали в `geometry.json` фикстуры).
- **Operating frequency**: 20 Hz – 20 kHz (audio band; pilot
  считает на 1 kHz как mid-band reference).

Геометрия выкладывается в `tests/fixtures/magnetic/opt-6p14p-se/`:

- `geometry.json` — JSON в формате PyOpenMagnetics MAS (Magnetic
  Application Specification) — core dimensions, winding turns,
  material, operating point. Использовать `design_magnetics_from_converter()`
  или вручную составить.
- `geometry.geo` — Gmsh-формат для FEM-solver'ов (Elmer / GetDP).
  Тот же геометрический объект.
- `expected.json` — analytical inductance из PyOpenMagnetics
  (recorded в pilot); используется в integration acceptance test
  как reference.

50 Hz силовой трансформатор и flyback SMPS дроссель — **out of
scope T113**, вынесены в BACKLOG (cross-validation follow-up'ы,
заводим после ADR pilot'а как T127, T128).

## Pilot table

Сравнительная таблица для ADR-решения. Заполняется в Phase 1, попадает
в ADR `2026-MM-DD — Magnetic field verification: choice solver`.

| Критерий | PyOpenMagnetics (analytical) | Elmer FEM | GetDP + Gmsh |
|---|---|---|---|
| Inductance Lp (расчётная, H) | _measured_ | _measured_ | _measured_ |
| Время расчёта (s) | _measured_ | _measured_ | _measured_ |
| Размер в Docker layer (apt deps, MB) | 11 (wheel) + ~50 deps | _measured_ | _measured_ |
| API для LLM-orchestration | high (AGENTS.md, MAS-JSON) | средне (CLI + Sif config) | средне (CLI + GetDP .pro) |
| Mesh quality (для FEM) | n/a | _assessment_ | _assessment_ |
| Open-source license | MIT | GPL | GPL |
| Поддержка под Linux + apt | ✅ pip wheel | ✅ `elmerfem-csc` apt | ✅ `getdp` + `gmsh` apt |
| Community / commits last 6mo | _check_ | _check_ | _check_ |

**Decision criteria (в порядке убывания веса):**

1. Близость FEM к analytical (PyOpenMagnetics) на OPT 6П14П (±10%).
2. Размер в Docker layer (предпочтение ≤ 250 MB apt-packages).
3. API-удобство — насколько просто вызвать solver subprocess'ом
   с JSON-input / file-input.
4. Поддержка модели materials / non-linear core.

## Integration architecture

**Dual port architecture:**

```
src/ports/outbound/
  ├── magnetic_analytics_port.py        # Protocol: design / verify (быстро)
  └── magnetic_field_solver_port.py     # Protocol: FEM compute (точно)

src/adapters/outbound/
  ├── magnetic_analytics_pyopenmagnetics/
  │   └── adapter.py                    # Wrapper PyOpenMagnetics
  └── fem_solver_<chosen>/
      └── adapter.py                    # subprocess wrapper Elmer/GetDP
```

**Use case `mag_verify_field`** (`src/application/mag_verify_field.py`):

1. Принимает `MagneticComponent` (domain object: core geometry,
   winding spec, operating point).
2. Вызывает `magnetic_analytics_port.calculate_inductance()` —
   быстрая analytical inductance.
3. Опционально (флаг `verify_with_fem=True`) — вызывает
   `magnetic_field_solver_port.solve_inductance()` для FEM-cross-
   check. Сравнивает; flag'ует расхождение > ±10%.
4. Возвращает `MagneticVerificationResult` (inductance, leakage,
   peak flux, optional FEM-verification status).

## Acceptance per phase

**Phase 0 (Setup)** — текущий PR-state до Pilot:

- `requires-python = ">=3.13,<3.14"` в `pyproject.toml`.
- `pyopenmagnetics` в `dependencies`.
- ADR-ы: «Python 3.14→3.13», «Magnetic analytical: PyOpenMagnetics».
- 4 gates ✅ (ruff / format / mypy / pytest на 3.13).
- venv ≤ 250 MB.

**Phase 1 (Pilot)** — после прогона:

- `pilot.Dockerfile` собирается, один shot прогоняет 3 solver'а
  на OPT 6П14П SE.
- Pilot table в этом spec'е заполнена measured-значениями.
- ADR в `DECISIONS.md` фиксирует выбор FEM-solver'а.
- `tests/fixtures/magnetic/opt-6p14p-se/{geometry.json,geometry.geo,expected.json}` существуют.

**Phase 2 (Integration)** — после реализации:

- Выбранный FEM-solver в `Dockerfile` base stage (`apt install
  elmerfem-csc` или `getdp + gmsh`).
- `magnetic_analytics_port.py` + adapter PyOpenMagnetics — реализованы.
- `magnetic_field_solver_port.py` + adapter `fem_solver_<chosen>` —
  реализованы.
- Use case `mag_verify_field` — реализован с unit tests.
- Integration test: OPT 6П14П analytical L (PyOpenMagnetics) совпадает
  с FEM-solver L в пределах ±10%.
- 4 gates ✅; pytest внутри `efactory:linux` зелёный.
- Размер `efactory:linux` ≤ 7 GB (текущий 6.65 GB + ~250 MB
  solver-apt-deps).

## Out of scope T113 (BACKLOG)

- **T127** (заведём после ADR pilot'а) — Power transformer 50 Hz
  fixture для cross-validation.
- **T128** (заведём после ADR pilot'а) — Flyback SMPS choke fixture.
- **mag-net-hub** (ML-based core-loss prediction) — отдельной задачей,
  не блокирует T113.
- **3D геометрии complex shapes** (planar transformers, helical
  winding) — вторая итерация, не pilot fixture.

## Open questions

(Заполняется в процессе реализации, finalize в ADR.)

1. **OPT 6П14П SE — точные dimensions?** Из data/models/ есть SPICE-
   library (`OPT_SE_5K_8.lib`), но нет geometry. Возможно нужно
   взять референсный production datasheet (Hammond / TANGO / коп.
   ШЛ16×16) и заморозить в fixture.
2. **Elmer vs GetDP — какой first-class в integration?** Решение из
   pilot table. В Phase 2 интегрируется **только выбранный**;
   второй — в BACKLOG как cross-check (опциональный extras).
3. **`mag_verify_field` use case API** — как именно агент будет
   вызывать (через MCP-tool? Прямой Python? Domain command)? Уточним
   при реализации Phase 2 после T012-T014 (chat-client).
