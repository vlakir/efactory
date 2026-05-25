# Spec: T016 — Dynamic project context в Claude Code

**Статус:** Analyzed
**Дата создания:** 2026-05-25
**Связанные документы:**
- `BACKLOG.md → T016` (формулировка задачи).
- `BOARD.md → T013` (Claude Code runtime — static system prompt уже работает).
- `docs/container-boundary.md` (граница образ/host, persist mounts).
- `docker/runtime-agent-CLAUDE.md` (текущий static prompt).
- `DECISIONS.md` 2026-05-24 («Tool surface = Bash + efactory CLI + filesystem, не MCP»).

---

## 1. Overview

Runtime-агент Claude Code сейчас получает только **статический** system
prompt (роль РЭА-проектировщика, перечень доступных тулзов). Он не
знает, **в каком проекте** сейчас работает пользователь, какие у этого
проекта файлы и какие были последние симуляции. T016 добавляет
**динамический project context**: SessionStart hook сканирует cwd
агента, определяет «текущий проект» (по концептуально-однозначному
правилу — это subdir `/workspace/<NAME>/`), и инжектирует в system
prompt сессии короткую сводку (project name, ключевые файлы,
последний sim result). Параллельно стандартизуется
infrastructure для записи sim-результатов в проект — чтобы было
**откуда** их читать.

## 2. Сценарии использования

- Vladimir запускает `./efactory-up --agent se-amp-demo` (или другой
  способ указать проект — определяется в clarify §Q1). Контейнер
  стартует в `/workspace/se-amp-demo/`. Claude Code при старте читает
  cwd, hook генерирует динамический блок — агент знает, что работает
  над `se-amp-demo`, и сразу видит, что в проекте `se_amp.kicad_sch`,
  `se_amp.kicad_pro`, файлы SPICE-моделей.
- Vladimir запустил use case `analyze_distortion_spectrum`
  (T131-стиль), тот записал результат в
  `/workspace/se-amp-demo/.efactory/sim-results/2026-05-25T14-30Z-thd.json`.
  В следующей сессии Claude Code hook видит этот файл и упоминает в
  динамическом контексте: «последний sim: THD analysis на
  `se_amp.kicad_sch`, выполнено вчера, THD 9.6%». Агент не угадывает,
  что было сделано раньше — у него есть фактическая запись.
- Vladimir переключается на другой проект (`docker run` нового
  контейнера с `-w /workspace/preamp-prototype/`). Старый контекст
  `se-amp-demo` не утекает — каждая сессия читает cwd заново, нет
  глобального «active project» persisted state.

## 3. Functional Requirements

**Hook (динамический контекст):**

- ДОЛЖЕН: SessionStart hook исполняется при каждом старте сессии
  Claude Code внутри `efactory:linux`.
- ДОЛЖЕН: hook определяет «текущий проект» по cwd: если cwd —
  `/workspace/<NAME>/` или путь внутри `/workspace/<NAME>/`, project
  name = `<NAME>` (первый сегмент после `/workspace`).
- ДОЛЖЕН: hook сканирует project root и формирует block:
  - project name + абсолютный путь;
  - ключевые файлы по расширениям: `*.kicad_pro`, `*.kicad_sch`,
    `*.kicad_pcb`, `*.cir`, `*.spice`, `*.subckt`, `*.lib`,
    `*.FCStd` (FreeCAD), `*.geo` (Gmsh), `*.sif` (Elmer), `*.pro`
    (GetDP). Глубина — top-level + 1 (subdir) для основных, чтобы не
    раздувать.
  - последние N (default N=3) sim-результатов из
    `<PROJECT_ROOT>/.efactory/sim-results/` (если каталог существует),
    отсортированные по timestamp убыванию.
- ДОЛЖЕН: вывести stdout в формате Claude Code SessionStart hook
  protocol:
  ```json
  {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<TEXT>"}}
  ```
- ДОЛЖЕН: если cwd НЕ внутри `/workspace/<NAME>/` (например, cwd =
  `/workspace` или `/`), генерировать context block: «No active
  project (cwd=…). Available projects in `/workspace/`: foo, bar.
  Use `./efactory-up --agent <NAME>` to start a session in a
  specific project.».
- НЕ ДОЛЖЕН: при ошибке (отсутствует cwd, нет прав, etc) валить
  Claude Code — graceful degradation, hook возвращает non-zero, сессия
  стартует без extra context. Stderr с диагностикой допустим (попадёт
  в Claude Code stderr-лог, не в prompt).
- ДОЛЖЕН: исполняться < 1 s на типичном проекте (≤ 100 файлов в
  scope). Timeout в settings.json — 10 s с запасом.

**Sim-results infrastructure:**

- ДОЛЖНА: появиться канонический путь
  `<PROJECT_ROOT>/.efactory/sim-results/`, куда use cases пишут JSON-
  результаты симуляций.
- ДОЛЖНА: появиться канонический JSON schema (schema_version = 1):
  - `schema_version: int`
  - `timestamp: str` (ISO 8601 UTC, e.g. `2026-05-25T14:30:00Z`).
  - `analysis_type: str` (`tran`, `ac`, `dc`, `op`, `four`, `thd`,
    `fem_field`, `leakage`, `bracket_sheet_metal`, etc — open list).
  - `source_file: str` (path к `.kicad_sch`/`.cir`/`.fcstd` relative
    к project root).
  - `tool: str` (`ngspice`, `kicad-cli`, `getdp`, `elmer`,
    `freecadcmd`).
  - `tool_version: str | null`.
  - `duration_seconds: float`.
  - `summary: str` (одна-две строки, human-readable).
  - `metrics: dict[str, Any] | null` (optional structured data —
    специфика на use case).
  - `artefacts: list[str]` (paths к raw logs, plots, etc — относительно
    `.efactory/sim-results/`).
- ДОЛЖЕН: появиться **Python writer** в `src/efactory/adapters/
  outbound/sim_results/` (или сравнимый путь — clarify §Q4):
  - `SimResultsWriter` (или `SimResultsRepository`-port + adapter, если
    идём через гексагон) с методом `write(result: SimResult,
    project_root: Path) -> Path`.
  - Атомарность: запись в `*.json.tmp` → `os.replace` финальный.
  - Имя файла: `<TIMESTAMP>-<analysis_type>.json` (TIMESTAMP в
    sortable format `2026-05-25T14-30-00Z`).
- ДОЛЖНА: появиться **интеграция как минимум в один existing use
  case** (clarify §Q5 — какой), чтобы доказать end-to-end pipeline.
- МОЖЕТ: появиться `SimResult` domain VO в `src/efactory/domain/sim_results.py`.

**Конфигурация:**

- ДОЛЖЕН: settings.json с hook'ом гарантированно подхватываться
  внутри образа, даже при persist mount поверх `/efactory/.claude/`
  (clarify §Q2 — финальный механизм).
- ДОЛЖЕН: hook script запекаться в образ, доступен по абсолютному
  пути (`/opt/efactory/scripts/session-start-hook.sh`).

## 4. Success Criteria

- `./efactory-up --agent <PROJECT>` (или эквивалентная команда, §Q1)
  → в стартовом system prompt Claude Code видна динамическая секция
  с project name, файлами, sim-результатами. Проверяется по
  `/CLAUDE.md`-style sanity: спросить агента «какой у меня сейчас
  проект и какие в нём файлы», получить корректный ответ без
  дополнительной разведки.
- Use case записывает sim-результат в
  `<PROJECT_ROOT>/.efactory/sim-results/`, файл проходит JSON schema
  validation (pydantic / dataclass + unit test).
- При запуске Claude Code в `/workspace` (без выбранного проекта)
  hook не падает, контекст содержит «No active project, available:
  …».
- Hook latency на demo-проекте — < 200 ms (cold start hook + scan).
- Pre-push gates (`ruff`, `format`, `mypy src`, `pytest` ≥80% cov)
  зелёные.
- Integration test (внутри `efactory:linux`): smoke на демо-проекте —
  hook stdout валидный JSON, содержит `additionalContext` с
  ожидаемой подстрокой (project name).

## 5. Key Entities

- **Project root** — `/workspace/<NAME>/`. Не имеет marker-файла, NAME
  — первый segment после `/workspace`. Subdir'ы внутри проекта не
  считаются отдельными проектами.
- **SimResult** — domain VO (или dataclass), описанный в §3.
- **SimResultsWriter** — outbound adapter (или просто helper —
  clarify §Q4), пишет SimResult в `.efactory/sim-results/`.
- **SessionStartContext** — bash-script `session-start-hook.sh`,
  читает cwd + project root, формирует JSON output. Внутри —
  bash, не Python: запускается до интерпретатора Python в Claude
  Code lifecycle, должен быть быстрым и low-dependency.

## 6. Assumptions & Constraints

- Claude Code версии 2.1.150+ (как pin в Dockerfile, T013).
- Hook scope = SessionStart на `startup` + опционально `resume`/`clear`
  (clarify §Q3). Default — все `source`.
- cwd Claude Code в `--agent` режиме — `/workspace/<PROJECT>/` (T013
  устанавливает `-w /workspace`, T016 модифицирует).
- Один контейнер = одна Claude Code сессия = один проект. Переключение
  проектов в рамках одной сессии — НЕ scope T016 (это будет `/project
  use` из T014).
- Размер `additionalContext` — рекомендуем держать < 2 KB (несколько
  файлов + последние 3 sim-результата), чтобы не раздувать каждый
  запрос. Hard cap не нужен — clarify §Q6.
- Sim-results — append-only (старые не перезаписываются), очистка —
  ручная или через follow-up задачу (не T016).

## 7. Out of Scope

- `/project use NAME` slash-команда внутри сессии — T014.
- `/project create` slash-команда — T014.
- Multi-project switching внутри одной сессии — T014.
- GUI integration (открытые `.kicad_sch` в KiCad GUI) — разные
  контейнеры, агент не видит GUI state. Out of scope **навсегда** в
  текущей containerization-модели.
- Real-time tail последних sim-результатов в active сессии (когда
  новый sim запускается во время разговора) — не делаем, hook
  работает только на старте сессии. Можно довести через PostToolUse
  hook позже (BACKLOG).
- Sim-results cleanup / rotation — отдельная задача, BACKLOG если
  понадобится.
- Поддержка не-`/workspace/<NAME>/` layout (например, агент запущен
  в `/tmp` или прямо в `/`) — graceful no-op, без специальной логики.

---

## Clarify (заполняется Claude)

### Open questions

- **Q1. Как переключать project в `efactory-up --agent`?**
  Варианты:
  - (a) `./efactory-up --agent NAME` — позиционный аргумент, контейнер
    стартует с `-w /workspace/NAME/`. Если `NAME` не существует —
    `fail`.
  - (b) `./efactory-up --agent --project NAME` — explicit флаг.
  - (c) `./efactory-up --agent` (без аргумента) — стартует в
    `/workspace/`, агент сам решает через cd (но это требует от
    агента диалога — больше шагов).
  - (d) `./efactory-up --agent` (без аргумента) — если есть env
    `EFACTORY_DEFAULT_PROJECT`, использует его; иначе fallback на
    `/workspace/`.
  Рекомендую **(a)** — минимум магии, согласовано с тем, что hook
  читает cwd.

- **Q2. Где settings.json с hook'ом, чтобы он гарантированно был
  активен внутри образа?**
  Тонкость: `/efactory/.claude/` mount'ится с host'а
  (`$HOME/efactory-state/claude/`). Если запечь settings.json в образ
  по `/efactory/.claude/settings.json`, persist mount поверх перетрёт
  его. Варианты:
  - (a) Bootstrap-step в `efactory-up --agent`: если host
    `$HOME/efactory-state/claude/settings.json` не существует —
    скопировать embedded template (из образа или из репо efactory).
    Пользователь может его редактировать.
  - (b) Запечь в образ `~/.claude/settings.json` (=
    `/opt/efactory/.claude/settings.json` или `/root/.claude/`), не
    под `CLAUDE_CONFIG_DIR`. Но тогда наш `CLAUDE_CONFIG_DIR=/efactory/
    .claude` override его игнорирует.
  - (c) Положить settings.json в **project scope** — внутри **каждого**
    `/workspace/<NAME>/.claude/settings.json`. Это user-managed файл,
    появляется через `/project create` (T014) — но T014 не сделан;
    создавать `.claude/settings.json` руками неудобно.
  - (d) Использовать **CLI флаг** `claude --settings-file
    /opt/efactory/.claude-defaults/settings.json` если такой
    существует (надо проверить — claude-code-guide агент не упомянул).
  Рекомендую **(a)** — explicit bootstrap, файл виден пользователю в
  persist state, редактируем.

- **Q3. SessionStart `source` filter.**
  Hook срабатывает на `startup` / `resume` / `clear` / `compact`.
  Запускать на все четыре, или только на `startup` + `resume`? На
  `clear` — динамический контекст должен ли перегенериться?
  Рекомендую **все четыре** (clear / compact = de facto «новая
  сессия», context нужен).

- **Q4. SimResultsWriter — port в гексагоне или плоский helper?**
  В hex архитектуре корректно — port `SimResultsRepository` + adapter
  `FileSystemSimResults`. Но это +2 файла + Protocol на одну операцию
  записи JSON. Альтернатива — простой module-function в
  `src/efactory/infrastructure/sim_results.py` (если у нас есть
  `infrastructure/` — иначе создать). Какой стиль для tooling-
  адаптеров с тривиальной логикой? Рекомендую **port + adapter** —
  будем согласованы с GetDpFemSolver / PyOpenMagneticsAnalytics
  (T113), цена низкая, тестируемость выше.

- **Q5. В какой existing use case интегрируем SimResultsWriter, чтобы
  доказать end-to-end?**
  Кандидаты (use cases, реально запускающие симуляции):
  - `mag_verify_field` (T113) — пишет FEM cross-check результаты.
  - `analyze_distortion_spectrum` (T131) — THD на saturable
    transformer.
  - `analyze_interleaved_leakage` (T132) — leakage L.
  - `sim_run` (T004, базовый ngspice pipeline) — если есть.
  - `kicad_sch_op_dc_pipeline` (T004 — facade для DC op) — если есть.
  Рекомендую **самый базовый** — простой `tran`/`op` ngspice pipeline,
  если он существует как отдельный use case. Если нет — берём
  `mag_verify_field` (свежий, активный, мы его помним).

- **Q6. Размер `additionalContext`: жёсткий cap?**
  Если в проекте 200 `.kicad_sch` файлов, hook сгенерирует длинный
  список. Делать ли cap (например, max 20 файлов на категорию + «and
  N more»)? Или полагаться на естественный размер демо-проектов?
  Рекомендую **soft cap = 20 файлов на категорию**, со суффиксом
  «(+N more)».

- **Q7. Hook script: bash или Python?**
  Проверил: `jq` в `efactory:linux` **нет** (`NO_JQ`). Без него bash
  для JSON output громоздок (escape кавычек, newlines, etc) и
  fragile. Python из stdlib (json, pathlib, datetime) — clean, без
  внешних зависимостей. Рекомендую **Python 3 stdlib-only** (без
  `import efactory.*` чтобы не тащить editable venv в hook cold-
  start). Запуск через `/usr/bin/python3` (system Python из Ubuntu
  base) — самый быстрый старт (~30 ms), не зависит от venv.

### Resolved (с ответами)

Vladimir 2026-05-25 — все 7 вопросов «по рекомендации»:

- **Q1 → (a):** `./efactory-up --agent NAME` (позиционный аргумент,
  контейнер стартует с `-w /workspace/NAME/`; если `NAME` не
  существует — `fail` на этапе pre-flight).
- **Q2 → (a):** bootstrap-step в `efactory-up --agent`: если host
  `$HOME/efactory-state/claude/settings.json` отсутствует —
  материализуется из embedded в репозиторий efactory template
  (`docker/runtime-agent-settings.json`). Файл становится user-
  editable (под persist mount).
- **Q3:** hook запускается на всех `source` (`startup` / `resume` /
  `clear` / `compact`) — после `/clear`/`/compact` контекст пропадает,
  его нужно вернуть.
- **Q4:** port + adapter — `SimResultsRepository` Protocol в
  `src/ports/outbound/` + `FileSystemSimResults` adapter в
  `src/adapters/outbound/sim_results_filesystem/` (по образцу
  T113 `GetDpFemSolver` / T132 `AnalyticalLeakage`).
- **Q5 → `sim_run`:** базовый use case
  (`src/application/sim_run.py`) получает optional параметр
  `sim_results_writer: SimResultsRepository | None = None` и
  `project_root: Path | None = None`; при обоих заданных — после
  `simulator.run` пишет `SimulationResult` через writer. Если
  writer не передан — use case ведёт себя как раньше (полная
  обратная совместимость).
- **Q6:** soft cap = 20 файлов на категорию + суффикс «(+N more)»
  если общее число больше.
- **Q7:** Python 3 stdlib only через `/usr/bin/python3` (3.12.3
  в образе подтверждён). Hook не зависит от editable venv,
  cold-start ~30-50 ms.

---

## Analyze (заполняется Claude)

### Issues

- 🟡 **A1 — Bootstrap settings.json не обновляется при upgrade образа.**
  Q2(a) решает «если файла нет — создать». Но если пользователь
  пользуется образом долго и в новой версии efactory меняется
  hook path (например, `/opt/efactory/scripts/` →
  `/opt/efactory/share/hooks/`), host-копия settings.json не
  обновится сама, hook перестанет работать.
  **Mitigation:** добавить флаг `efactory-up --agent --reset-claude-
  settings` (или подобный) — материализует embedded template,
  затирая host-копию (с осторожным backup `*.bak-YYYY-MM-DD`).
  Документировать в README + container-boundary.md как «escape
  hatch для апгрейда». В hook script — defensive: если hook ругается
  на non-existent path, переменная окружения `EFACTORY_DEBUG_HOOK=1`
  включает stderr-трассу, чтобы пользователь увидел, что
  settings.json устарел.

- 🟡 **A2 — Async vs sync writer.**
  `sim_run` — `async def`. Writer метод — sync (просто FS write).
  Решение: writer method `write` остаётся sync (нет I/O bound на
  POSIX FS write небольшого JSON), вызываем `await
  asyncio.to_thread(writer.write, result, project_root)` если
  paranoia на event loop blocking — но 1-2 KB JSON write < 1 ms,
  это премия. Делаем **sync вызов из async use case** без
  `to_thread` — простота важнее микро-perf.

- 🟢 **A3 — SimResult ≠ SimulationResult.**
  В спеке поминается `SimResult` (domain VO для записи), в
  существующем коде есть `SimulationResult` (`domain/simulation.py`,
  возвращаемый `Simulator.run`). Это **разные** объекты:
  `SimulationResult` — внутреннее представление (waveforms,
  measurements от ngspice), `SimResult` спеки — externalized JSON-
  снимок (timestamp, tool, summary). Конструируем
  externalized из internal через `SimResult.from_simulation_result(...)`
  factory или прямо в `FileSystemSimResults.write`. Clarify в коде
  тестами.

- 🟢 **A4 — Hook latency на больших проектах.**
  Target 200 ms может быть нарушен, если у проекта много
  `.kicad_sch` / large `.efactory/sim-results/`. Soft cap Q6 (20
  файлов / категория) частично снимает. Полностью — закроет лишь
  measurement. Acceptance — 200 ms на demo-проекте (se-amp-demo);
  на extreme проектах допустимо до 1 s (settings.json timeout 10 s
  оставляет запас). Зафиксируем как known fact в README.

- 🟢 **A5 — `additionalContext` size в JSON output.**
  Если sim-results много или metrics весомые, output может вырасти
  до десятков KB. Claude Code лимит на hook output не документирован.
  Hook будет **не** включать `metrics` в контекст (только summary +
  timestamp + analysis_type + source_file), чтобы держать output в
  пределах 2-4 KB. metrics остаются в JSON-файле, агент может
  прочитать их при необходимости через `Read`.

- 🟢 **A6 — `pwd` vs `${CLAUDE_PROJECT_DIR}` placeholder в hook.**
  claude-code-guide агент рекомендовал `${CLAUDE_PROJECT_DIR}` как
  надёжный. Используем оба: 1) пробуем env `CLAUDE_PROJECT_DIR`,
  2) fallback на `os.getcwd()`, 3) если оба ведут не в
  `/workspace/<NAME>/`, выводим «No active project».

- 🟢 **A7 — Test scope.**
  Unit-тесты для hook-генератора (stdlib parsing) — Python module
  отдельно от runtime-script wrapper, чтобы тестировать парсинг
  через pytest без subprocess. Integration test внутри
  `efactory:linux` — отдельный `tests/integration/test_session_
  start_hook.py`, skipif outside container.

Все issues — Warning / Note, **нет Critical**. Приступаем к
implementation.

---

## Phases

- **Phase A — Hook script + settings.json bootstrap.**
  - `docker/runtime-agent-settings.json` — embedded template для
    Claude Code settings.json.
  - `scripts/session_start_hook.py` — Python 3 stdlib генератор
    дин-контекста (parsing-функции импортируемы для unit-тестов;
    `if __name__ == '__main__':` обёртка делает stdout-emit).
  - `Dockerfile` — `COPY` обоих + `chmod +x` для hook.
  - `efactory-up --agent NAME` — позиционный аргумент, валидация
    каталога, изменение `-w /workspace/$NAME`, bootstrap settings.json
    в `$STATE_DIR/claude/settings.json`.
  - Unit-тесты для hook-парсера (TDD).
  - Integration test через `docker run` (skipif без docker).
  - Acceptance: на `se-amp-demo` агент сразу видит project name,
    файлы.

- **Phase B — Sim-results schema + writer.**
  - `src/domain/sim_results.py` — `SimResult` dataclass + JSON
    schema (constants for `analysis_type`, etc).
  - `src/ports/outbound/sim_results.py` — `SimResultsRepository`
    Protocol.
  - `src/adapters/outbound/sim_results_filesystem/` — `FileSystemSimResults`
    adapter с атомарной записью.
  - Unit-тесты для adapter (TDD на tempdir).
  - Acceptance: написали SimResult → файл валидируется через json
    schema, имя в правильном формате.

- **Phase C — Integration в `sim_run`.**
  - `sim_run` принимает optional `sim_results_writer` + `project_root`.
  - Unit-тест: writer вызывается с правильным `SimResult` после
    `simulator.run`.
  - Integration test (полный pipeline) — опционально, если
    существующий `Simulator` fake/integration test покрывает.
  - Acceptance: end-to-end — запустить `sim_run` с tempdir, проверить
    файл в `.efactory/sim-results/`.

- **Phase D — Documentation + closing.**
  - `docs/container-boundary.md` — добавить `.efactory/sim-results/`
    в раздел «что persist'им».
  - `README.md` — короткое описание T016 (project switching,
    sim-results layout).
  - `BACKLOG.md` follow-up'ы:
    - sim-results rotation/cleanup (если набирается много);
    - `PostToolUse` hook для real-time sim-results update в active
      сессии.
  - `BOARD.md` Doing → Done.
  - `CHANGELOG.md [Unreleased]` запись.

**Sequencing:** Phase A independent (можно ship отдельно если
runtime), но B-C короче связаны и докажут end-to-end на одном PR.
Объединяем A+B+C+D в один PR (укрупняем PR per методике).
