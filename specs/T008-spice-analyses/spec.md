# Spec: T008 — Базовые SPICE-анализы в bridge (OP / tran / AC)

**Статус:** Analyzed → In Progress (Phase 1)
**Дата создания:** 2026-05-18
**Связанные документы:**
`specs/T004-kicad-sim-pipeline/spec.md` (предшественник, оставил
`StubSimulator` как заглушку), `specs/T006-tube-library/spec.md`
(модели для фикстуры SE-amp), `specs/T007-transformer-models/spec.md`
(OPT-фикстура для SE-amp), `specs/T009-platform-and-apps/spec.md`
(`AppManager.run(NGSPICE, …)` уже есть).

---

## 1. Overview

Первая реально работающая SPICE-симуляция в efactory. Заменяет
`StubSimulator` (T004 split-scope) рабочим `NgspiceSimulator`,
который запускает ngspice batch-режимом через `AppManager.run` и
парсит ASCII raw output. Поддерживает три классических анализа —
operating point, transient, AC sweep — на трёх минимальных
тест-фикстурах (RC-фильтр, single-ended ламповый каскад,
выпрямитель). После T008 пайплайн `design-to-sim` доводит
`Simulation.status` до `SIMULATED`, а не останавливается на
`NETLIST_READY`.

## 2. Сценарии использования

В efactory нет live-пользователей (CLI-инструмент для одного
разработчика); вместо user stories — сценарии конвейера.

- **S1 (OP):** разработчик имеет KiCad-проект RC-фильтра →
  `bridge design-to-sim <project> --analysis op` → получает
  напряжения узлов в `SimulationResult.operating_points`.
- **S2 (tran):** разработчик имеет готовый SPICE-netlist SE-amp →
  `bridge sim-run sim/se_amp.cir --analysis tran --t-stop 20m --t-step 10u`
  → получает осциллограмму выходного узла, может проверить, что
  ламповый каскад в активной зоне (не зашёл в насыщение / отсечку).
- **S3 (AC):** разработчик имеет RC-фильтр →
  `bridge sim-run sim/rc_filter.cir --analysis ac --f-start 1 --f-stop 1Meg --n-points 20 --sweep dec`
  → получает АЧХ + ФЧХ, может прочитать частоту среза `fc = 1/(2πRC)`.
- **S4 (выпрямитель):** разработчик имеет KiCad-проект однополупериодного
  выпрямителя → `bridge design-to-sim ... --analysis tran` → видит
  пульсирующее выходное напряжение.
- **S5 (ngspice не установлен):** `bridge sim-run …` сразу выдаёт
  человеческое сообщение «ngspice not found in PATH, install via
  apt/brew» и exit 1, без попытки запуска.

## 3. Functional requirements

**Domain.**
- ДОЛЖНА: ввести `AnalysisSpec` — pydantic discriminated union
  `OpAnalysis | TranAnalysis | AcAnalysis` (discriminator
  `type: Literal['op'|'tran'|'ac']`).
- ДОЛЖНА: расширить `SimulationResult` тремя опциональными ветками:
  `operating_points: dict[str, float] | None`,
  `time_series: TimeSeries | None`,
  `ac_sweep: AcSweep | None`. Ровно одна из трёх заполнена в любом
  валидном результате (model_validator).
- ДОЛЖНА: ввести VO `TimeSeries(time: tuple[float, ...],
  traces: dict[str, tuple[float, ...]])` и
  `AcSweep(frequency: tuple[float, ...],
  traces_real: dict[str, tuple[float, ...]],
  traces_imag: dict[str, tuple[float, ...]])`. Complex храним парой
  real/imag (JSON-serializable; пользовательский код легко собирает
  `complex` или `magnitude/phase` на лету).

**Port.**
- ДОЛЖНА: расширить `Simulator` методом
  `async def run(self, netlist: Path, analysis: AnalysisSpec,
  *, timeout_s: float = 60.0) -> SimulationResult`.
- ДОЛЖНА: удалить старый метод `run_op` (callers переключаются на
  `run(netlist, OpAnalysis())`); StubSimulator переписывается под
  новый контракт.

**Adapter `NgspiceSimulator`.**
- ДОЛЖНА: лежать в `src/adapters/outbound/ngspice/simulator.py` (новый
  пакет), внедряться в `composition.main`.
- ДОЛЖНА: для каждого вызова `run` генерировать в TMP-файл (`<netlist>.wrapper.cir`)
  обёртку:
  ```
  .include <netlist absolute path>
  .<op|tran|ac directive>
  .control
    set filetype=ascii
    run
    write <out.raw> all
    exit
  .endc
  .end
  ```
- ДОЛЖНА: запускать `AppManager.run(ApplicationKind.NGSPICE,
  ['-b', wrapper.cir], timeout_seconds=timeout_s)` (имя параметра в
  T009 — `timeout_seconds`, не `timeout`).
- ДОЛЖНА: парсить ASCII raw (см. формат ngspice rawfile: header
  блок `Title/Date/Plotname/Flags/No. Variables/No. Points/Variables/Values`)
  в `SimulationResult`. Реализуется самописно без новых зависимостей.
- ДОЛЖНА: на таймаут / non-zero exit / отсутствие raw-файла бросать
  `SimulationFailedError(<details>)`.
- ДОЛЖНА: на отсутствие ngspice (`AppManager.status(NGSPICE).status !=
  AVAILABLE`) бросать `SimulatorUnavailableError('ngspice not found
  in PATH, install via apt/brew/...')`.

**CLI.**
- ДОЛЖНА: новая команда `bridge design-to-netlist <project>
  [--schematic PATH] [--netlist-output PATH]` — чисто экспорт без
  симуляции (вынос текущей половины `design-to-sim`).
- ДОЛЖНА: новая команда `bridge sim-run <netlist> --analysis
  op|tran|ac [...analysis params] [--timeout S]` — только симуляция
  готового netlist.
- ДОЛЖНА: `bridge design-to-sim` остаётся: теперь полная композиция
  `export + sim`; новый обязательный флаг `--analysis op|tran|ac` +
  параметры анализа.
- ДОЛЖНА: для tran/AC поддержать SPICE-style суффиксы (`1m`/`1u`/`1n`/
  `1Meg`/`1k`) при парсинге числовых параметров CLI.
- ДОЛЖНА: писать структурированный session-лог
  (`bridge.sim_run`, `bridge.design_to_sim`).

**Тесты / фикстуры.**
- ДОЛЖНА: 3 минимальных `.kicad_sch` в `tests/fixtures/`:
  `rc_filter.kicad_sch` (уже есть), `se_amp.kicad_sch` (новый,
  на GENERIC_TRIODE+OPT_SE_5K_8), `rectifier.kicad_sch` (новый,
  на RECTIFIER-tube из T006).
- ДОЛЖНА: пройти e2e матрицу (3 фикстуры × 3 анализа = 9 тестов),
  где это физически осмысленно (см. §4 success).
- ДОЛЖНА: parsing/wrapper-логика покрыта unit-тестами с
  ASCII-raw-фикстурами (без запуска ngspice — для CI на машине
  без ngspice).
- ДОЛЖНА: contract test для `NgspiceSimulator` помечен
  `@pytest.mark.requires_ngspice` и skipped, если
  `command -v ngspice` пуст.

**НЕ ДОЛЖНА.**
- НЕ ДОЛЖНА: устанавливать ngspice (apt/brew/AppImage — отдельно,
  ручная установка / bootstrap T001-T003).
- НЕ ДОЛЖНА: использовать PySpice / pyspice-фронтенд.
- НЕ ДОЛЖНА: предоставлять GUI / графики / визуализацию (числа only).
- НЕ ДОЛЖНА: трогать `bridge_edit` / `bridge_sweep` (T004b).
- НЕ ДОЛЖНА: реализовывать DC sweep, Noise, PSS, Monte-Carlo, .NOISE,
  .TF.
- НЕ ДОЛЖНА: персистить `Simulation` в БД (по-прежнему runtime VO).

## 4. Success criteria

- **RC OP:** `Vin=1V` через `R=1k, C=1u` → `V(out) ≈ 1.000 V` (±1%).
- **RC AC:** `fc = 1/(2π·R·C) ≈ 159.15 Hz`; в результате `|H(fc)| ≈
  -3 dB ±1 dB`.
- **SE-amp tran:** sin-вход 0.1 Vp, 1 kHz, 20 ms; на выходе синусоида
  с инверсией фазы и `|gain| ≥ 10` (грубая верификация
  работоспособности каскада, не подгонка под конкретное число —
  GENERIC_TRIODE — приблизительная модель).
- **SE-amp AC:** flat-зона в диапазоне 100 Hz – 10 kHz, спад на краях
  ≥ 3 dB (грубая ширина полосы).
- **Rectifier tran:** sin-вход 10 Vp, 50 Hz, 50 ms; на выходе
  однополупериодное напряжение, `max(V) ≥ 8 V`, `min(V) ≥ -0.5 V`.
- **CLI smoke:** `efactory bridge sim-run …` на каждом из 3
  netlist'ов завершает 0 exit code.
- **No-ngspice path:** на машине без ngspice — `SimulatorUnavailableError`
  с понятным сообщением.
- **Timeout path:** искусственно низкий `--timeout 0.001` →
  `SimulationFailedError(...timed out...)`.
- **Quality gates:** `uv run ruff check . && uv run ruff format --check . &&
  uv run mypy src && uv run pytest` зелёные, coverage ≥ 80% на `src/`
  (не падает относительно текущих 88.37%).

## 5. Key entities

- `AnalysisSpec` — discriminated union (`OpAnalysis | TranAnalysis |
  AcAnalysis`), discriminator `type`.
- `OpAnalysis`: только `type: Literal['op']`.
- `TranAnalysis`: `type='tran'`, `t_step: float`, `t_stop: float`,
  опционально `t_start: float = 0.0`, `uic: bool = False`.
- `AcAnalysis`: `type='ac'`, `sweep: Literal['dec','lin','oct']='dec'`,
  `n_points: int`, `f_start: float`, `f_stop: float`.
- `SimulationResult` (расширенный): три опциональные ветки результатов
  + invariant «ровно одна заполнена».
- `TimeSeries`, `AcSweep` — VO для tran / AC данных.
- `NgspiceSimulator` — adapter, реализует port `Simulator`.
- `RawFileParser` (внутренний для adapter) — парсит ngspice ASCII raw.

## 6. Assumptions & constraints

- `ngspice` установлен и доступен в `PATH` (проверено на 45.2;
  формат ASCII raw совместим с ngspice ≥ 26)
  (`AppManager.status(NGSPICE)` возвращает `AVAILABLE`); установка —
  отдельно от T008 (ручной `apt install ngspice` или
  bootstrap-скрипт).
- Netlist на входе — валидный SPICE без `.OP/.TRAN/.AC` директив
  (то, что отдаёт `kicad-cli sch export spice`).
- Симулятор пишет результаты во временный raw-файл в `sim/`
  рядом с netlist'ом; raw-файлы не очищаются автоматически (полезны
  для дебага).
- Жёсткий timeout по умолчанию **60 s** (CLI флаг `--timeout`,
  применяется через `subprocess.run(timeout=…)` внутри
  `AppManager.run`).
- Async / event loop — оставляем blocking `subprocess.run` внутри
  `asyncio.to_thread` через `AppManager.run` (как сделано в T009).
  Прогресса нет.
- Тест-фикстуры `se_amp.kicad_sch` / `rectifier.kicad_sch` —
  минимальный ручной s-expr (как `rc_filter.kicad_sch` в T004); не
  «рисованные в KiCad GUI» (открываемость в GUI желательна, но не
  обязательна — главное, что `kicad-cli sch export spice` отрабатывает).
- AC traces комплексные → храним парой real/imag (JSON-friendly).
  Magnitude/phase derives на стороне consumer.

## 7. Out of scope

- `bridge_edit_and_resim` / `bridge_sweep` (T004b — отдельная задача).
- DC sweep, `.NOISE`, `.PSS`, `.TF`, Monte-Carlo, sensitivity.
- PySpice / любой другой Python wrapper для ngspice (только
  subprocess).
- GUI, графики, plotting (Matplotlib / Plotly).
- Persistence `Simulation` в SQL (по-прежнему runtime VO).
- Установка ngspice (apt/brew/AppImage — bootstrap T001-T003 или ручной
  шаг).
- Поддержка LTspice / Qspice / спайс-движков отличных от ngspice.
- Кросс-платформенная отладка под Windows (Linux first; Windows позже
  через bootstrap T003).
- Параллельный запуск нескольких симуляций (один процесс ngspice
  в моменте).
- Бинарный raw-формат ngspice (только ASCII).

---

## Clarify (наполнено в диалоге T008 от 2026-05-18)

### Resolved

- **Q1: ngspice install.** Ставится отдельно от T008 — ручной
  `sudo apt install ngspice` (Linux dev) / `brew install ngspice`
  (macOS) / bootstrap T001-T003. T008 предполагает наличие; при
  отсутствии `AppManager.status(NGSPICE)` → `SimulatorUnavailableError`
  с понятным сообщением.
- **Q2: PySpice или subprocess.** Subprocess через
  `AppManager.run(ApplicationKind.NGSPICE, ...)`, без PySpice.
  Причины: heavy dep (CFFI/libngspice), деградировавший
  maintainership, неизвестная совместимость с Python 3.14;
  инфраструктура `AppManager` уже готова из T009.
- **Q3: контракт порта.** Один метод
  `run(netlist, analysis: AnalysisSpec)` с pydantic discriminated
  union. Будущее расширение под Noise/DC sweep без поломки сигнатуры.
- **Q4: CLI surface.** Разделение:
  - `bridge design-to-netlist <project>` — только экспорт,
  - `bridge sim-run <netlist> --analysis ...` — только симуляция,
  - `bridge design-to-sim` — композиция двух (с обязательным
    `--analysis`).
- **M-1: parsing ASCII raw.** Самописный парсер ngspice rawfile
  (формат документирован), ~50–100 строк, без новой зависимости.
- **M-2: timeout.** Default 60 s, CLI флаг `--timeout`.
- **M-3: persistence.** Не персистим в T008, держим в памяти.
  `Simulation.netlist_path` остаётся; пути к raw — внутренние для
  adapter'а.
- **M-4: AC complex.** Храним парой `traces_real` / `traces_imag`
  (JSON-friendly); magnitude/phase derives на стороне consumer.
- **M-5: ngspice command.** `ngspice -b <wrapper.cir>`; результаты
  пишутся через `.control … write <raw> all … .endc` блок.
- **M-6: SPICE-суффиксы CLI.** Парсим стандартные SPICE-суффиксы
  (`m`/`u`/`n`/`p`/`k`/`Meg`/`G`) — реалистично для физика.

### Resolved (продолжение, добавлено после Q1–Q4)

- **Q5: фикстуры SE-amp / rectifier.** Двухстадийная валидация:
  - на ходу разработки T008 — `kicad-cli sch export spice` как
    primary check (если экспорт даёт валидный netlist и ngspice
    переваривает — фикстура годная);
  - перед merge — Владимир открывает все 3 `.kicad_sch` в KiCad GUI
    и подтверждает визуально (один раз, финальный аппрув).
  Если GUI выявит проблему — правлю фикстуру и перепрогоняю
  acceptance-тесты.
- **Q6: куда складывать raw-файлы.** В `sim/<stem>.raw` рядом с
  netlist'ом (не временные). Размер на тест-фикстурах копеечный,
  дебагается удобно. В `.gitignore` соответствующих папок —
  `*.raw`.

---

## Analyze (заполнен 2026-05-18)

Базовая проверка фактов (на ходу):

- `ApplicationKind.NGSPICE` — есть в T009 (`src/domain/application.py:22`).
- `AppManager.run(kind, args, *, timeout_seconds: float | None = None)` —
  реальное имя параметра `timeout_seconds`, не `timeout`. Спека
  поправлена.
- ngspice 45.2 установлен (`/usr/bin/ngspice`); спека уточнена
  («≥ 39» → «проверено на 45.2, минимум подбираем по факту»).
- KiCad 10.0 simulation workflow: симулируемые symbol'ы используют
  свойства `Sim.Type` / `Sim.Device` / `Sim.Pins` / `Sim.Library` /
  `Sim.Params` / `Sim.Name`. `rc_filter.kicad_sch` подтверждает.

### Issues

- 🔴 **C-1. Tube-symbol в ручном s-expr — reality check для Phase 5.**
  `rc_filter.kicad_sch` использует только пассивные symbol'ы из
  `Simulation_SPICE` / `Device`. Для SE-amp нужен tube-symbol с
  привязкой к `.subckt` через `Sim.Library = <path>`, `Sim.Name =
  GENERIC_TRIODE`, `Sim.Pins = 1=P 2=G 3=K`. Ручной s-expr такого
  symbol'а — нетривиально, и `kicad-cli sch export spice` должен
  правильно встроить `.include` библиотеки модели в netlist.
  Объём ручной работы и риск, что что-то «не подцепится», на
  порядок выше, чем для `rc_filter`.
  **Mitigation:** перед Phase 5 — мини-«пилот»: соберу руками
  одну фикстуру (`se_amp_minimal.kicad_sch`) с GENERIC_TRIODE,
  прогоню через kicad-cli + ngspice, посмотрю на результат. Если
  взлетает за разумное время — пишу остальные. Если нет — вместе
  решаем: (a) rectifier делаем на диоде из `Simulation_SPICE` без
  tube; (b) Phase 5 переключается на готовые `.cir` файлы как
  fixtures (минуя KiCad для SE-amp), документируем как known limit;
  (c) Владимир рисует фикстуры в GUI и сохраняет — самый дорогой
  по времени, но самый надёжный путь.

- 🟡 **W-1. ASCII raw в batch.** `ngspice -b -r out.raw` по
  умолчанию пишет **binary** raw. Чтобы ASCII, нужно либо
  `set filetype=ascii` в `.spiceinit` (CWD), либо в `.control`-блоке
  внутри wrapper'а (исходный план в §3 FR). `.control`-блок
  не загрязняет глобальный state — оставляю в спеке как было,
  фиксирую в Analyze.

- 🟡 **W-2. Очистка `.end` из исходного netlist.** ngspice разрешает
  одно `.end` на сессию. KiCad netlist может содержать своё `.end`.
  Wrapper делает `.include <netlist>` + свои директивы + `.end`. Если
  внутри netlist'а уже стоит `.end` — будет ошибка / преждевременный
  выход. Adapter должен либо удалять `.end` из netlist'а перед
  `.include`, либо вставлять содержимое netlist'а текстуально вместо
  `.include`. Проверю экспериментально на rc_filter в Phase 3 и решу.

- 🟡 **W-3. Миграция callers `run_op` в Phase 2.** Удаление метода
  ломает 3 точки: `StubSimulator`, use case `design_to_sim`, любые
  тесты. Все три мигрируют атомарно в Phase 2 одним коммитом, чтобы
  не было промежуточного red-состояния на main.

- 🟡 **W-4. Судьба `StubSimulator` после T008.** Был placeholder'ом до
  реального адаптера; после T008 — `NgspiceSimulator` становится
  default в `composition.main`. Варианты:
  - (a) удалить StubSimulator целиком (минус 30 строк, но в CI на
    машине без ngspice тесты use case `design_to_sim` без
    `requires_ngspice`-маркера сломаются);
  - (b) оставить как тестовый double `FailingSimulator`, бросающий
    `SimulatorUnavailableError`, под `tests/doubles/`;
  - (c) ввести `InMemorySimulator` (тестовый double), возвращающий
    предсказуемый результат — для unit-тестов use case
    `design_to_sim`.
  **Предлагаемый план:** (c). `InMemorySimulator` живёт в
  `tests/doubles/`, не в production-коде. `StubSimulator` удаляется.
  `composition.main` инжектит `NgspiceSimulator`.

- 🔴 **C-2. Invariant «ровно одна ветвь» в SimulationResult и
  miграция тестов.** Расширение `SimulationResult` ломает любые
  тесты, конструирующие `SimulationResult()` с пустым
  `operating_points={}`. Нужен полный аудит callers/тестов и
  миграция в Phase 1.

- 🟢 **N-1. `Meg` суффикс.** SPICE: `M = milli` (НЕ mega!), `Meg =
  mega`. Самая распространённая ошибка при ручном вводе. Парсер
  CLI должен:
  - быть case-insensitive по основанию (`MEG`/`Meg`/`meg` → mega);
  - НЕ путать `M`/`m` (milli) с `Meg` (mega).
  Зафиксирую в unit-тестах парсера.

- 🟢 **N-2. Coverage.** Адаптер `NgspiceSimulator` (~200 строк) +
  parser (~100 строк) — большая площадь нового кода. Чтобы не
  уронить ниже 80%, parser покрываем плотно unit-тестами на
  фиксированных ASCII-raw фикстурах, adapter — частично unit
  (wrapper generation, error handling) + integration через ngspice
  под маркером.

- 🟢 **N-3. ngspice разные версии.** Формат ASCII raw стабилен с
  давних версий (≥ 26 точно), 45.2 совместим. Минимальную версию
  не указываем жёстко — в Assumptions: «проверено на 45.2;
  параметры формата raw совместимы с 26+».

### Action items до Implement

1. (W-1, W-2) Оставляем как known limits, проверяем на ходу в Phase 3.
2. (W-3) Атомарность миграции callers `run_op` — Phase 2 одним
   коммитом.
3. (W-4) **Согласовано 2026-05-18 (с корректировкой в Phase 2):**
   `StubSimulator` удаляется в Phase **3** (одновременно с
   появлением `NgspiceSimulator`, иначе `composition.main`
   разваливается). В Phase 2 — `StubSimulator` переписан под новый
   контракт `run(netlist, analysis, *, timeout_seconds=60.0)`,
   бросает `SimulatorUnavailableError` с message `"T008 Phase 3:
   ngspice adapter not implemented yet"`. `InMemorySimulator` в
   `tests/doubles/` — **отменён (YAGNI)**: `FakeSimulator` нужен
   только в одном test-файле, остаётся inline в
   `test_design_to_sim.py`. В Phase 3 `composition.main` инжектит
   `NgspiceSimulator` как default.
4. (C-1) **Согласовано 2026-05-18:** Phase 5 стартует с пилота
   `se_amp_minimal.kicad_sch` (ручной s-expr) → kicad-cli +
   ngspice. Если взлетает — продолжаем по плану; если нет — fallback
   (a/b/c) решаем по ситуации.
5. (C-2) **Audit callers (2026-05-18, в начале Phase 1):**
   - **Конструкторы `SimulationResult`** (под invariant):
     - `tests/unit/domain/test_simulation.py:61,66,74` (3 случая,
       мигрируют тривиально — `operating_points={...}`).
     - `tests/unit/application/test_design_to_sim.py:127`
       (`SimulationResult(operating_points={'V(out)': 3.3})` —
        invariant ОК).
   - **Callers `Simulator.run_op`** (мигрируют в Phase 2):
     - `src/application/design_to_sim.py:81`.
     - `src/adapters/outbound/stub_simulator/` (удаляется).
     - `src/composition/main.py:45,117` (DI на `NgspiceSimulator`).
     - `src/adapters/inbound/cli/app.py:76,121` (compose root).
     - `tests/unit/application/test_design_to_sim.py` —
       `FakeSimulator` переписать на `run(netlist, analysis)`.
     - `tests/integration/adapters/stub_simulator/` (удаляется).

---

## Phases

1. **Phase 1 — Domain. ✅ Done 2026-05-18.** `AnalysisSpec` union
   (Op/Tran/Ac + discriminator), `TimeSeries` + `AcSweep` VO,
   расширение `SimulationResult` тремя ветвями + invariant «ровно
   одна заполнена», audit callers (только domain-уровень, миграция
   port/adapter — Phase 2). 39 новых тестов; 413 passed, coverage
   88.73% (≥80%). Все 4 quality gates зелёные.
2. **Phase 2 — Port. ✅ Done 2026-05-18.** `Simulator.run(netlist,
   analysis, *, timeout_seconds=60.0) → SimulationResult` (вместо
   `run_op`). `StubSimulator` переписан под новый контракт (бросает
   `SimulatorUnavailableError` с пометкой «Phase 3»). Миграция
   `design_to_sim` use case (`run(netlist, OpAnalysis())`).
   `FakeSimulator` inline в `test_design_to_sim.py` переписан под
   новый контракт. `composition.main` не тронут — StubSimulator на
   месте до Phase 3. 415 passed, coverage 88.73%, все quality gates
   зелёные.
3. **Phase 3 — Adapter. ✅ Done 2026-05-18.** Новый пакет
   `src/adapters/outbound/ngspice/`: `raw_parser.py` (ASCII raw →
   `SimulationResult` через `_Header`/`_Variable` dataclass'ы),
   `wrapper.py` (генератор обёртки с очисткой `.end` из netlist'а
   case-insensitive, `.control { set filetype=ascii; run; write … all;
   exit }.endc`), `simulator.py` (адаптер через `AppManager.run` +
   маппинг `ApplicationNotInstalledError → SimulatorUnavailableError`,
   `ApplicationStartError` / non-zero exit / отсутствие raw →
   `SimulationFailedError`). `StubSimulator` удалён;
   `composition.main` переключён на `NgspiceSimulator(app_manager)`.
   Тесты: 10 parser unit + 5 wrapper unit + 6 adapter с FakeAppManager
   + 4 integration с реальным ngspice (skip-if-no-ngspice).
   **Reality-check находка:** фикстура `rc_filter.kicad_sch` (T004)
   экспортируется со всеми unconnected nets (`unconnected-_R1-Pad1_`
   и т.п.) — wires в s-expr не реально соединяют pins. ngspice
   падает. T004 acceptance проходил только потому, что StubSimulator
   не симулировал. **Phase 5 первым делом чинит rc_filter.** e2e тест
   `tests/e2e/walking_skeleton/test_bridge_design_to_sim.py` адаптирован
   под текущее поведение (exit 2 + понятная ошибка) с TODO. 437
   passed, coverage 88.77%, все quality gates зелёные.

4. **Phase 4 — CLI. ✅ Done 2026-05-18.** Use case'ы расщеплены:
   `design_to_netlist` (только экспорт), `sim_run` (только симуляция
   готового netlist), `design_to_sim` — композиция export + sim (теперь
   с обязательным `analysis: AnalysisSpec` и опциональным
   `timeout_seconds`). SPICE-суффикс parser
   (`adapters/inbound/cli/spice_units.py`): поддержка `f/p/n/u/m/k/Meg/G/T`
   + игнор unit-hint после префикса (`20mA`, `1kHz`, `1uF`),
   case-insensitive, не путает `m` с `Meg`. CLI: новая команда
   `bridge design-to-netlist`, два sub-sub-app'а `bridge sim-run
   {op,tran,ac}` и `bridge design-to-sim {op,tran,ac}` (первый случай
   3-уровневой иерархии typer в efactory). Маппинг ошибок:
   `ProjectNotFoundError → exit 1`, остальные bridge-ошибки + SPICE
   parse + pydantic ValidationError → exit 2. Session-логи:
   `bridge.design_to_netlist`, `bridge.sim_run.{op,tran,ac}`,
   `bridge.design_to_sim.{op,tran,ac}`. Существующие e2e тесты
   адаптированы под новый синтаксис (`design-to-sim op rc_test ...`).
   485 passed (+48), coverage 87.71% (≥80%; снижение из-за новых CLI
   веток, не покрытых отдельными тестами — закроется в Phase 5).
5. **Phase 5 — Fixtures + e2e.** **Перво-наперво** — починка
   `rc_filter.kicad_sch` (после Phase 3 reality check: unconnected
   nets); только потом `se_amp.kicad_sch`, `rectifier.kicad_sch`
   (пилот SE-amp по C-1) и acceptance-тесты (§4).
