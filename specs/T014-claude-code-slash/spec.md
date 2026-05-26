# Spec: T014 — efactory custom slash-команды для Claude Code

**Статус:** Analyzed
**Дата создания:** 2026-05-26
**Связанные документы:**
- `BACKLOG.md → T014` (формулировка задачи).
- `BOARD.md → T013` (Claude Code runtime — npm install + entrypoint).
- `BOARD.md → T016` (Dynamic project context — SessionStart hook + sim-results).
- `DECISIONS.md` 2026-05-24 («Tool surface = Bash + efactory CLI + filesystem, не MCP»).
- `docker/runtime-agent-settings.json` (паттерн bootstrap host state из container template).
- `scripts/session_start_hook.py` (динамический context, переиспользуем для `/project use`).
- `scripts/gen-se-amp-demo.py` (генератор SE-amp demo — основа `se-amp` шаблона).

---

## 1. Overview

Phase 1b: Claude Code запускается в контейнере (T013) и при старте сессии
получает project context (T016). T014 закрывает Phase 1b — добавляет
**custom slash-команды** для типовых efactory-рабочих сценариев:
создать новый проект из шаблона, переключиться на другой проект внутри
работающей сессии, запустить SPICE-симуляцию текущей схемы. Команды —
тонкие markdown-обёртки в `.claude/commands/` поверх существующего
`efactory` CLI. Параллельно CLI расширяется механизмом шаблонизации
проектов (`efactory project create --template se-amp NAME`), который
материализует pre-built SE-amp 6П14П в `/workspace/<NAME>/`.

## 2. Сценарии использования

Канонический синтаксис slash-команд (см. Analyze A1) —
**hyphenated flat**: `/project-create`, `/project-use`, `/sim-run`.

- **Создание проекта из шаблона.** Vladimir в TUI Claude Code:
  `/project-create my-amp-v2`. Slash-команда вызывает
  `efactory project create --template se-amp --name my-amp-v2`,
  материализуется `/workspace/my-amp-v2/` с
  `my-amp-v2.kicad_sch`/`my-amp-v2.kicad_pro` (filename =
  sanitized project name), каталогом `models/` и `manifest.yaml`.
  Агент видит вывод CLI и путь к новому проекту; следующим шагом —
  `/project-use my-amp-v2`.

- **Просмотр контекста другого проекта (display-only).** Vladimir в
  сессии `se-amp-demo`, хочет понять, что в `my-amp-v2`:
  `/project-use my-amp-v2`. Slash-команда проверяет, что
  `/workspace/my-amp-v2/` существует, и запускает
  `CLAUDE_PROJECT_DIR=/workspace/my-amp-v2 python3 /scripts/session_start_hook.py`
  с пустым stdin — печатает свежий project context block (имя,
  файлы, последние sim-результаты). В выводе явное note: «контекст
  показан, но cwd сессии не изменён; для последующих shell-команд
  используй абсолютные пути под `/workspace/my-amp-v2/`. Для полного
  refresh системного prompt — выйди и `./efactory-up --agent
  my-amp-v2`, или `/clear` если ты уже работал из этого cwd
  изначально».

- **Запуск SPICE-симуляции.** Vladimir в проекте `se-amp-demo`:
  `/sim-run se_amp.kicad_sch`. Slash вызывает
  `efactory bridge sim-run --schematic se_amp.kicad_sch`, рендерит
  output (op-point/измерения/duration). При вызове без аргумента —
  auto-detect единственного `.kicad_sch` в cwd (top-level + 1 subdir,
  skip dot-directories). Результат пишется в
  `.efactory/sim-results/` (через T016 infrastructure) — в следующей
  сессии будет в context-блоке hook'а.

- **Discoverability.** Vladimir набирает `/` в Claude Code TUI —
  три новые команды (`/project-create`, `/project-use`, `/sim-run`)
  видны в menu с описаниями и `argument-hint`. Команда без
  обязательных аргументов печатает usage.

## 3. Functional Requirements

**Slash-команды (markdown в `.claude/commands/`):**

- ДОЛЖНЫ: лежать в `docker/runtime-agent-commands/` в репозитории,
  bootstrap'иться в host state `$HOME/efactory-state/claude/commands/`
  при старте `efactory-up --agent`, mount'иться в контейнер на
  `/efactory/.claude/commands/` (тот же механизм, что
  `runtime-agent-settings.json` в T016).
- ДОЛЖНЫ: три файла (filename = command name) —
  - `project-create.md` (`/project-create NAME`),
  - `project-use.md` (`/project-use NAME`),
  - `sim-run.md` (`/sim-run [SCHEMATIC] [--analysis TYPE]`).
- ДОЛЖНЫ: каждая команда содержит frontmatter:
  - `description` (видим в `/`-menu),
  - `argument-hint` (показывается в autocomplete),
  - `allowed-tools: Bash` (+ `Read` где нужно — снижает permission
    prompts, см. Analyze A9).
- ДОЛЖНЫ: при отсутствии обязательного аргумента или передаче `--help`
  выводить usage без побочных эффектов.
- `/project-use NAME` — **display-only** (см. Analyze A2). Не делает
  `cd`, не модифицирует state сессии. Запускает hook через
  `CLAUDE_PROJECT_DIR=/workspace/<NAME> python3
  /scripts/session_start_hook.py < /dev/null` в одном Bash call,
  печатает context block + явное note про абсолютные пути и
  `/clear`. Pre-flight: `/workspace/<NAME>/` существует и не
  hidden (не начинается с `.`).
- `/sim-run` — auto-detect единственного `.kicad_sch` в cwd при
  отсутствии аргумента (top-level + 1 subdir, skip dot-directories,
  см. Analyze A5). При нуле или >1 match — fail с usage и списком
  кандидатов.
- НЕ ДОЛЖНЫ: дублировать functionality встроенных команд Claude Code
  (`/model`, `/tools`, `/save`, `/load`, `/compact`, `/clear`).

**CLI расширение (`efactory project create --template`):**

- ДОЛЖЕН: появиться флаг `--template <NAME>` у `efactory project create`
  (optional; без него поведение прежнее — пустой проект через
  `create_project` use case).
- ДОЛЖЕН: при передаче `--template se-amp` — материализовать дерево из
  `data/templates/se-amp/` в `/workspace/<project-name>/` (или в
  configurable `--target-dir`, см. §Q3): копия файлов, substitution
  placeholder'ов (минимум `{{PROJECT_NAME}}`) в текстовых файлах
  (`.kicad_pro`, `manifest.yaml`), регистрация проекта через тот же
  `create_project` use case.
- ДОЛЖЕН: при неизвестном template name — печатать список доступных и
  fail с non-zero exit.
- ДОЛЖЕН: при существующем target dir — fail с понятным сообщением
  («target already exists: …, use --force to overwrite»). `--force`
  flag — out of scope T014, см. §Q5.
- НЕ ДОЛЖЕН: вводить `efactory project use` CLI subcommand —
  «активный проект» в Claude Code сессии = cwd, нет смысла дублировать
  это в SQL state.

**Template infrastructure:**

- ДОЛЖЕН: каталог `data/templates/<name>/` — шаблоны хранятся как
  static assets (включаются в wheel через существующую `data/`
  packaging-конфигурацию).
- ДОЛЖЕН: единственный shipping шаблон — `se-amp`, содержит:
  - `{{PROJECT_NAME}}.kicad_sch` — запечённый artefact от
    текущего `gen-se-amp-demo.py` builder'а (генерация **build-
    time**); filename substituted при материализации (sanitizer:
    spaces → `_`, `/` → `_`, см. Analyze A4).
  - `{{PROJECT_NAME}}.kicad_pro` (минимальный, для KiCad Simulator).
  - `models/6P14P.lib`, `models/OPT_SE_5K_8.lib` (копии из
    `data/models/`, относительные пути в `Sim.Library`).
  - `manifest.yaml.tmpl` с placeholder `{{PROJECT_NAME}}` (расширение
    `.tmpl` помечает файл как требующий substitution; renames в
    `manifest.yaml` после).
  - `template.yaml` (метаданные шаблона: `description`, `summary` —
    видны в `--template list` выводе CLI).
  - `README.md` (короткий — что в шаблоне, как использовать).
- ДОЛЖЕН: появиться `scripts/regenerate-templates.py` (или сравнимая
  команда), который вызывает builder и **переписывает** запечённые
  файлы в `data/templates/<name>/`. Не часть автоматического pipeline —
  ручной запуск при изменении builder'а.
- ДОЛЖЕН: shipping шаблон проходит тесты —
  `tests/integration/test_template_se_amp.py` материализует во временный
  каталог, проверяет что `kicad-cli sch erc` проходит (или хотя бы
  возвращает rc 0), и `ngspice -b` отрабатывает базовый `.op` анализ.
- ДОЛЖЕН: `data/templates/` упакован в wheel через
  `[tool.hatch.build.targets.wheel.force-include]` (см. Analyze A3 —
  pre-existing pyproject gap; T014 закрывает только templates,
  общий fix для `data/models/` — follow-up T-id).
- ДОЛЖЕН: snapshot test для запечённого шаблона
  (`tests/integration/test_template_se_amp_snapshot.py`):
  регенерирует через `scripts/regenerate-templates.py` во временный
  каталог, нормализует non-deterministic content (timestamps в
  `.kicad_pro`, UUID'ы в schematic — см. Analyze A8), сравнивает
  с запечённым. Fail message: «run `uv run python
  scripts/regenerate-templates.py` to refresh».

**Discoverability:**

- ДОЛЖНЫ: команды появляться в выводе `/help` runtime-агента Claude Code
  внутри `efactory:linux` сразу после bootstrap (без manual rescan).
- ДОЛЖЕН: `docker/runtime-agent-CLAUDE.md` (system prompt) обновиться
  упоминанием доступных efactory-команд («Custom slash-команды: …»).

**Документация:**

- ДОЛЖНЫ: `README.md` (раздел «Запуск runtime-агента») получить блок
  про slash-команды.
- ДОЛЖЕН: `docs/container-boundary.md` отразить новый mount/COPY путь
  для commands.
- ДОЛЖНЫ: `CHANGELOG.md [Unreleased]` + перенос T014 в `BOARD.md →
  Done` в задачном PR по правилу из проектного CLAUDE.md.

## 4. Success Criteria

- В TUI `claude` внутри `efactory:linux` `/`-menu показывает три
  efactory-команды (`/project-create`, `/project-use`, `/sim-run`)
  с описаниями и argument-hint.
- `/project-create my-amp-v2` создаёт `/workspace/my-amp-v2/` с
  работающей SE-amp схемой `my-amp-v2.kicad_sch`; в `manifest.yaml`
  записано `name: my-amp-v2`.
- В новом проекте `kicad-cli sch erc my-amp-v2.kicad_sch` возвращает
  rc 0 (нет critical ERC violations).
- `/sim-run my-amp-v2.kicad_sch` запускает `efactory bridge sim-run`
  и возвращает текстовый summary + создаёт запись в
  `.efactory/sim-results/<TS>-<analysis>.json`. Вызов `/sim-run` без
  аргумента в каталоге с одним `.kicad_sch` находит его автоматически.
- `/project-use my-amp-v2` (display-only) печатает свежий project
  context block для `/workspace/my-amp-v2/` (имя, файлы, последние
  sim-результаты) и явное note: «cwd сессии не изменён, используй
  абсолютные пути или `/clear` + перезапуск».
- Все шаги воспроизводимы внутри `efactory:linux` без MCP-серверов
  и без host-side toolchain'ов.
- Pre-push gates зелёные (`ruff check`, `ruff format --check`,
  `mypy src`, `pytest` ≥ 80% coverage, `lint-imports` 3/3 contracts
  kept).

## 5. Key Entities

- **`SlashCommand`** — markdown-файл в `docker/runtime-agent-commands/`
  с frontmatter (`description`, `argument-hint`) и телом (instructions
  для агента: какой `efactory ...` запустить, как обработать output).
  Concept-уровень — не отдельный domain VO, просто файлы в репо.

- **`ProjectTemplate`** — каталог `data/templates/<name>/` с
  фиксированной структурой (см. §3). Метаданные шаблона (`description`,
  `summary`) — в `data/templates/<name>/template.yaml` (rendered в
  `--template-list` output CLI). См. §Q1 — формат может уточниться.

- **`TemplateMaterializer`** — внутренний adapter
  (`adapters/outbound/template_filesystem/` или сравнимый путь —
  clarify §Q4): метод
  `materialize(template_name: str, target_dir: Path, context:
  dict[str, str]) -> Path`. Атомарность — write into
  `<target>.tmp/` → `Path.replace`. DI инжектится в `create_project`
  use case через новый optional port.

- **`SimRunResult`** (уже существует как T016 `SimResult`) —
  переиспользуем без изменений; `/sim run` через `efactory bridge
  sim-run` пишет туда же.

## 6. Assumptions & Constraints

- **Claude Code 2.1.150** уже стоит в образе (T013); custom slash-
  команды поддерживаются через `<dir>/commands/<name>.md` с
  frontmatter — это документированный API CLI.
- Slash-команды живут на host'е (`$HOME/efactory-state/claude/
  commands/`), mount'ятся в контейнер ro. Host state persistent
  (T140 boundary), значит после первого bootstrap команды переживают
  `docker rm`.
- Single-user: конкурентного доступа нет, race conditions на
  `--reset-claude-settings` не рассматриваем.
- `data/templates/se-amp/` запекается **один раз** перед merge T014
  через `regenerate-templates.py`; обновляется ручным запуском при
  изменении builder'а в `gen-se-amp-demo.py` / `_build_se_amp`.
- Установка `efactory` CLI внутри `efactory:linux` уже работает
  (T013-prep, editable install в `/opt/efactory/.venv`).
- `/project-use NAME` НЕ перезапускает Claude Code session и НЕ меняет
  cwd Bash-инструмента (Bash cwd persistence нестабильна, см. Analyze
  A2). Команда — display-only: запускает hook через `CLAUDE_PROJECT_
  DIR` env-override, печатает свежий context для указанного проекта,
  выводит note про абсолютные пути. Полный refresh system prompt —
  через пользовательский `/clear` или exit + `efactory-up --agent
  NAME`.
- `data/` (включая `data/templates/`) сейчас не упакован в wheel
  (pyproject `[tool.hatch.build.targets.wheel] packages` содержит
  только `src/*`). T014 добавляет `force-include` для
  `data/templates`; общий gap для `data/models/` остаётся pre-
  existing, follow-up T-id в BACKLOG.

## 7. Out of Scope

- **`/export-production`** — вынесено в новую задачу **T150**
  (production-package: BOM + PDF schematic + sim-results + optional
  Gerber).
- **Дополнительные шаблоны** (`pp-amp`, `preamp`, `filter`) — отдельные
  T-задачи в BACKLOG follow-ups; T014 acceptance явно требует только
  `se-amp`.
- **`--force` overwrite** для `efactory project create --template` —
  отдельная задача (нужен ли — TBD на основе UX в работе).
- **Watch-mode** для `/sim run` (auto-rerun на изменение `.kicad_sch`) —
  Phase 2 territory.
- **`efactory export production` CLI subcommand** — часть T150.
- **Любые улучшения lifecycle Claude Code TUI** (programmatic `/clear`,
  session restart APIs) — не наша задача, depend on upstream.
- **MCP-серверы** — отвергнуты ADR 2026-05-24.
- **`efactory project use` CLI subcommand** — slash-команда работает
  через `cd` напрямую, дублирование в SQL state не нужно.

---

## Clarify (заполняется Claude)

### Open questions

<!-- Все 10 вопросов закрыты «по рекомендации» 2026-05-26. -->

### Resolved (с ответами)

- **Q1 — template metadata: `data/templates/<name>/template.yaml`**
  (по рекомендации). Отдельный файл, не путается с материализуемым
  `manifest.yaml`; содержит `description`, `summary`.

- **Q2 — `/project use NAME` оставляем** (по рекомендации). Cd в shell-
  сессии Bash + manual hook re-run + note про `/clear` для полного
  refresh системного prompt.

- **Q3 — `EFACTORY_WORKSPACE_DIR` env + `--target-dir` flag** (по
  рекомендации). Env-default для контейнера и тестов; flag перекрывает
  для разовых случаев.

- **Q4 — TemplateMaterializer как helper-функция в CLI-adapter** (по
  рекомендации). Без отдельного port'а; refactor в hex когда появится
  второй inbound consumer.

- **Q5 — ручной `regenerate-templates.py` + pytest-snapshot test** (по
  рекомендации). В T014 — snapshot test, fail с сообщением «run
  `uv run python scripts/regenerate-templates.py`». CI-enforcement —
  follow-up T-задача (T151+, см. §`Out of Scope` дополнение).

- **Q6 — default `--template se-amp`** (по рекомендации). Когда
  шаблонов станет 3+, переоценим (interactive wizard / positional).

- **Q7 — держим existing `--name`** (по рекомендации). Slash-команда
  транслирует `/project create my-amp-v2` в
  `efactory project create --name my-amp-v2 --template se-amp`.

- **Q8 — auto-detect single `.kicad_sch`** (по рекомендации). Один
  match — берём его; ноль или больше одного — fail с usage и списком
  кандидатов.

- **Q9 — переименовать в `--reset-claude-state`** (по рекомендации).
  Bootstrap'ит settings + commands; `--reset-claude-settings` остаётся
  deprecated-alias (warning в stderr); backup в один `*.bak-YYYY-MM-DD/`.

- **Q10 — Phase A (CLI + template + materializer) + Phase B (slash +
  bootstrap + docs)** (по рекомендации). Два commit'а на ветке, один
  squash при merge.

---

## Analyze (заполняется Claude)

Проведено 2026-05-26 на статусе Clarified. Источники: верификация
syntax slash-команд через claude-code-guide subagent (docs URL
`https://code.claude.com/docs/en/slash-commands.md`), чтение
`scripts/session_start_hook.py` + `docker/runtime-agent-settings.json`,
аудит `pyproject.toml` (wheel packaging) и существующего CLI
(`efactory project create`).

### 🔴 Critical

- **A1. Невалидный синтаксис `/project create NAME`.** Claude Code 2.1.x
  парсит инвокацию как одну slash-команду без пробелов: `/project
  create NAME` будет распознан как команда `/project` с аргументами
  `create NAME`. Реально доступные опции:
  - **(a) Hyphenated flat-naming**: `commands/project-create.md` →
    `/project-create NAME`; `commands/project-use.md` → `/project-use
    NAME`; `commands/sim-run.md` → `/sim-run [SCHEMATIC]`.
  - **(b) Dispatcher command**: `commands/project.md` (body парсит
    `$1` как subcommand: `create`/`use`/...). Универсальнее, но
    `argument-hint` теряет конкретику и `/help` показывает одну
    запись вместо трёх.
  - **(c) Plugin namespace**: `commands/efactory/project-create.md` →
    `/efactory:project-create`. Идиоматично, но требует упаковки
    как plugin — heavier чем нужно.

  **Recommendation: (a) hyphenated flat**. Spec § Functional
  Requirements + § Success Criteria + § Сценарии использования
  переписать с `/project-create`, `/project-use`, `/sim-run`.
  BACKLOG-формулировка с пробелами была концептуальной, не литералом —
  это надо явно зафиксировать.

- **A2. Bash cwd persistence нестабильна между tool calls в runtime-
  агенте.** Документация Claude Code прямо рекомендует *«always use
  absolute file paths»* — cwd может reset'нуться между Bash-
  инвокациями (особенно в Agent-threads; поведение в main thread
  runtime-агента не гарантировано стабильным API). Текущий дизайн
  `/project-use NAME` (cd в одном Bash call, ручной hook re-run в
  следующем) **может молча не работать** — второй call стартует из
  исходного cwd, hook напечатает context старого проекта.

  Опции рефакторинга:
  - **(а) Chain в одном Bash call**: `cd /workspace/NAME && CLAUDE_PROJECT_DIR=/workspace/NAME python3 /scripts/session_start_hook.py`.
    Гарантированно работает (один shell), но эффект «cd» исчезает
    после возврата из Bash call.
  - **(б) Display-only**: `/project-use NAME` **не делает cd**,
    только запускает hook с `CLAUDE_PROJECT_DIR=/workspace/NAME` для
    печати свежего context-блока + явное note агенту: «для
    последующих shell-команд используй абсолютные пути под
    `/workspace/NAME/`». Честнее относительно ограничений среды.
  - **(в) File-маркер `active-project`** — два источника правды
    (cwd vs маркер), отвергаю.
  - **(г) Убрать `/project-use` вообще** — рекомендовать exit +
    `./efactory-up --agent NAME`. Самый честный путь, но проигрывает
    UX.

  **Recommendation: (б) display-only** (chained cd + hook в одном
  Bash call — bonus, не контракт). В § Functional Requirements
  переформулировать: «`/project-use NAME` печатает context-block
  для `/workspace/<NAME>/` и note: для последующих shell-команд
  используй абсолютные пути; для полного refresh системного
  prompt — пользовательский `/clear`».

### 🟡 Warning

- **A3. Wheel packaging для `data/templates/`.** В `pyproject.toml`
  УЖЕ есть `[tool.hatch.build.targets.wheel.force-include]
  "data/models" = "data/models"` — на момент implementation
  обнаружил, что общий gap для `data/` не существует (я ошибся при
  первоначальном аудите). T014 просто добавит рядом
  `"data/templates" = "data/templates"`; никакого follow-up T-id
  не нужно.

- **A4. Snake_case filename vs human project name.** В шаблоне
  baked filename `se_amp.kicad_sch`; project name может быть
  `my-amp-v2`. Опции:
  - (а) переименовать в `{{PROJECT_NAME}}.kicad_sch` с substitution
    + sanitizer (`name.replace(" ", "_").replace("/", "_")`).
  - (б) оставить `se_amp.kicad_sch` (filename ≠ project name —
    KiCad не возражает).
  - (в) `main.kicad_sch` (generic).

  **Recommendation: (а)** — substitution filename. Делает output
  опрятным; sanitizer тривиален.

- **A5. `/sim-run` auto-detect — фильтрация `.efactory/` и
  dot-префиксов.** Scan cwd на `.kicad_sch` должен исключить
  dot-prefixed directories (`.efactory/`, `.git/`). Простой фильтр:
  scan top-level + 1 subdir (как hook), skip names с `.`. Прописать
  в § Functional Requirements.

- **A6. `template.yaml` YAML-парсинг.** Адаптер `manifest_yaml/`
  использует PyYAML (зависимость есть). Template loader использует
  тот же loader, не вводим toml/json параллельно.

- **A7. `--reset-claude-state` rename consistency.** Сейчас
  `--reset-claude-settings` упоминается в README + CHANGELOG +
  T016 spec implementation note. Action в Phase B: rename во всех
  местах; keep alias `--reset-claude-settings` ⇒ stderr warning,
  удаление alias — следующий minor release.

- **A8. Determinism snapshot-теста для regenerate-templates.**
  `_build_se_amp` может emit'ить non-deterministic content
  (timestamps в `.kicad_pro`, UUID'ы в схеме). Action в Phase A:
  - проверить determinism (diff двух последовательных runs);
  - если non-deterministic — нормализовать (regex substitute
    timestamp полей на placeholder перед сравнением; sorted JSON
    output для `.kicad_pro`).
  Pytest snapshot test делает ту же нормализацию перед diff.

### 🟢 Note

- **A9. `allowed-tools` frontmatter.** Можно явно указать
  `allowed-tools: Bash` (+ `Read` где нужно) — снижает permission-
  prompts. Внутри `efactory:linux` `--dangerously-skip-permissions`
  уже выставлен (T013), поэтому effect минимальный, но для
  будущих host-deployments полезно. Добавить в три файла.

- **A10. Smoke testing внутри образа.** Pre-push gates на хосте не
  поймают TUI-issues (frontmatter, `/help` display, реальное
  поведение). В Phase B — TUI smoke `./efactory-up --agent
  se-amp-demo` после rebuild: три команды видны в `/`-menu,
  каждая отрабатывает на demo-проекте.

- **A11. Phase A → B зависимость от bootstrap.** Phase B вводит
  bootstrap commands в host state. Без rebuild + `--reset-claude-
  state` агент не увидит новые команды. README — инструкция «после
  T014: `docker build` + однократный `--reset-claude-state`»
  (зеркало T016 уведомления).

- **A12. Backward-compat existing `efactory project create`.**
  Существующая инвокация `efactory project create --name foo` без
  `--template` остаётся валидной (пустой проект). Acceptance — unit-
  test «без --template создаёт проект как раньше, без изменений».
  Защита от регрессии.

### Сводка действий перед Implementation

1. **A1**: переименовать команды на hyphenated в § Functional
   Requirements + § Success Criteria + § Сценарии использования.
2. **A2**: переформулировать `/project-use` как display-only.
3. **A3**: добавить `data/templates` в `force-include` wheel
   packaging; завести follow-up T-id для общего `data/` gap.
4. **A4**: `{{PROJECT_NAME}}.kicad_sch/pro` с sanitizer.
5. **A5**: фильтр dot-префиксов + top-level+1 для auto-detect.
6. **A8**: determinism check + нормализация snapshot test.
7. **A9/A10/A11**: применяются при реализации.

После применения 1-7 + согласование с Vladimir → переход в
In Progress.
