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
| Phase 1 (Pilot) | **Host-side:** manual MAS skeleton OPT 6П14П SE (близко к ШЛ16×16) → `calculate_inductance_from_number_turns_and_gapping` (PyOM analytical, лёгкий путь). Генерация `.geo` из тех же dimensions. **Pilot Dockerfile (heavy run, `--memory=4g`):** (a) `design_magnetics_from_converter("push_pull", ...)` — full advisor optimization, реальная «тяжёлая» задача (stress test memory + времени); (b) Elmer FEM на manual MAS geometry; (c) GetDP+Gmsh FEM на той же geometry. Заполнить сравнительную таблицу (§Pilot table). ADR с выбором FEM-solver'а. | Таблица заполнена; ADR в `DECISIONS.md`; pilot отрабатывает в `--memory=4g` контейнере без OOM. |
| Phase 2 (Integration) | apt-install выбранного solver'а в `Dockerfile` (base stage, рядом с KiCad / FreeCAD). `src/ports/outbound/magnetic_analytics_port.py` (Protocol для PyOpenMagnetics). `src/ports/outbound/magnetic_field_solver_port.py` (Protocol для FEM-solver'а). Adapter'ы в `src/adapters/outbound/`. Use case `mag_verify_field` в `src/application/`. | OPT 6П14П: analytical inductance совпадает с FEM ±10%; integration test зелёный; solver в efactory:linux runtime. |

## Pilot fixture: OPT 6П14П SE

Single-ended output transformer для лампового усилителя на 6П14П
(EL84). Известны параметры из data/models:

- **Primary inductance Lp**: 5–7 H (typical для SE OPT 6П14П).
- **Turns ratio**: ~5000:8 Ω → N₁/N₂ ≈ 25.
- **Core**: silicon-steel laminated EI — manual MAS skeleton,
  размеры близки к ШЛ16×16 (стандарт советских OPT под 6П14П SE);
  ближайший шейп из PyOM каталога подбирается grep'ом по
  `get_core_shapes()` (family `e`, габариты ~42×21×16 мм).
- **Operating frequency**: 20 Hz – 20 kHz (audio band; pilot
  считает на 1 kHz как mid-band reference).
- **Air gap**: распределённый ~0.1 мм (типично для SE OPT для
  компенсации DC bias класса A).

Геометрия выкладывается в `tests/fixtures/magnetic/opt-6p14p-se/`:

- `geometry.json` — JSON в формате PyOpenMagnetics MAS (Magnetic
  Application Specification) — core (shape + material + gapping),
  coil (turns), operating point. **Составляется вручную** в
  `scripts/pilot/build_fixture.py` (запускается на хосте; advisor
  не вызывается — только лёгкий `calculate_*` API).
- `geometry.geo` — Gmsh-формат для FEM-solver'ов (Elmer / GetDP).
  Тот же геометрический объект, генерируется из `geometry.json`
  скриптом `scripts/pilot/mas_to_gmsh.py`.
- `expected.json` — analytical inductance из PyOM
  `calculate_inductance_from_number_turns_and_gapping` (записывается
  при сборке фикстуры); используется в integration acceptance test
  как reference.

**Pilot heavy run (отдельно от фикстуры):** в `pilot.Dockerfile`
прогоняется полный `design_magnetics_from_converter("push_pull", ...)`
с audio-band параметрами — это «тяжёлая задача» для stress-test'а
(memory + время), не источник geometry. Результаты идут в Pilot
table как информационная колонка («PyOM advisor pick»), но фикстура
для FEM построена на manual skeleton — иначе advisor каждый раз
может выбирать разный core.

50 Hz силовой трансформатор и flyback SMPS дроссель — **out of
scope T113**, вынесены в BACKLOG (cross-validation follow-up'ы,
заводим после ADR pilot'а как T127, T128).

## Pilot table

Сравнительная таблица для ADR-решения. Заполнена в Phase 1 (Stages A-E,
2026-05-20), попала в ADR `2026-05-20 — Magnetic field verification:
GetDP+Gmsh выбран (Elmer — cross-validation в BACKLOG)` в
`DECISIONS.md`.

| Критерий | PyOM analytical (manual MAS) | PyOM advisor (flyback¹, info-only) | Elmer FEM | GetDP + Gmsh |
|---|---|---|---|---|
| Inductance Lp (расчётная, H) | 6.96 (ZHANG)² | 6.35e-3 (nominal magnetizing Lp на flyback design) | 23.78 | 23.78 |
| Время расчёта (s) | 0.12 | 45.3 (heavy) | 0.04 (ElmerGrid) + 3.10 (solve) = 3.14 | 0.86 |
| Peak RAM (MB, через `/usr/bin/time -v`) | 88 | 1067 | 47 | 119 |
| Размер в Docker layer (apt deps, MB) | 11 (wheel) + ~50 deps | same | ~115 (`elmerfem-csc` 100 + `libmumps`/`libhypre` deps 15) | ~45 (`getdp` 5 + `libpetsc` 19 + `libslepc` 3 + `libgmsh` 18) |
| API для LLM-orchestration | high (AGENTS.md, MAS-JSON) | high (single call) | среднее (CLI: ElmerGrid + ElmerSolver — два subprocess'а; .sif с квирками: SaveScalars `body int` + `Mask Name`, обязательность Active Solvers, см. auto-memory `feedback_elmer_savescalars_quirks.md`) | высокое (CLI: один subprocess `getdp <.pro> -msh <.msh> -solve <ResName>`; .pro более прямолинеен) |
| Mesh quality (для FEM) | n/a | n/a | использует ту же `geometry.msh` через ElmerGrid (Gmsh msh22 → mesh.{header,nodes,elements,boundary}); качество идентично GetDP | reads `geometry.msh` напрямую; 12244 quadratic triangles, mesh-converged (B+C: 5334→12244 элементов: 23.71→23.78 H) |
| Open-source license | MIT | MIT | GPL | GPL |
| Поддержка под Linux + apt | ✅ pip wheel (cp313 x86_64) | same | ✅ `elmerfem-csc` (Elmer 26.2, через `ppa:elmer-csc-ubuntu/elmer-csc-ppa` — в noble universe нет) | ✅ `getdp` (3.2.0) + `gmsh` (4.12.1) в noble universe штатно |
| Community / commits last 6mo | active (1.3.10 May 2026) | same | github.com/ElmerCSC/elmerfem: 1575★, last push 2026-05-19, **330 commits last 6mo** (очень активный) | gitlab.onelab.info/getdp: последний stable release 3.5.0 (May 2022), но active snapshots, copyright 2026 (поддерживается, но slower release cadence) |

¹ Spec изначально просит `push_pull`, но PyOM 1.3.10 advisor возвращает
`{"data": []}` (нет подходящих cores) на типичных push_pull параметрах
(50W/10W telecom 36–72V → 5V). Pilot stress-test реализован на
canonical AGENTS.md §6.1 flyback (220V→12V/2A 100kHz 24W) — цель
(advisor под нагрузкой, измерение времени+памяти) сохранена. См.
auto-memory `feedback_pyom_advisor_quirks.md`.

² PyOM analytical перебирает 5 reluctance моделей (ZHANG/MUEHLETHALER/
BALAKRISHNAN/STENGLEIN/EFFECTIVE_AREA), Lp в диапазоне 6.65–7.02 H.
В таблице — ZHANG (default).

**Главный observation Phase 1:** Elmer и GetDP на одной mesh с
идентичной физикой (linear μ_r=8000, ±Jz coil topology, Dirichlet
A=0 на infinity boundary) сошлись **до printed precision: оба 23.78 H,
0.00% cross-check**. Расхождение FEM ↔ PyOM analytical (242%) —
воспроизводится одинаково в обоих solver'ах → известный physics
model gap (operating-point-dependent μ_eff в PyOM vs constant
μ_r=8000 в линейной FEM-формулировке), не bug в одном из solver'ов.
В Phase 2 эта разница ликвидируется добавлением nonlinear B-H curve
material (Elmer/GetDP оба supports) либо переходом на operating-point
μ_eff в FEM-фазе.

**Memory note:** PyOM advisor с `"available cores"` (~1301 shapes)
требует > 6 GB peak RSS на нашей host'е (6.2 GB available) → OOM-kill
в `--memory=4g` и `--memory=6g` контейнерах. С `"standard cores"`
(~1250 magnetics после pruning) укладывается в 1067 MB / 4g → OK.
Pilot использует "standard cores" (рекомендация для Phase 2 runtime
agent — same, либо документировать большое требование к памяти).

**Decision criteria (в порядке убывания веса):**

1. Близость FEM к analytical (PyOpenMagnetics) на OPT 6П14П (±10%).
2. Размер в Docker layer (предпочтение ≤ 250 MB apt-packages).
3. API-удобство — насколько просто вызвать solver subprocess'ом
   с JSON-input / file-input.
4. Поддержка модели materials / non-linear core.

**Assessment по критериям:**

1. **Близость к analytical**: оба FEM **одинаково расходятся** на 242%
   (это physics gap, см. observation выше) → критерий не разделяет
   solvers. *Tie.*
2. **Docker layer**: GetDP ≈ 45 MB, Elmer ≈ 115 MB — оба под 250 MB
   threshold, но **GetDP в 2.5× меньше** (плюс уже в noble universe,
   не нужен PPA). *GetDP.*
3. **API**: GetDP — один subprocess + один .pro файл, прямолинейный
   синтаксис weak-form. Elmer — два subprocess'а (ElmerGrid + ElmerSolver),
   .sif с известными квирками (см. таблицу). *GetDP.*
4. **Material model**: оба поддерживают nonlinear B-H (Elmer: `Material
   { H-B Curve = ... }`; GetDP: `nu[] = NLF[Material]{H}`). Elmer имеет
   больше built-in модулей (eddy currents, JouleHeating) для будущих
   расширений; GetDP — низкоуровневый DSL, всё руками. *Elmer slight
   edge, но не блокирующее для T113 use case (magnetostatic).*

→ **GetDP** выигрывает по 2 из 4 критериев (включая высший #2 по весу
после tied #1), Elmer — по 1 (низшему #4). Decision в ADR.

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

- `tests/fixtures/magnetic/opt-6p14p-se/{geometry.json,geometry.geo,expected.json}`
  существуют. `geometry.json` — manual MAS skeleton (близко к
  ШЛ16×16), `expected.json` — PyOM analytical Lp на нём; собрано
  скриптами `scripts/pilot/build_fixture.py` + `mas_to_gmsh.py` на
  хосте (только лёгкие `calculate_*` API, без advisor).
- `pilot.Dockerfile` собирается; запуск через `docker run
  --memory=4g efactory-pilot` прогоняет:
  - PyOM analytical на manual MAS (sanity-check, должен совпасть
    с `expected.json`),
  - PyOM advisor — `design_magnetics_from_converter("push_pull",
    audio-band, "available cores")` — «тяжёлая» задача,
    information-only,
  - Elmer FEM на `geometry.geo`,
  - GetDP+Gmsh FEM на `geometry.geo`.
- Pilot table в этом spec'е заполнена measured-значениями
  (включая peak RAM через `/usr/bin/time -v`).
- ADR в `DECISIONS.md` фиксирует выбор FEM-solver'а для Phase 2.
- В контейнере с `--memory=4g` advisor отрабатывает без OOM
  (если упирается — фиксируем требование к памяти в ADR; на хосте
  Владимира всё равно advisor не запускается).

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

1. ~~OPT 6П14П SE — точные dimensions?~~ **Closed 2026-05-20:**
   manual MAS skeleton близко к ШЛ16×16, ближайший шейп в PyOM
   каталоге (family `e`, ~42×21×16 мм). Production datasheet
   (Hammond / TANGO) не привязываем — для pilot важна solver-
   агрегация на **одной** geometry, а не её точное соответствие
   конкретному коммерческому изделию.
2. **Elmer vs GetDP — какой first-class в integration?** Решение из
   pilot table. В Phase 2 интегрируется **только выбранный**;
   второй — в BACKLOG как cross-check (опциональный extras).
3. **`mag_verify_field` use case API** — как именно агент будет
   вызывать (через MCP-tool? Прямой Python? Domain command)? Уточним
   при реализации Phase 2 после T012-T014 (chat-client).
