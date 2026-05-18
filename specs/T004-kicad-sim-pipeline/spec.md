## Spec: T004 — KiCad → SPICE pipeline (split-scope, без ngspice)

**Статус:** Draft (готов к Clarify)
**Дата создания:** 2026-05-18
**Связанные документы:**
- `CONCEPT.md` §2.1 (kicad-sch-api), §2.3 (SPICEBridge), §4 (структура
  проекта со `schematic/`, `sim/`).
- `BACKLOG.md` → T004 (Фаза 1a — MVP-ядро).
- `specs/T009-platform-and-apps/spec.md` — `app_manager.run(KICAD_CLI,
  args)` используется здесь для `kicad-cli sch export netlist`.
- Будущее: **T008** доделает реальную симуляцию через ngspice / PySpice
  (split-scope договорённость 2026-05-18).

---

### 1. Overview

T004 в BACKLOG смешивает «дать pipeline» и «реально симулировать
ngspice'ом». Договорились **split** (2026-05-18): T004 = pipeline
framework + export `.kicad_sch → SPICE netlist` через kicad-cli;
T008 = реальный ngspice прогон + извлечение результатов через PySpice.

Здесь:
1. Domain `Simulation` aggregate (status, paths, optional results).
2. Outbound ports `SchematicExporter` (netlist export) + `Simulator`
   (interface, stub adapter в T004).
3. Adapter `KicadCliSchematicExporter` — `app_manager.run(KICAD_CLI,
   ['sch', 'export', 'netlist', '--format', 'spice', ...])`.
4. Application use case `design_to_sim` — export + (stub) simulate.
5. CLI `efactory bridge design-to-sim <project> --schematic <path>`.
6. Тестовый `.kicad_sch` RC-фильтр в `tests/fixtures/` для e2e
   acceptance: export даёт SPICE netlist с R/C/V_source.

**НЕ делаем здесь:** `bridge_edit_and_resim`, `bridge_sweep`,
реальные ngspice результаты — после T008 (когда симулятор работает,
edit/sweep осмысленны).

### 2. User Stories

- **«Превратить схему в netlist.»** Как разработчик с готовым
  `.kicad_sch`, я хочу `efactory bridge design-to-sim demo
  --schematic schematic/SE-amp.kicad_sch` — получить SPICE netlist
  в `sim/SE-amp.cir` для дальнейшей обработки.
- **«Запустить симуляцию.»** То же CLI вернёт «симуляция: not yet
  implemented (T008)» — flow готов, симулятор — следующая задача.
- **Bridge для LLM (Phase 1b).** chat-клиент будет звать
  `design_to_sim` use case напрямую через MCP tool wrapper.

### 3. Functional Requirements

#### Domain

- ДОЛЖНА: `domain/simulation.py`:
  ```python
  class SimulationStatus(StrEnum):
      PENDING = 'pending'
      NETLIST_READY = 'netlist_ready'
      SIMULATED = 'simulated'   # T008
      FAILED = 'failed'

  class Simulation(BaseModel):
      model_config = ConfigDict(frozen=True)
      id: UUID
      project_id: UUID
      schematic_path: Path     # абсолют или относительный к проекту
      netlist_path: Path | None  # появляется после export
      status: SimulationStatus
      created_at: datetime
      # results: dict | None — заполнит T008 (placeholder в T004).
  ```

#### Outbound port: `SchematicExporter`

- ДОЛЖНА: `ports/outbound/schematic_exporter.py`:
  ```python
  class SchematicExporter(Protocol):
      async def export_spice_netlist(
          self, schematic: Path, output: Path,
      ) -> Path:
          """Экспорт `.kicad_sch` → SPICE netlist.
          Возвращает фактический путь `output` (для chain).
          Бросает SchematicExportError при сбое.
          """
          ...
  ```
- ДОЛЖНО: контрактное исключение `SchematicExportError`.

#### Outbound port: `Simulator` (T008 заполнит реализацией)

- ДОЛЖНА: `ports/outbound/simulator.py`:
  ```python
  class Simulator(Protocol):
      async def run_op(self, netlist: Path) -> SimulationResult: ...
      # async def run_tran(...) → T008
      # async def run_ac(...) → T008
  ```
- ДОЛЖНА: `SimulationResult` (frozen VO, минимальный shape — T008
  расширит):
  ```python
  class SimulationResult(BaseModel):
      operating_points: dict[str, float]
      # waveforms: dict — T008
  ```
- ДОЛЖНО: `SimulatorUnavailableError` — stub бросает («T008 не
  реализован»).

#### Adapter: `KicadCliSchematicExporter`

- ДОЛЖНА: `adapters/outbound/kicad_cli/`:
  - Конструктор: `app_manager: AppManager` (DI).
  - `export_spice_netlist(schematic, output)`:
    ```python
    args = ['sch', 'export', 'netlist',
            '--format', 'spice',
            '--output', str(output),
            str(schematic)]
    result = await app_manager.run(ApplicationKind.KICAD_CLI, args)
    if result.returncode != 0:
        raise SchematicExportError(result.stderr or result.stdout)
    return output
    ```

#### Adapter: `StubSimulator`

- ДОЛЖНА: `adapters/outbound/stub_simulator/`:
  - `run_op(netlist)` → `SimulatorUnavailableError` с пометкой
    «Real simulator arrives with T008».
  - Это «placeholder, чтобы pipeline сам по себе тестировался без
    реального ngspice».

#### Application use case

- ДОЛЖНА: `application/design_to_sim.py`:
  ```python
  async def design_to_sim(
      *,
      project_name: str,
      schematic: Path,
      netlist_output: Path | None = None,
      repo, manifest_repo, exporter, simulator,
      session_logger?,
  ) -> Simulation
  ```
  - get_project (path lookup) → resolve absolute paths
    (`schematic` relative to project path → absolute).
  - default netlist_output: `<project_path>/sim/<schematic.stem>.cir`.
  - `mkdir parents=True exist_ok=True` для netlist dir.
  - `exporter.export_spice_netlist(schematic, netlist_output)` →
    Simulation.status = NETLIST_READY.
  - Try `simulator.run_op(netlist)`:
    - SimulationResult → Simulation.status = SIMULATED.
    - SimulatorUnavailableError → status остаётся NETLIST_READY,
      CLI напечатает hint про T008.
  - Возвращает `Simulation`.

#### CLI

- ДОЛЖНА: новый Typer subapp `bridge`:
  ```
  efactory bridge design-to-sim <project_name>
    --schematic PATH
    [--netlist-output PATH]
  ```
- Session-log event: `bridge.design_to_sim`.
- Вывод:
  ```
  Exported netlist: /path/to/sim/SE-amp.cir
  Simulation: not yet implemented (T008)
  ```

#### Composition

- Wire `KicadCliSchematicExporter(app_manager)` и `StubSimulator()`
  в build_app.

### 4. Success Criteria

- TDD outside-in.
- 5-step гейт зелёный.
- Coverage ≥ 80%.
- **Acceptance e2e:**
  - Подготовлен `tests/fixtures/rc_filter.kicad_sch` — простой RC
    (R + C + V_source DC) в KiCad 10 формате.
  - `efactory project create rc_test` → создание проекта.
  - `cp rc_filter.kicad_sch <project>/schematic/rc_filter.kicad_sch`.
  - `efactory bridge design-to-sim rc_test --schematic schematic/
    rc_filter.kicad_sch` → exit 0.
  - `<project>/sim/rc_filter.cir` существует, содержит `R1`, `C1`,
    `V1` (или подобные KiCad-default имена компонентов).
  - stdout содержит «not yet implemented (T008)» подсказку.
- Skip-if-no-kicad для e2e: если KiCad AppImage отсутствует на
  тестовой машине, e2e skip'нется через `app status` check.

### 5. Key Entities

- `Simulation`, `SimulationStatus`, `SimulationResult` — domain.
- `SchematicExporter` (Protocol) + `KicadCliSchematicExporter`
  (adapter).
- `Simulator` (Protocol) + `StubSimulator` (placeholder; T008 даст
  реальную реализацию через PySpice).
- `SchematicExportError`, `SimulatorUnavailableError` — контрактные
  исключения портов.
- `design_to_sim` — application use case.
- CLI subapp `bridge` (расширится в T004b/T008 для
  edit-and-resim/sweep).

### 6. Assumptions & Constraints

- KiCad-cli доступен через `app_manager.run(KICAD_CLI)` (T009
  KICAD_CLI fallback через KiCad AppImage).
- `.kicad_sch` файл предполагается валидным; невалидный → kicad-cli
  вернёт non-zero exit → `SchematicExportError`.
- Schematic path относительный к project path; netlist_output по
  default — `<project>/sim/<schematic.stem>.cir`.
- Caller (пользователь / chat-клиент) сам положил `.kicad_sch` в
  `<project>/schematic/`. Pipeline не создаёт схему «с нуля» — это
  отдельная задача (T027 templates).

### 7. Out of Scope

- **Реальная симуляция** через ngspice / PySpice / SPICEBridge —
  **T008** (split-scope договорённость).
- **`bridge_edit_and_resim`** — после T008 (нужна симуляция чтобы
  edit имел смысл; и kicad-sch-api dep для манипуляций).
- **`bridge_sweep`** — после T008 (нужна симуляция для каждого шага).
- **`model_assign`** — T005 (отдельная задача в BACKLOG).
- **Auto-сравнение результатов** — Phase 2 (T021).
- **kicad-sch-api dep** — пока не нужен (export через kicad-cli
  достаточен для T004 scope). Появится в T004b (edit/sweep) и T005.
- **Visualisation результатов** — Phase 2 (T024).
- **MCP tool wrapper** для chat-клиента — Phase 1b.

---

### Clarify

#### Open questions

##### 1. Domain.Simulation в DB / SQL?

Сейчас Project хранится в SQL + manifest. Simulation — это runtime
артефакт (запустил → получил netlist + результаты). Хранить в SQL/
manifest или нет?

- **(A)** Только runtime — Simulation возвращается из use case,
  netlist на диске, ничего не persist'им в DB. Проще.
- **(B)** Хранить в SQL + manifest (`project.yaml → simulations: [...]`).
  История симуляций видна после restart.

**Предлагаемый дефолт:** **(A) runtime only** для T004. Persistence
— отдельная задача после T008 (когда результаты реально интересно
хранить). Сейчас фокус — pipeline.

##### 2. `tests/fixtures/rc_filter.kicad_sch` — где брать?

KiCad 10 schematic — s-expression формат, ~50-100 строк для RC.

- **(A)** Я составлю вручную (текстом) минимально валидный
  `.kicad_sch` с R, C, V_source.
- **(B)** Открыть KiCad GUI, нарисовать RC, сохранить — но это
  blocking shell-acción, не воспроизводимо.
- **(C)** Use existing template из KiCad library examples.

**Предлагаемый дефолт:** **(A) вручную**. Минимальный валидный
schematic ~50 строк. Тестируется тем, что kicad-cli sch export
проходит без ошибок.

##### 3. CLI имя subcommand: `bridge` vs `sim` vs `pipeline`?

- **(A)** `efactory bridge design-to-sim ...` — bridge с дефисом.
- **(B)** `efactory bridge design_to_sim ...` — underscore (Python
  style).
- **(C)** `efactory sim run ...` — короче.
- **(D)** `efactory pipeline design-to-sim ...` — explicit.

**Предлагаемый дефолт:** **(A) `bridge design-to-sim`** — в BACKLOG
`bridge_design_to_sim`, в CLI «bridge» это subapp namespace,
«design-to-sim» команда (дефис как у `decision add` / `tube show`).

##### 4. `--netlist-output` — обязателен или default?

- **(A)** Обязателен.
- **(B)** Default `<project>/sim/<schematic.stem>.cir`, можно override.

**Предлагаемый дефолт:** **(B)** — sensible default. Pipeline
зрит про `<project>/sim/`.

##### 5. Что если `<project>/sim/` нет?

`mkdir parents=True exist_ok=True` или error?

**Предлагаемый дефолт:** mkdir. Pipeline сам создаёт sim/ при
первом запуске (это часть проектной структуры).

##### 6. Phasing

- **(A) Один phase** — даже с stub Simulator это компактно.
- **(B) Два phase:** domain/ports/exporter; CLI/use case/e2e.

**Предлагаемый дефолт:** **(A)**.

##### 7. SimulatorUnavailableError — error или success?

Use case ловит → возвращает Simulation в status=NETLIST_READY. CLI
exit 0 («exported, simulation pending T008»). Это **не ошибка**,
это intended состояние Phase 1a.

- **(A)** Success exit 0 с info-message.
- **(B)** Exit 0 с warning-message.
- **(C)** Exit code 2 «partial completion».

**Предлагаемый дефолт:** **(A) success exit 0** — netlist получен,
это завершённый шаг. T008 добавит реальную симуляцию.

---

### Analyze (после Clarify)
