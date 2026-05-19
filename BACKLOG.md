# Backlog

Парковка идей, побочных находок и «надо бы потом починить».

**Правило:** если в процессе работы над текущей задачей Claude или
Разработчик замечают что-то постороннее — оно идёт сюда, а не в текущий
коммит. Это защищает от расползания scope.

Это **не формальный таск-трекер** со сроками и метриками — это парковка
идей. Но **порядок имеет значение**: сверху — то, что планируется
ближайшим, ниже — менее срочное (FIFO по умолчанию, можно поднимать
приоритетное наверх). Когда из бэклога что-то берётся в работу — оно
вырастает в задачу или спеку (`specs/T<NNN>-…`) и удаляется отсюда.

## Формат

`- **T<NNN>** — [<дата находки>] <короткое описание> — <опционально: контекст / откуда всплыло>`

ID присваивается при создании; новый = `max(существующих T-ID в
BACKLOG.md, BOARD.md и CHANGELOG.md) + 1`. ID не переиспользуется
и сохраняется при перетекании задачи между BACKLOG и BOARD; после
релиза задача переходит в `CHANGELOG.md` (с тем же T-ID), что
гарантирует уникальность между релизами.

## Items

Задачи дорожной карты концепта (CONCEPT.md §13), фазы 1a/1b/2/3/4/5/6/7/8.
Плюс отдельный раздел архитектурных follow-up'ов сверху — то, что
выявилось при работе над фундаментом T085 / Walking Skeleton и не
вписывается напрямую в фазы дорожной карты.

### Архитектурные follow-up'ы Walking Skeleton

<!-- Задачи, выявленные при работе над hexagonal-фундаментом (T085)
     и его обкаткой полным CRUD-набором (T086–T092). Источник —
     ретроспективы milestone'ов в `CHANGELOG.md`. -->

<!-- T094 закрыт ADR от 2026-05-19 в DECISIONS.md (вариант "в":
     /ultrareview как primary external review, CodeRabbit best-effort). -->


### Tech Debt (отложено)

<!-- Задачи признанные нужными, но без активного владельца / времени.
     Не идут в Doing до явного решения Разработчика «берём». -->

- **T002** — [2026-05-15, replaced 2026-05-19 by T110] ~~bootstrap.sh
  для Linux: установка KiCad, ngspice, FreeCAD, FEMM, Python,
  MCP-серверов по `compatibility.toml`.~~ **Replaced by T110
  (Dockerfile с полным стеком).** ADR — `DECISIONS.md` 2026-05-19,
  «Distribution: Linux Docker image».
- **T003** — [2026-05-15, parked 2026-05-19 до Phase Cross-platform]
  bootstrap.ps1 для Windows: то же самое через winget/chocolatey +
  pip. **Parked:** efactory переходит на Docker-distribution (Linux
  only в текущей фазе). Windows-поддержка — через Docker Desktop /
  WSLg в отдельной Phase Cross-platform (см. ниже).
- **T011** — [2026-05-15, parked 2026-05-19] `kicad-sim-chat`:
  терминальный UI на Rich (история, ввод, рендер ответов).
  Acceptance: интерактивный чат работает в любом современном
  терминале, поддерживает прокрутку и подсветку. **Parked:**
  решено использовать Claude Code как frontend (см. T108 OpenCode
  pilot и будущий ADR «Frontend = готовый AI-терминал, а не свой
  клиент»). Возвращать к T011 — только если оба готовых решения
  не подойдут после пилота.
- **T108** — [2026-05-19] **Spike: пилотное знакомство с OpenCode**
  как альтернативным frontend'ом efactory (MIT, Go-based TUI,
  multi-provider через Models.dev, MCP local+remote, mid-session
  model switch). Цель — оценить, закрывает ли OpenCode дух
  T012-T019 «бесплатно» и стоит ли менять Claude Code → OpenCode
  как основной фронтенд.
  Acceptance: за одну вечернюю сессию проверены и зафиксированы
  выводы в `specs/T108-opencode-pilot/notes.md`:
  (a) установка и запуск на dev-машине Владимира (Linux);
  (b) подключение хотя бы одного efactory MCP-сервера через
  `opencode.json`, вызов тула из чата;
  (c) переключение моделей mid-session (Anthropic ↔ OpenAI-compat
  ↔ локальный Ollama, что доступно);
  (d) есть ли аналог `CLAUDE.md` (project-level system prompt) и
  слэш-команд;
  (e) рендер markdown / code / таблиц в TUI на качественном
  уровне;
  (f) поддержка side-by-side `/compare`-сценария (T020) — есть /
  нет / можно ли добавить плагином.
  По итогам — ADR «Frontend для efactory: Claude Code vs OpenCode»
  в `DECISIONS.md` и решение по судьбе T011-T019.

### Фаза 1a — MVP-ядро (3–4 недели)

<!-- T004b + T005 перенесены в BOARD.md → Done (2026-05-19, common PR). -->

<!-- T004b/T005 Phase 1 перенесены в BOARD.md → Done (2026-05-19). -->
<!-- T101 перенесена в BOARD.md → Done (2026-05-19). -->
<!-- T102 перенесена в BOARD.md → Doing (2026-05-18). -->

<!-- T103 перенесена в BOARD.md → Done (2026-05-19). -->

<!-- T105 Phase 0 перенесена в BOARD.md → Done (2026-05-19). -->

<!-- T105 Phase 1 (a)+(c) перенесены в BOARD.md → Done (2026-05-19):
     ECC83 self-contained (без extends), multi-unit dual-triode
     instancing (Valve:ECC81B / ECC83B / ECC88B registry entries). -->

<!-- T107 Phase 0 закрыт 2026-05-19 (BOARD.md → Done), Phase 1
     deferred перенесён в Фазу 3 перед T106 (Vladimir 2026-05-19) —
     связан с T032 SVG-render + T106 LLM-vision beautifier. -->

<!-- T106 (scheme layout beautifier) перенесён в Фазу 3 после T032
     (Vladimir 2026-05-19) — связан с SVG render + LLM-vision. -->


### Phase 0.9 — Containerization (новая фаза, 2026-05-19)

<!-- Введена решением 2026-05-19 (DECISIONS.md «Distribution:
     Linux Docker image с полным стеком»). Ставится между Phase
     1a и Phase 1b: до того, как развивать chat-client / runtime-
     агента, упаковать весь инструментарий в один воспроизводимый
     образ. После завершения Phase 0.9 все дальнейшие фазы
     исполняются внутри контейнера. Linux-only; Mac/Windows —
     Phase Cross-platform (см. конец файла). -->

<!-- T110 (Phase 0 базовый Dockerfile) перенесён в BOARD.md → Doing
     2026-05-19. Spec — `specs/T110-containerization/spec.md`
     (Analyzed, Phase 0). -->
- **T111** — [2026-05-19] **KiCad GUI passthrough.** X11/Wayland
  socket mount, Xauthority, `/dev/dri` для Intel/AMD GPU
  acceleration (или nvidia-runtime для NVIDIA). KiCad eeschema /
  pcbnew / 3D viewer запускается из контейнера, открывается на
  хосте. Acceptance: открыть SE-amp фикстуру, сохранить,
  переоткрыть — стабильно на >50 cycles.
<!-- T112 перенесена в BOARD.md → Doing (2026-05-20). Acceptance
     уточнено: FreeCAD 1.0+ через AppImage (variant C), Sheet Metal
     через git clone в Mod/, freecad-mcp вынесен в T124. См. ADR
     2026-05-20 в DECISIONS.md и Phase 2 implementation note. -->
<!-- T066 absorbed by T112: bootstrap FreeCAD больше не нужен —
     поставка через AppImage внутри efactory:linux. -->
- **T113** — [2026-05-19] **FEM-solver: пилот и интеграция.**
  Заменяет FEMM (см. ADR от 2026-05-19 «Magnetic field
  verification: Linux-native FEM-solver»). Пилот сравнивает
  **Elmer FEM (primary)** vs **GetDP + Gmsh (fallback)** на
  фикстурах: OPT 6П14П single-ended, силовой трансформатор
  50 Гц, flyback SMPS дроссель. Критерии выбора: качество
  результатов vs аналитики (PyOpenMagnetics), API-удобство
  для LLM-orchestration, время счёта, размер в образе.
  Absorbs T058 (FEMM bootstrap). После выбора — интеграция
  через `adapters/outbound/fem_solver/` (solver-agnostic
  port `MagneticFieldSolver`), MAS JSON → solver input
  (~50–100 строк). Acceptance: для тестового OPT 6П14П
  расчётная индуктивность через solver совпадает с
  аналитической в пределах ±10%; решение зафиксировано в
  ADR.
<!-- T114 перенесена в BOARD.md → Doing (2026-05-20) — объединена
     с T121 в один PR (variant C). См. BOARD.md → T114 + T121. -->
- **T115** — [2026-05-19] **CI: сборка и публикация образа.**
  GitHub Actions / GHCR workflow: на каждый merge в `main`
  пересобираем образ, прогоняем smoke-test внутри (kicad-cli
  ERC + ngspice OP + FreeCAD headless rendering + solver
  unit-test), публикуем в GHCR с tag = git SHA + `linux-latest`.
  Релизы (0.X.0) дополнительно теггируются `linux-0.X.0`.
  Acceptance: первый merge после T110-T114 → GHCR содержит
  pull-able образ, `docker pull ghcr.io/vlakir/efactory:linux-
  latest` работает на чистой машине.
- **T120** — [2026-05-19] **Cleanup: удалить AppImage-detection
  из `platform_layer`.** После Phase 0.9 KiCad/FreeCAD внутри
  контейнера всегда через apt (в PATH); AppImage-fallback в
  `src/adapters/outbound/platform_native/platform_layer.py`
  становится dead code. Удалить `_scan_appimage_locations`,
  `_detect_kicad_cli_via_kicad_appimage`, multi-call AppImage
  logic; почистить glob-патрены и known locations
  (`~/Загрузки/`, `~/AppImages/`, `~/<app>/`). Подправить
  тесты в `tests/integration/adapters/platform_native/`:
  убрать AppImage reality-tests, оставить PATH-detection через
  apt. Пройтись по `pytest.mark.skipif` в integration/e2e —
  оставить только условие «kicad in PATH». Spec T009 пометить
  как partially-replaced. Acceptance: 0 строк кода специфичных
  для AppImage; все тесты зелёные при KiCad из apt; PR ловится
  pre-push gate как обычно.
<!-- T121 перенесена в BOARD.md → Doing (2026-05-20) — объединена
     с T114 в один PR (variant C). См. BOARD.md → T114 + T121. -->

- **T122** — [2026-05-20] **Fallback path: git clone KiCad-libraries
  из upstream GitLab** (вместо `docker pull efactory-libs`). Spec
  T110 §3 описывает primary / fallback пути для libraries bootstrap;
  T121 реализовал только primary (`docker create` + `docker cp`).
  Fallback нужен только в degraded scenario (нет сети к GHCR или
  registry недоступен) — раньше T115/CI смысла не имеет (до GHCR
  publish primary тоже local-only). Acceptance: `efactory-up
  --update-libs --no-registry` (или auto-fallback при failed
  `docker pull`) клонирует `https://gitlab.com/kicad/libraries/
  kicad-symbols`, `kicad-footprints`, `kicad-templates` (3dmodels
  — отдельно, тяжёлые) в `$HOME/efactory-libs/`, идемпотентно при
  повторе. Зафиксировано как out-of-scope T121 (Vladimir 2026-05-19,
  variant C).
- **T123** — [2026-05-20] **Убрать KiCad warning «Sim.Library не
  в symbol-library-table»** при открытии demo / любого
  efactory-сгенерированного `.kicad_sch`. Источник — путаница в
  KiCad 10: на открытии schematic смотрит каждое `Sim.Library`-
  property компонента и сравнивает с `sym-lib-table` (хотя `.lib`
  — это SPICE, а не symbol). Симуляция работает, warning безвреден,
  но появляется при каждом открытии — раздражает.
  Acceptance: при `./efactory-up --demo` (или любой схеме,
  сгенерированной через `adapters/outbound/schematic_kicad/facade`)
  KiCad открывает schematic без диалога «не в таблице».
  Два возможных пути (выбрать после исследования):
  (a) **Inline `.subckt`** в `Sim.Params` (или новый property) —
      без внешней `Sim.Library`. Минус: каждое использование одной
      и той же модели дублируется в schematic.
  (b) **Well-known path для всех SPICE-libs** — система регистрирует
      их где-то под `/usr/share/kicad/spice/` (или внутри
      `kicad_common.json`) так, чтобы KiCad сразу видел и не
      жаловался. Минус: нужно понять, что именно KiCad 10 проверяет
      и считает «валидным» путём.
  Затрагивает `src/adapters/outbound/schematic_kicad/facade.py`
  (метод `_add_simulation_props` и аналоги). T100-test'ы должны
  остаться зелёными (netlist export не меняется, меняется только
  GUI-warning поведение).
- **T125** — [2026-05-20] **Fix mypy на main — 64 ошибки в 8 файлах.**
  Обнаружено в pre-push T112 (mypy выдаёт те же ошибки на чистой `main`
  без T112-правок — значит регрессия пришла с предыдущим merge,
  скорее всего T114+T121 #54). Файлы:
  `tests/integration/adapters/graph_store/test_kuzu_smoke.py`,
  `tests/integration/adapters/subprocess_apps/test_app_manager.py`,
  `tests/unit/application/test_{create,delete,get,list}_project.py`,
  `tests/unit/application/test_design_to_{netlist,sim}.py`.
  Большинство — `incompatible type: FakeXRepository / expected
  XRepository protocol` (тестовые fake-репы рассинхронизированы с
  protocol после изменений в `ports/outbound/`). Acceptance:
  `uv run mypy src tests` → 0 ошибок. Контекст процесса: глобальная
  методика требует 0 ошибок перед каждым push; T112 не вводит новых
  ошибок, но прошёл pre-push gate в degraded state (надо признать
  и закрыть быстро отдельным PR `T125-fix-mypy`).
- **T124** — [2026-05-20] **freecad-mcp wrapper + integration.**
  Acceptance T112 изначально включал «freecad-mcp подключается,
  базовые tool-calls работают»; вынесено в отдельную задачу
  (Vladimir 2026-05-20 clarify-1). Содержание: Python wrapper
  поверх `freecadcmd` в `src/adapters/outbound/freecad/`, MCP-
  сервер с минимальным set'ом tool-calls (open document,
  create sheet metal base wall, add bend, unfold, export STEP/
  DXF), регистрация в общем MCP-реестре efactory. После выбора
  решения T108 (Claude Code как frontend) — wrapper должен
  отвечать на tool_use из агента. Acceptance: запуск MCP-сервера
  внутри efactory:linux, smoke tool-call «open empty document
  и create base wall» возвращает path к сохранённому `.FCStd`.
  Не блокировано: T112 (FreeCAD CLI / GUI) уже даёт `freecadcmd`,
  на котором wrapper может работать сразу.

### Phase 1b — Чат-клиент (+2–3 недели, исполняется внутри контейнера после Phase 0.9)

<!-- T011 перенесён в Tech Debt 2026-05-19: решено использовать
     Claude Code как frontend; пилот OpenCode = T108. Судьба
     T012-T016 (бэкенды, MCP-клиент, slash-команды, контекст-
     менеджмент, system prompt) будет переоценена после T108
     ADR — большая часть закрывается готовым frontend'ом
     "из коробки". Frontend живёт внутри Docker-образа
     (см. Phase 0.9). -->

- **T012** — [2026-05-15] `kicad-sim-chat`: бэкенд `claude-code-max`
  через `claude -p` (только генерация текста / tool_use, без
  исполнения).
  Acceptance: запрос пользователя → LLM генерирует tool_use →
  клиент исполняет инструмент → результат возвращается в LLM.
- **T013** — [2026-05-15] `kicad-sim-chat`: MCP-клиент с единым
  реестром инструментов (все 5 серверов) + tool use loop.
  Acceptance: при старте клиент подключает все настроенные
  MCP-серверы; инструменты доступны по полному имени.
- **T014** — [2026-05-15] `kicad-sim-chat`: базовые команды `/model`,
  `/tools`, `/project`, `/save`, `/load`.
  Acceptance: каждая команда выполняется, валидирует аргументы,
  показывает help при `/<cmd> --help`.
- **T015** — [2026-05-15] `kicad-sim-chat`: управление контекстным
  окном — summary + conversation compaction по триггеру (token budget).
  Acceptance: при достижении ~80% контекста бэкенда история
  сворачивается в summary, не теряя текущей задачи.
- **T016** — [2026-05-15] `kicad-sim-chat`: system prompt —
  статические блоки (роль, правила, инструменты) + динамический
  контекст (текущий проект, открытые файлы, последние результаты).
  Acceptance: при переключении проекта system prompt обновляется,
  старый контекст не утекает.

### Фаза 2 (+2 недели)

- **T017** — [2026-05-15] Бэкенд `anthropic-api`.
  Acceptance: переключение `/model anthropic claude-X` работает,
  tool use идентичен `claude-code-max`.
- **T018** — [2026-05-15] Бэкенд `openai-compat` (Anthropic SDK,
  OpenAI SDK, любой OpenAI-совместимый endpoint).
  Acceptance: можно подключить кастомный URL/key через
  `backends.toml`, tool use работает.
- **T019** — [2026-05-15] Конвертация контекста между форматами
  LLM (Anthropic ↔ OpenAI ↔ Claude Code).
  Acceptance: переключение бэкенда в середине сессии не теряет
  историю; tool calls конвертируются корректно.
- **T020** — [2026-05-15] Команда `/compare` — режим сравнения
  моделей на одном запросе.
  Acceptance: `/compare claude-X openai-Y` шлёт один промпт в обе
  модели, рендерит ответы рядом.
- **T021** — [2026-05-15] `bridge_edit_and_resim` с автосравнением
  результатов (до/после).
  Acceptance: после изменения схемы выводится дельта по ключевым
  метрикам (gain, bandwidth, THD).
- **T022** — [2026-05-15] Параметрический sweep (`bridge_sweep`)
  с визуализацией.
  Acceptance: sweep по 1-2 параметрам строит таблицу + график.
- **T023** — [2026-05-15] Измерения: THD, gain, bandwidth,
  phase margin как отдельные инструменты bridge.
  Acceptance: каждый инструмент возвращает значение + точку/диапазон,
  где оно измерено.
- **T024** — [2026-05-15] ASCII-графики через `plotext`.
  Acceptance: график АЧХ выводится в терминал, читаемый на ширине 80.
- **T025** — [2026-05-15] Визуализация схем: Sixel/Kitty protocol
  + fallback на `xdg-open` (Linux) / `start` (Windows).
  Acceptance: при поддержке терминала схема рендерится прямо в чат;
  иначе открывается во внешнем просмотрщике.
- **T026** — [2026-05-15] Конкурентный доступ к файлам: staged-
  модификации при открытом KiCad (`.kicad_sch.staged` → diff →
  apply через IPC reload).
  Acceptance: при изменении схемы из чата запущенный KiCad
  не теряет состояние, перезагружает изменения.
- **T027** — [2026-05-15] Шаблоны проектов: SE amp, PP amp, preamp,
  filter — в `templates/`.
  Acceptance: `/project create --template se-amp NAME` создаёт
  работающий проект с предзаполненной схемой и моделями.

### Фаза 3 (+2 недели)

- **T028** — [2026-05-15] Бэкенд Ollama с prompt injection fallback
  (для моделей без native tool use).
  Acceptance: tool use работает через текстовый протокол; при
  поддержке native — используется он.
- **T029** — [2026-05-15] Интеграция ERC/DRC через `kicad-mcp-pro`
  quality gates в pipeline.
  Acceptance: pipeline блокирует переход к экспорту, если ERC/DRC
  не зелёные; ошибки рендерятся понятно.
- **T030** — [2026-05-15] `model_import_url`: скачивание SPICE-моделей
  от производителей по URL с автоматической классификацией.
  Acceptance: URL TI/Vishay/ON Semi → модель добавлена в библиотеку
  с метаданными.
- **T031** — [2026-05-15] Интеграция Tube-curve-fitting (Gleb
  Zaslavsky): извлечение параметров Koren из сканов даташитов.
  Acceptance: даташит лампы → параметры Koren → .LIB-модель в
  библиотеке.
- **T032** — [2026-05-15] Рендер схемы в SVG (через kicad-cli) +
  визуальная проверка LLM (vision-режим, где доступно).
  Acceptance: схема → SVG → опционально показывается LLM для
  валидации топологии.
- **T107 Phase 1 (deferred)** — datasheet-accurate symbol drawing для
  советских ламп. Phase 0 (закрыт 2026-05-19, PR #46) реализован
  через copy-rename базовых EL84/ECC81 форм (visually одинаковы,
  отличается lib_id и Value). Phase 1 — нарисовать оригинальные
  shapes: GU50 (octal base с top-cap anode), 6П45С (specific beam
  tetrode shape), 6Н6П (octal dual triode layout). Drawing-heavy
  vector polyline work. Возможно делегировать LLM-vision при T032
  SVG render + T106 Phase 3 beautifier готовности (LLM смотрит
  datasheet картинку → генерирует s-expr polylines).
- **T106** — [2026-05-19] **Scheme layout beautifier.** Post-process
  валидного `.kicad_sch` (после ERC) для «textbook look»: убрать
  collisions подписей/компонентов/проводников, выровнять reference/
  value текст, сделать layout читаемым.

  **Edge:** Altium / KiCad auto-place были разработаны до multimodal
  LLM эры — их алгоритмы чисто deterministic-rule-based. У нас есть
  **iterative LLM-vision refinement** (через T032 SVG render → vision
  model → diff), которого pre-LLM tools физически не имели. Это
  потенциально даёт нам качество выше commercial EDA для нишевых
  схем (audio amps в нашем случае).

  **Phase 0 (rule-based, ~1 сессия):** детект label/value/reference
  text-on-component-body или text-on-wire overlap'ов через bbox
  intersection. Если есть — nudge text на свободную сторону компонента
  (4-direction polling). Acceptance: на наших фикстурах (RC, rectifier,
  CE, SE-amp, triode_amp) — ноль текстовых overlap'ов.

  **Phase 1 (rule-based, ~2 сессии):** wire-through-body detection
  (wire visually passes через symbol bbox без electrical pin contact)
  → reroute через «channel corridors» (горизонтальные/вертикальные
  free-from-bodies lanes между рядами компонентов). По T100 §Analyze
  W2 — это ≤50 LOC при правильной геометрии. Acceptance: SE-amp
  wires не идут визуально через тело лампы или OPT.

  **Phase 2 (rule-based, ~3 сессии):** component placement
  optimization — детект unaligned components (off-grid pin positions,
  asymmetric Y-spread), apply nudges и rotations для balanced layout
  (schematic-style symmetry: power вверху, GND внизу, signal flow
  слева-направо). Acceptance: auto-built ≈ mentor-style reference
  fixture.

  **Phase 3 (LLM-vision driven, наш main edge):** feed SVG-render
  схемы в multimodal LLM с промптом «оптимизируй визуал как audio
  textbook». LLM возвращает список patches (nudge label / rotate
  component / reroute wire), фасад применяет diff к `.kicad_sch`,
  итеративно до convergence. Acceptance: blind test — pre-LLM
  pipeline output vs T106-Phase3 output, выбираем «красивее»; T106
  выигрывает на ≥80% test cases.

  Зависит от **T032** (SVG render) — выход T032 = вход T106 Phase 3.
  Не блокирует Phase 1b LLM chat-client (chat работает с
  функционально верными схемами независимо от визуала).
- **T033** — [2026-05-15] Команда `/cost` — трекинг расходов на API
  по сессии и проекту.
  Acceptance: `/cost` показывает токены и стоимость по бэкендам.
- **T034** — [2026-05-15] Автодополнение команд и имён компонентов
  в Rich TUI.
  Acceptance: Tab дополняет команды, имена компонентов из текущей
  схемы, имена проектов.
- **T035** — [2026-05-15] Публикационный workflow:
  `export_schematic_publication`, `export_sim_report`.
  Acceptance: схема → SVG/PDF для статьи; результаты симуляции →
  Markdown-отчёт с графиками.
- **T036** — [2026-05-15, re-evaluate 2026-05-19 после Phase 0.9]
  Стратегия обновлений: флаги `--update`, `--update-models`,
  `--doctor` в bootstrap + CLI.
  **Re-evaluate:** после Phase 0.9 Containerization большая часть
  заменяется на `docker pull efactory:linux-latest`. Что
  остаётся актуальным — `--doctor` внутри образа (диагностика
  тулчейна, проверка GPU/X11 passthrough) и `--update-models`
  для пользовательских SPICE-моделей вне образа. Acceptance
  переоценить при взятии в работу.

### Фаза 4 — PCB-модуль (+3–4 недели)

- **T037** — [2026-05-15] `pcb_from_schematic`: создание `.kicad_pcb`
  из `.kicad_sch` (импорт нетлиста, контур платы, правила
  проектирования).
  Acceptance: схема → пустая плата с импортированным нетлистом и
  установленными правилами.
- **T038** — [2026-05-15] `pcb_place_components`: программное
  размещение через pcbnew API по стратегиям (`tube_amp`, `digital`,
  `smps`, `audio_analog`).
  Acceptance: компоненты разнесены по функциональным группам и
  тепловым зонам, soft-constraints выполнены.
- **T039** — [2026-05-15] `pcb_autoroute`: запуск FreeRouting CLI
  (DSN → SES → импорт), статистика completion rate.
  Acceptance: некритические цепи разведены автоматически, силовые
  и ВЧ исключаются.
- **T040** — [2026-05-15] `pcb_manual_route`: ручная трассировка
  критических цепей (силовые, ВЧ, дифф. пары) через pcbnew API.
  Acceptance: указанные сети разводятся по заданным маршрутам и
  ширинам.
- **T041** — [2026-05-15] `pcb_validate`: DRC + DFM + визуальная
  инспекция через рендер всех слоёв в SVG.
  Acceptance: возвращает структурированный отчёт по нарушениям
  и DFM-предупреждениям.
- **T042** — [2026-05-15] `pcb_export_manufacturing`: Gerber + drill
  + BOM + pick-and-place + STEP. Профили: `jlcpcb`, `generic`.
  Acceptance: для тестового проекта файлы валидны (Gerber viewer
  + JLCPCB upload OK).
- **T043** — [2026-05-15] `pcb_render`: SVG-рендер слоёв (top,
  bottom, all) для визуального контроля в чате.
  Acceptance: PNG/SVG показывается в чате (Sixel/Kitty) или
  открывается внешне.
- **T044** — [2026-05-15] `pcb_jlcpcb_check`: поиск компонентов в
  каталоге LCSC, оценка стоимости платы и монтажа.
  Acceptance: BOM → артикулы LCSC + смета (плата + компоненты +
  монтаж).
- **T045** — [2026-05-15] P2P bridge (навесной монтаж): инструменты
  `p2p_layout`, `p2p_wiring_table`, `p2p_wiring_diagram`,
  `p2p_assembly_order`.
  Acceptance: `--assembly p2p` при создании проекта → инструменты
  доступны; для тестового SE-amp генерируются раскладка + таблица
  + порядок монтажа.
- **T046** — [2026-05-15] Многоплатные проекты: поддержка нескольких
  `.kicad_sch`/`.kicad_pcb` в одном проекте, межплатные соединения,
  спецификация кабелей и жгутов.
  Acceptance: проект с 2+ платами собирается в общую 3D-сборку,
  общий BOM, таблица разъёмов.
- **T047** — [2026-05-15] `pcb_emi_check`: автоматический аудит
  помехозащиты (заземление, экранировка, полигоны, развязка
  питания, накальные цепи).
  Acceptance: возвращает список нарушений с приоритетами и
  рекомендациями.
- **T048** — [2026-05-15] `safety_checklist`: автоматический чеклист
  электробезопасности (разрядные R, предохранители, заземление,
  зазоры ВН).
  Acceptance: схема → Markdown/PDF-чеклист + карта зазоров.
- **T049** — [2026-05-15] `psu_wizard`: wizard блоков питания
  (линейные топологии: CLC, CLCRC, стабилизаторы; SMPS: Buck, Boost,
  Buck-Boost, Flyback, Forward, Half-Bridge).
  Acceptance: ТЗ → схема БП + рассчитанные номиналы + моделирование
  пульсаций.

### Фаза 5 — Намоточные изделия (+3 недели)

- **T051** — [2026-05-15] `mag_select_core`: подбор сердечника по
  ТЗ (мощность, частота, габариты, материал) из базы OpenMagnetics
  (10 000+ сердечников).
  Acceptance: ТЗ → список топ-N сердечников с обоснованием выбора;
  поддержаны кремнистая сталь (аудио) и ферриты (ИИП).
- **T052** — [2026-05-15] `mag_design_transformer`: полный расчёт
  трансформатора — число витков, сечение провода (с AC-эффектами:
  скин, proximity), конфигурация слоёв и секционирование, изоляция,
  заполнение окна.
  Acceptance: для тестовых ТЗ (SE-OPT 6П14П, силовой 50 Гц,
  flyback SMPS) выводится полная спецификация обмоток, проходит
  проверка заполнения окна.
- **T053** — [2026-05-15] `mag_design_choke`: расчёт дросселя —
  индуктивность, ток подмагничивания, зазор; для SMPS — ripple
  current и core loss; синфазные дроссели для EMI-фильтров.
  Acceptance: ТЗ дросселя → конструктивный расчёт + проверка
  отсутствия насыщения.
- **T054** — [2026-05-15] `mag_calc_parasitics`: расчёт паразитов
  (Llk, Cw, Rp, Rs, Rc) → генерация SPICE-модели `.subckt`,
  совместимой со SPICEBridge.
  Acceptance: расчётный `.subckt` загружается в pipeline моделирования,
  АЧХ трансформатора совпадает с расчётной в пределах допуска.
- **T055** — [2026-05-15, renamed/refactored 2026-05-19]
  `mag_verify_field` (solver-agnostic, бывш. `mag_verify_femm`):
  верификация магнитного поля через Linux-native FEM-solver
  (Elmer FEM primary, GetDP fallback — выбор по T113).
  Экспорт solver input, запуск, парсинг. ADR — `DECISIONS.md`
  2026-05-19 «Magnetic field verification: Linux-native
  FEM-solver». Acceptance: распределение поля и значения
  индуктивности возвращаются в чат; рассогласование с
  PyOpenMagnetics-расчётом подсвечивается; solver-agnostic
  port в `adapters/outbound/fem_solver/` позволяет подменить
  backend без слома domain.
- **T056** — [2026-05-15] `mag_build_3d`: 3D-модель магнитного
  компонента через MVB → FreeCAD (сердечник + каркас + обмотки) +
  экспорт STEP.
  Acceptance: STEP-файл импортируется в сборку корпуса (Фаза 6)
  без коллизий.
- **T057** — [2026-05-15] `mag_export_winding_spec`: спецификация
  для намотчика (PDF/Markdown) — сердечник, каркас, таблица обмоток,
  порядок намотки, изоляция, пропитка, параметры приёмки.
  Acceptance: спецификация валидируется на тестовом OPT — все поля
  заполнены, диаграмма послойной намотки читается.
- **T058** — [2026-05-15, absorbed 2026-05-19 by T113] ~~Bootstrap:
  установка FEMM (системно) + pyFEMM (Python) на Linux и Windows;
  обновление `compatibility.toml`.~~ **Absorbed by T113** (FEM-solver
  pilot + integration в Phase 0.9): Linux-native solver (Elmer /
  GetDP) ставится в Dockerfile, отдельная bootstrap-задача не
  нужна. FEMM сам заменён в ADR от 2026-05-19.

### Фаза 6 — Проектирование корпуса (+3–4 недели)

- **T059** — [2026-05-15] Подключение `freecad-mcp` как 5-го
  MCP-сервера в `kicad-sim-chat` (профиль конфигурации + проверка
  доступности FreeCAD).
  Acceptance: после `bootstrap` инструменты `freecad-mcp` доступны
  в чате по полному имени.
- **T060** — [2026-05-15] `enclosure_from_pcb`: импорт STEP платы
  (из `kicad-cli pcb export step`) в FreeCAD, создание базовой
  формы шасси по габаритам платы с отступами.
  Acceptance: для тестовой платы 200×150 мм генерируется корпус
  с правильными отступами и крепёжными отверстиями, совмещёнными
  с платой.
- **T061** — [2026-05-15] `enclosure_add_cutout`: добавление вырезов
  — круглый (под панельку/потенциометр), прямоугольный (под разъём),
  произвольный по контуру.
  Acceptance: для тестового корпуса добавляются вырезы под октальную
  панельку, IEC-ввод, потенциометр; интерференций нет.
- **T062** — [2026-05-15] `enclosure_sheet_metal`: применение
  workbench Sheet Metal — сгибы, фланцы, стойки для крепления
  платы; генерация развёрток.
  Acceptance: для тестового шасси выводится корректная развёртка
  с указанием линий сгиба.
- **T063** — [2026-05-15] `enclosure_assembly`: сборка
  плата + корпус + крепёж + трансформаторы (Assembly workbench),
  проверка зазоров и интерференций.
  Acceptance: для тестовой системы (плата + корпус + 2 трансформатора)
  сборка собирается без интерференций; отчёт о зазорах генерируется.
- **T064** — [2026-05-15] `enclosure_export`: DXF развёртки панелей,
  STEP сборки, STL для 3D-печати прототипа, PDF чертежей TechDraw.
  Acceptance: все четыре формата валидны (DXF открывается лазерным
  раскроем, STL — слайсером, STEP — KiCad/FreeCAD).
- **T065** — [2026-05-15] `enclosure_render`: 3D-рендер сборки для
  визуального контроля (PNG/SVG в чат через freecad-mcp).
  Acceptance: рендер показывается в терминале (Sixel/Kitty) или
  открывается внешне.
- **T066** — [2026-05-15, absorbed 2026-05-19 by T112] ~~Bootstrap:
  установка FreeCAD 1.0+ + addon Sheet Metal на Linux и Windows;
  обновление `compatibility.toml`.~~ **Absorbed by T112** (FreeCAD
  CLI + GUI в образе, Phase 0.9): FreeCAD и Sheet Metal addon
  ставятся в Dockerfile, отдельная bootstrap-задача не нужна.

### Фаза 7 — Производственная документация (+2 недели)

- **T067** — [2026-05-15] Команда `/export-production <project>
  [--format jlcpcb|generic] [--lang ru|en]`: сборка полного пакета
  документации (schematic / simulation / pcb или p2p / magnetics /
  enclosure / cables / sourcing / safety / specifications) одним
  вызовом.
  Acceptance: для тестового проекта генерируется полный
  `production-package/` по §7.1 концепта.
- **T068** — [2026-05-15] Sourcing: интеграция Mouser API — поиск
  по part number, цены, наличие, артикулы.
  Acceptance: BOM → `sourcing_mouser.csv` с актуальными ценами и
  доступностью.
- **T069** — [2026-05-15] Sourcing: интеграция DigiKey API —
  аналогично T068.
  Acceptance: BOM → `sourcing_digikey.csv` с актуальными ценами и
  доступностью.
- **T070** — [2026-05-15] Sourcing: интеграция LCSC (JLCPCB) через
  `kicad-mcp-pro` — поиск, артикулы, оценка стоимости монтажа.
  Acceptance: BOM → `sourcing_lcsc.csv` + оценка стоимости платы
  с монтажом.
- **T071** — [2026-05-15] Сводный BOM по всем платам / корпусу /
  намоточным / кабелям (`consolidated_bom.xlsx`).
  Acceptance: для многоплатного тестового проекта формируется
  единый BOM без дублирования.
- **T072** — [2026-05-15] Cost estimate: смета по поставщикам с
  разбивкой и общей стоимостью (`cost_estimate.md`).
  Acceptance: смета содержит детализацию по поставщикам, валютам,
  и итоговую сумму с учётом доставки (оценочно).
- **T073** — [2026-05-15] `bridge_import_measurement`: импорт
  измерений с приборов — CSV (осциллограф, анализатор), Touchstone
  (.s1p/.s2p — NanoVNA), Rigol/Siglent CSV, ручной ввод (мультиметр).
  Acceptance: каждый из четырёх форматов загружается без ошибок,
  данные нормализуются к внутреннему формату.
- **T074** — [2026-05-15] `bridge_compare_sim_vs_measured`:
  наложение измерений на результаты симуляции, отчёт о расхождениях
  (АЧХ, рабочие точки, паразиты трансформаторов).
  Acceptance: для тестового проекта генерируется
  `sim_vs_measured.pdf` с графиками и таблицей расхождений.
- **T075** — [2026-05-15] Шаблоны документов: `device_spec.md` (ТТХ),
  `test_protocol.md` (протокол испытаний с ожидаемыми значениями),
  `emi_report.md` (отчёт по помехозащите).
  Acceptance: для тестового проекта все три документа генерируются
  и наполняются актуальными значениями из результатов фаз 1–6.

### Фаза 8 — Будущее

- **T076** — [2026-05-15] Web-интерфейс для удалённого доступа к
  `kicad-sim-chat` (без замены TUI, дополнительный фронтенд).
  Acceptance: запуск web-server, базовый чат-UI работает поверх той
  же бэкенд-логики.
- **T077** — [2026-05-15] Streaming для API-бэкендов (Anthropic,
  OpenAI-compat) — токен-за-токеном вывод в TUI.
  Acceptance: ответ LLM рендерится с задержкой <100 мс на первый
  токен.
- **T078** — [2026-05-15] Параллельный запрос на несколько моделей
  (расширение `/compare`): одновременная отправка в N бэкендов,
  агрегированный вывод.
  Acceptance: 3 модели опрашиваются параллельно; время = max, а не
  sum.
- **T079** — [2026-05-15] Интеграция официального `kicad-python`
  (IPC API) для редактирования схем — когда появится поддержка
  `.kicad_sch` в upstream. Заместит часть функциональности
  `kicad-sch-api`.
  Acceptance: pipeline работает через kicad-python для базовых
  операций со схемой; ADR в `DECISIONS.md` фиксирует решение.
- **T080** — [2026-05-15] SSE-транспорт для MCP-серверов (доступ
  с телефона / удалённо).
  Acceptance: `kicad-sim-bridge` поднимается по SSE; мобильный
  MCP-клиент подключается и исполняет инструменты.
- **T081** — [2026-05-15] Панелизация: объединение нескольких плат
  в одну производственную панель с отбоиваемыми перемычками.
  Acceptance: на вход — несколько `.kicad_pcb`, на выход — единый
  Gerber-набор панели с tooling-вырезами.
- **T082** — [2026-05-15] Экспорт IPC-2581 (современная альтернатива
  Gerber).
  Acceptance: для тестового PCB выводится валидный IPC-2581 файл,
  проходит проверку viewer-ом.
- **T083** — [2026-05-15] Интеграция с другими производителями PCB:
  PCBWay, OSHPARK, Elecrow — профили экспорта в `pcb_export_manufacturing`.
  Acceptance: для каждого производителя — рабочий профиль,
  загружаемый файл-пакет, оценка стоимости.
- **T084** — [2026-05-15] RF-модуль: S-параметры, Smith chart,
  модели линий передачи, интеграция NanoVNA для измерений.
  Acceptance: для RF-проекта (тестовый антенный согласователь)
  снимаются S-параметры, рендерится Smith chart, сравнение с
  симуляцией.

### Phase Cross-platform — Mac/Windows поддержка (после стабилизации Linux Docker workflow)

<!-- Введена решением 2026-05-19 (DECISIONS.md «Distribution:
     Linux Docker image»). Отдельная фаза с собственным
     acceptance, чтобы не блокировать Linux-only итерацию.
     Берётся в работу после того, как Phase 0.9 + 1a + 1b
     стабильно работают на Linux. -->

- **T116** — [2026-05-19] Docker Desktop на Windows: запуск
  efactory через WSL2 / WSLg для GUI passthrough. Документация
  по установке и known-issues. Acceptance: на чистой Windows 11
  + Docker Desktop + WSLg `./efactory-up.ps1` (или эквивалент)
  запускает KiCad GUI из контейнера; задача создания SE-amp
  проходит end-to-end.
- **T117** — [2026-05-19] Docker Desktop на macOS: запуск
  efactory через Docker Desktop + XQuartz (Intel) или
  Docker Desktop + native macOS XQuartz (Apple Silicon).
  Multi-arch image (linux/amd64 + linux/arm64) для Apple
  Silicon — проверить, что весь стек собирается на arm64
  (KiCad да; FreeCAD да; FEM-solver — проверить Elmer/GetDP
  на arm64). Acceptance: на чистой macOS 14+ задача SE-amp
  проходит end-to-end.
- **T118** — [2026-05-19] **Опционально:** native FEMM fallback
  для пользователей, которым нужна совместимость с
  существующими FEMM-моделями индустрии. Реализуется только
  если возникнет реальный запрос. ADR — `DECISIONS.md`
  2026-05-19 «Magnetic field verification».
  Acceptance: opt-in путь через флаг конфигурации,
  переключающий FEM-backend с Elmer/GetDP на FEMM (native
  на хосте, не в контейнере).
- **T119** — [2026-05-19] Native fallback distribution для
  пользователей без Docker (corporate restrictions и т.п.):
  возрождение T002/T003 как opt-in пути. Acceptance —
  переоценить при реальном запросе.
