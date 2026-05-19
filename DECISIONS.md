# Architecture Decisions

ADR-Lite: компактный лог архитектурных решений с обоснованиями.
Цель — через полгода можно ответить на вопрос «а почему мы тогда так
сделали?», не реконструируя контекст по коммитам.

## Формат

Каждое решение — короткий блок:

- **Дата** — когда принято.
- **Решение** — что решили (1 строка).
- **Контекст** — какая задача / ограничение к нему привели.
- **Альтернативы** — что рассматривали и почему отвергли.
- **Последствия** — что это нам теперь даёт и чего лишает.

Решения не редактируются после фиксации. Если решение пересмотрено —
добавляется новый блок со ссылкой на старый, старый помечается как
«Заменено решением от <дата>».

---

## Решения проекта

<!-- Реальные решения добавляются сюда, новые сверху. При совпадении
     дат — от фундаментального к инструментальному. -->

### 2026-05-19 — Distribution: Linux Docker image с полным стеком (включая GUI), кроссплатформенность отложена в отдельную фазу

- **Контекст:** efactory интегрирует разнородный тулчейн —
  KiCad 10 (GUI + CLI), ngspice, FreeCAD (CLI + GUI), FEM-solver
  для магнетики, Python 3.14 stack, Claude Code как frontend
  агента, MCP-серверы. Установка этого стека на машину
  пользователя выглядела как **T002 (bootstrap.sh для Linux)** +
  **T003 (bootstrap.ps1 для Windows)** + **T036 (--update /
  --doctor)** + **T058 (FEMM bootstrap)** + **T066 (FreeCAD
  bootstrap)** — суммарно ~500 строк bash+ps1 + ручное
  координирование версий через `compatibility.toml`. Пять
  независимых релизных циклов + Wine для FEMM = постоянный
  versioning hell у пользователя. Параллельно встал вопрос
  **изоляции runtime-агента** от dev-инстанса Claude Code
  (mem0, методика dreamteam, личные настройки) — для чистоты
  эксперимента и будущей передачи продукта пользователям.
- **Решение:** **Distribution = Linux Docker image с полным
  стеком, включая GUI.** Один образ `efactory:linux` содержит:
  KiCad из официального KiCad-репозитория (apt), ngspice,
  FreeCAD из репозитория, Linux-native FEM-solver (см.
  отдельный ADR от 2026-05-19 о замене FEMM), Python 3.14 +
  uv + весь efactory код, Claude Code как frontend агента,
  наши MCP-серверы. GUI приложений (eeschema, pcbnew, FreeCAD)
  выкидывается через X11/Wayland passthrough; GPU acceleration —
  через `/dev/dri` (Intel/AMD) или nvidia-runtime. Наружу через
  volume mounts: папка проектов пользователя, папка библиотек,
  `~/.claude/.credentials.json:ro` для Claude Code auth.
  Запуск — единым shell-скриптом `efactory-up`.
  **Кроссплатформенность отложена** в отдельную фазу
  «Cross-platform» (Docker Desktop / WSLg / Colima support —
  Phase 8 или позже).
- **Альтернативы:**
  - **Native install через bootstrap-скрипты (status quo, T002/
    T003)** — отвергли: пять разных тулов с независимыми
    релизными циклами + Wine для FEMM = постоянный versioning
    hell. Compatibility.toml лечит только знание, не сам факт
    рассогласования у пользователя.
  - **Headless Docker гибрид (Docker для CLI, native KiCad на
    хосте для GUI)** — рассматривался как промежуточный шаг.
    Отвергли: пользователь всё равно должен установить KiCad
    нативно (та же versioning-hell), Docker даёт только CLI-
    изоляцию. Меньше выигрыш ценой архитектурной двойственности
    «что внутри, что снаружи».
  - **Полный Docker с кроссплатформенностью с первого дня**
    (Mac/Win Docker Desktop с XQuartz / WSLg) — отвергли как
    стартовую цель: GUI passthrough на Mac/Win нетривиальный,
    overhead через VM (Docker Desktop на не-Linux крутит свою
    Linux VM), Wine FEMM в двойной виртуализации = боль.
    Linux-only сейчас даёт чистый прирост без этих рисков;
    cross-platform как отдельная фаза с собственным acceptance.
  - **Подождать KiCad schematic IPC API (Phase 8 концепта)** —
    отвергли как несвязанный вопрос: IPC API про коммуникацию
    с KiCad-процессом, distribution-проблема не уходит.
- **Последствия:**
  - **T002 (bootstrap.sh Linux) → replaced by T110 (Dockerfile).**
    Native bootstrap для Linux больше не пишется — функция
    закрыта образом.
  - **T003 (bootstrap.ps1 Windows) → parked** до Phase
    Cross-platform; реализация отложена до тех пор, пока
    Linux-only Docker workflow не отшлифован.
  - **T036 (--update / --doctor / --update-models)** →
    re-evaluate. Часть функциональности заменяется
    `docker pull efactory:latest` + `docker run efactory --doctor`
    (внутрь образа кладём диагностику тулчейна).
  - **T058 (FEMM bootstrap), T066 (FreeCAD bootstrap)** →
    absorbed в T113/T112 (FEM-solver и FreeCAD ставятся в
    Dockerfile, отдельные bootstrap-задачи не нужны).
  - **Изоляция runtime-агента от dev-инстанса (рассматривалась
    через `CLAUDE_CONFIG_DIR`)** — закрыта **бесплатно как
    побочный эффект Docker**. Контейнер не видит ни моего
    `~/.claude/CLAUDE.md`, ни mem0, ни tools-MCP — туда попадает
    только то, что заложено в Dockerfile.
  - **`compatibility.toml`** становится **информационным**
    артефактом (для отчётности по версиям внутри образа);
    источник истины — Dockerfile с pinned версиями.
  - **Кроссплатформенность как принцип в README** ослабляется:
    «Linux первой фазой, кросс-платформа как отдельная Phase
    Cross-platform». Не отказ от поддержки Mac/Windows, а
    осознанная decomposition по времени.
  - **Размер образа** ожидаемо 8–12 GB (KiCad libraries ~3 GB +
    FreeCAD ~1.5 GB + FEM-solver ~500 MB + Python stack).
    Приемлемо для desktop-distribution, не для CI fat-pull;
    для CI-нагрузок будем держать минимальный slim-вариант без
    GUI (`efactory:linux-headless`) — детали в spec T110.
  - **Новая фаза в roadmap** — «Phase 0.9 Containerization»
    встаёт **между Phase 1a и Phase 1b**: до того, как делать
    chat-client / runtime-агента, нужно положить весь
    инструментарий в один воспроизводимый образ. Задачи:
    T110-T115 (см. BACKLOG.md). После Phase 0.9 все
    дальнейшие фазы исполняются внутри контейнера.

### 2026-05-19 — Magnetic field verification: Linux-native FEM-solver (Elmer FEM primary, GetDP+Gmsh fallback), FEMM как legacy

- **Контекст:** ADR от 2026-05-15 фиксировал **FEMM + pyFEMM**
  как 2D-FEA для верификации магнитного поля трансформаторов и
  дросселей (T055 `mag_verify_femm`). FEMM — это нативно-
  Windows-приложение; на Linux запускается через Wine. При
  переходе на Linux Docker distribution (ADR от 2026-05-19
  выше) FEMM/Wine становится узкой точкой:
  - Wine layer внутри Docker = двойная виртуализация на
    Mac/Windows (когда дойдёт до Phase Cross-platform).
  - FEMM не обновляется активно (последний major release ~2019).
  - GUI FEMM через Wine + X11 passthrough — лишний шаг с
    хрупким UX.
  - На Linux есть зрелые native-альтернативы для magnetostatic
    2D/3D FEA.
- **Решение:** **FEMM заменяется Linux-native FEM-solver'ом**.
  Кандидаты для пилотного выбора в рамках T113:
  - **Elmer FEM (primary)** — open-source multi-physics solver,
    Linux-native, имеет GUI (ElmerGUI), Python API через
    elmer-tools / ElmerSolver CLI, лучше параллелится,
    активно развивается. Используется в академии и индустрии
    для электромашин и трансформаторов.
  - **GetDP + Gmsh (fallback)** — академический мейнстрим для
    электромагнитики (авторы — те же люди, что делают Gmsh),
    более низкоуровневый (требует weak form), но проверен на
    десятилетиях работ с трансформаторами и электромашинами.
  Окончательный выбор — после пилотного сравнения в **T113**
  (Containerization phase): какой solver проще интегрировать
  в efactory pipeline (input — MAS JSON от PyOpenMagnetics,
  output — поля + индуктивности + потери), какой даёт
  стабильные результаты на тестовых OPT/SMPS-трансформаторах,
  какой проще для LLM-driven автоматизации. **PyOpenMagnetics
  остаётся** как ядро магнитного дизайна — заменяется только
  FEM-верификация.
- **Альтернативы:**
  - **FEMM в Docker через Wine** — отвергли: двойная
    виртуализация на не-Linux, хрупкий GUI passthrough,
    FEMM не активно развивается, упускаем возможность
    перейти на нативный Linux-инструмент.
  - **FreeFEM** — рассматривался: magnetostatic module есть,
    но ориентирован на исследователей-математиков (DSL для
    weak form), менее инженерный workflow, чем Elmer.
  - **FEniCS / FEniCSx** — мощнейший Python-FEM framework,
    но требует написания weak form вручную; overhead обучения
    для нашего use case (готовый magnetostatic workflow
    интереснее, чем PDE-конструктор).
  - **Подождать Linux-port FEMM** — нет таких планов в upstream
    (FEMM поддерживается одним мейнтейнером с 2019, native
    Linux никогда не был приоритетом).
  - **Коммерческие (Ansys Maxwell, COMSOL)** — отвергли по
    тому же принципу первого ADR (open-source-first).
- **Последствия:**
  - **ADR от 2026-05-15 «PyOpenMagnetics + FEMM»** — **частично
    заменён** этим ADR в части FEMM. PyOpenMagnetics остаётся
    как ядро магнитного дизайна; FEMM-секция заменяется на
    Linux-native solver (выбор после T113 пилота).
  - **T055 (`mag_verify_femm`)** — переименование и переоценка
    acceptance: solver-agnostic API в efactory (`mag_verify_field`
    с pluggable backend), внутри которого первая реализация —
    через Elmer (или GetDP по результатам T113).
  - **T058 (FEMM bootstrap)** — переименуется в T113
    (FEM-solver pilot + integration) и absorbed в Dockerfile.
  - **MAS JSON формат** остаётся как input стандарт — Elmer/
    GetDP принимают meshing input (geometry + материалы),
    преобразование MAS → solver input делает наш orchestration
    layer (~50–100 строк Python в `adapters/outbound/fem_solver/`).
  - **Phase Cross-platform (будущее):** возможно появится
    fallback на нативный FEMM/Wine для пользователей, которым
    нужна совместимость с существующими FEMM-моделями
    индустрии — но это **opt-in**, не основной путь.

### 2026-05-19 — Сторонние review-боты: CodeRabbit как best-effort, primary path = self-review + опциональный `/ultrareview`

- **Контекст:** T094 закрытие — что делать с CodeRabbit integration.
  Ретро `[0.2.0]` (2026-05-17) задокументировало проблему: rate-limit
  хитнул 6+ PR из 9, status-check показывал SUCCESS без реального
  ревью. На milestone `[0.4.0]` Vladimir Pro plan исчерпал credits;
  ретро `[0.5.0]` — оба бота (CodeRabbit + Qodo) silently не давали
  ревью на 7 PR.
  Решение нужно зафиксировать прежде чем стартует Фаза 1b (где скорость
  итераций повысится — LLM chat development) — нельзя продолжать
  делать вид что external review работает.
- **Решение:** **вариант (в)** из BACKLOG T094 — заменить CodeRabbit
  на user-triggered `/ultrareview` для критичных PR'ов. CodeRabbit
  integration остаётся подключённой, но трактуется как **best-effort
  signal** (если что-то полезное сказал — учитываем; rate-limit/no-
  credit silent — не блокирует merge). Primary review path: **Гвидо
  self-review с 7-point checklist** (scope / архитектура / код / гейты
  / документация / соглашения / безопасность), Vladimir-review по
  желанию, `/ultrareview` для архитектурно-критичных или security-
  sensitive PR'ов.
- **Альтернативы:**
  - **(а) Подключить paid plan CodeRabbit полноценно.** Отвергнуто:
    cost-benefit неясен — на `[0.4.0]` Pro plan кончился через 7-8 PR,
    значит usage profile быстро превышает Pro budget. Hobbyist project,
    не commercial team — затраты не оправданы. Vladimir может
    пересмотреть позже если pattern usage станет регулярным.
  - **(б) Полностью отключить CodeRabbit.** Отвергнуто: integration
    уже подключена, бот при наличии credits даёт неплохие insights
    occasionally. «Best-effort» tier нас не штрафует — silent rate-
    limit просто игнорируется.
  - **Оставить status quo (всё как есть, без явного решения).**
    Отвергнуто: ретро 0.2.0/0.4.0/0.5.0 повторяли одну и ту же
    жалобу — нужно зафиксировать обращение к проблеме иначе она
    останется ноющим долгом.
- **Последствия:**
  - **Self-review с 7-point checklist обязателен на каждом PR**
    (уже de facto практика, теперь явно как primary review path).
  - **`/ultrareview`** доступен Vladimir-у для важных PR'ов
    (cross-cutting refactor, security-sensitive changes, фазовые
    milestone'ы). Поскольку он user-triggered (билируется по time),
    не каждый PR — выборочно.
  - **CodeRabbit silent rate-limit/no-credit не блокирует merge** —
    раньше иногда возникало психологическое сомнение «надо ли ждать
    бот». Now explicitly: нет, merge'аем по self-review.
  - **Qodo (qodo-code-review)** — отдельный бот, тоже paused на user.
    Не отключаем — той же логикой best-effort.
  - **Не закрытое направление:** если Phase 1b (LLM chat) generates
    много PR'ов от LLM-driven workflow, может возникнуть necessity
    для batch review automation — пересмотрим (новый ADR, возможно
    paid plan-комбо).

### 2026-05-18 — Programmatic schematic generation: собственный фасад `efactory.schematic` поверх `sexpdata` (вариант D)

- **Контекст:** для T011–T014 (LLM chat-client фазы 1b) и для
  всех SPICE-сценариев (RC, выпрямитель, SE-amp на 6П14П) нужен
  программный способ строить `.kicad_sch`. Ручной s-expr на T008
  оказался хрупким (Y-down vs Y-up, кастомные `lib_symbols` валят
  KiCad GUI, GND через power-symbol с substitution на net 0, KiCad
  SPICE pin-order quirks) — каждая фикстура превращалась в
  микропроект «обучения» Гвидо. Pre-spike (2026-05-18):
  `kicad-sch-api` 0.5.6 **читает** наш KiCad 10 файл, но
  `components.add(lib_id='Device:R', ...)` падает с
  `LibraryError: Symbol 'Device:R' not found` — в KiCad 10 файлы
  библиотек переехали в `*.kicad_symdir/` директории с бинарными
  per-symbol `.kicad_sym`, парсер 0.5.6 ожидает легаси текстовый
  формат «один `Device.kicad_sym` со всеми символами» (KiCad ≤8).
  Дополнительно: библиотека втягивает 78 транзитивных пакетов
  (mcp/fastmcp/uvicorn) — нам не нужен встроенный MCP-сервер.
- **Решение:** **вариант D из спеки T100** — собственный фасад
  `adapters.outbound.schematic_kicad` поверх `sexpdata`. API: класс
  `Schematic(name)` с методами `add_resistor / add_capacitor /
  add_inductor / add_diode / add_v_dc / add_v_ac / add_v_sin /
  add_v_pulse / add_bjt_npn / add_bjt_pnp / add_mosfet_nmos /
  add_mosfet_pmos / add_tube_subcircuit / add_transformer_subcircuit
  / add_ground / add_pwr_flag / connect(pin_a, pin_b) / label /
  save(path)`. Embedded `lib_symbols` snippets (14 шт., text
  `.sexp` под `src/adapters/outbound/schematic_kicad/lib_symbols/`,
  force-include в wheel) — `.kicad_sch` self-contained, не зависит
  от глобальной `KICAD_SYMBOL_DIR` машины-получателя. Hexagonal:
  port `ports.outbound.schematic_writer.SchematicWriter` + adapter
  `KicadSchematicWriter` + domain VO в `domain.schematic` (Pin /
  ComponentSpec / WireSpec / etc.). GND-convention сохранена как
  в T004: фасад ставит `power:GND`-instance, `GND → 0` substitution
  делает `KicadCliSchematicExporter`.
- **Альтернативы:**
  - **(A) Форк `kicad-sch-api`** с поддержкой `*.kicad_symdir/`
    (binary per-symbol) формата KiCad 10. MIT-лицензия разрешает.
    Отвергли: параллельный maintenance чужого кода + 78-deps
    цепочка с MCP-балластом остаётся, а winnings — лишь чтение
    бинарного формата, которое нам не нужно (мы пишем
    самодостаточные snippets).
  - **(B) Bundled freeze KiCad 8/9 текстовых `.kicad_sym` + `kicad-
    sch-api` как backend.** Положить рядом с фасадом «freeze»-копию
    легаси-библиотек (Device, Simulation_SPICE, power) и feed-ить
    их в cache `kicad-sch-api`. Отвергли: библиотеки KiCad 8 ≠
    KiCad 10 (UUID, properties), на load в KiCad 10 могут быть
    warnings; всё ещё 78-deps балласт. Оставлен как **kill-switch
    fallback** на случай провала Phase 0 (не понадобился).
  - **(C) Bypass cache** через monkey-patch / subclass
    `Components`, чтобы `add()` не валидировал существование
    символа в cache. Минимально инвазивно, но хрупко на upgrade
    `kicad-sch-api`.
  - **(E) Подождать upstream `kicad-python` IPC API для схем.** На
    2026-05-18: `kicad-python` 0.7.1 покрывает только PCB, GitLab
    issue #2077 «Schematic Editor Python API» открыт с 28.10.2017
    (8.5 лет) без milestone, реалистичный горизонт KiCad 11
    (~2027) или KiCad 12 (~2028). IPC требует running KiCad с API
    server — плохо ложится на headless CI / batch-LLM / kicad-cli
    pipeline. Будет уместен для T026 (staged-modifications при
    открытом GUI) и для части T079 (Phase 8), но **рядом** с
    генератором, а не вместо.
  - **SKiDL.** Отвергли в pre-spike: генерирует netlist для PCB, а
    не `.kicad_sch` — теряется визуальная схема, KiCad GUI не
    нужен.
- **Последствия:**
  - **Полный контроль над API под наш use case.** Phase 1b
    (LLM-driven design) — функции под LLM-тулчейн, не под чужого
    мейнтейнера. Hexagonal port позволяет подменить backend
    (например, на upstream IPC в Phase 8) без слома
    пользовательского фасада `efactory.schematic`.
  - **Zero лишних deps.** Единственная новая runtime-зависимость —
    `sexpdata` (уже была у `kicad-sch-api`, MIT, чистый Python).
    Не пришли 78 транзитивных пакетов с MCP-стеком.
  - **Self-contained `.kicad_sch`.** Embedded lib_symbols snippets
    (14 шт.) делают файлы переносимыми между машинами без
    `KICAD_SYMBOL_DIR` синхронизации.
  - **Acceptance достигнут.** Фазы 0–2 закрыли RC-фильтр /
    half-wave rectifier / common-emitter BJT / SE-amp 6П14П
    (через T006 tube subckt). ERC = 0 в `kicad-cli`, валидный
    SPICE netlist, ngspice прогоняет OP/TRAN/AC ожидаемо. Coverage
    на `src/adapters/outbound/schematic_kicad/`: facade 97%, writer
    100%. Старая ручная фикстура `tests/fixtures/rc_filter.kicad_sch`
    (149 строк s-expr) удалена в Phase 3 — строится фасадом через
    `tests/conftest.py::rc_filter_schematic_path`.
  - **Цена.** Мы поддерживаем собственный s-expr serializer и
    embedded `lib_symbols` snippets. **План миграции на KiCad 11
    / 12:** при выходе новой версии открыть фикстуру в новом KiCad
    GUI, пересохранить, обновить snippets (1–2 часа на minor).
    Тесты через `kicad-cli erc` ловят несовместимость немедленно
    при апгрейде CI.
  - **Не закрытые направления (вынесены в BACKLOG).** Многолистные
    иерархические схемы (Phase 2 концепта), wire-router для >10
    компонентов (если SE-amp начнёт давать ложные junction'ы),
    рендер SVG для LLM-vision (T032), upstream IPC API (T079).

### 2026-05-17 — Domain expansion direction: D (Phase VO → Manifest primary → Decision aggregate)

- **Контекст:** после 0.2.0 у нас закрыт минимальный CRUD по
  `domain.Project` (Create / List / Show / Delete), но фундамент
  не проверен на: (1) Update use case (единственный stored field
  `status` имел ровно одно значение `CREATED`), (2) множественные
  агрегаты в одном domain'е, (3) портативность Project (CONCEPT
  §4.1) — сейчас Project живёт только в SQL, без YAML-манифеста.
  Запаркован как T096 в ретро `[0.2.0]`.
- **Решение:** **направление D — гибрид в порядке B → C → A**:
  - **B (T097):** `Phase` как embedded value object внутри
    `Project` aggregate. Полноценный VO (`name: PhaseName enum`,
    `status: PhaseStatus enum`, `started_at`, `completed_at`,
    методы `start() / complete() / skip()` с инвариантами).
    Project содержит collection of 6 фаз (schematic, simulation,
    pcb, magnetics, enclosure, documentation) — все со
    status=`pending` по умолчанию. **`Project.status` становится
    derived computed property** от phases (mapping в спеке
    T096 → Resolved #6); stored поле снимается. Update use case
    `efactory project update --name X --phase Y --status Z` плюс
    `add-phase` / `skip-phase` (из CONCEPT §4.1).
  - **C (T098):** `project.yaml` (`Manifest`) становится
    **primary storage** Project'а; SQL переводится в роль **индекса
    / cache** для быстрого `list` / `search`. Полная реиндексация
    SQL возможна перечитыванием всех manifest'ов
    (`efactory project reindex`). Новый outbound port
    `ProjectManifestRepository` + adapter
    `FilesystemProjectManifestRepository` (YAML). Read pattern:
    `show` — из manifest (truth); `list` — из SQL (быстро).
    Write pattern: `create / update / delete` — manifest first,
    SQL reindexed после.
  - **A (T099):** `Decision` как новый aggregate root (CONCEPT
    §4.4). Domain.Decision с полями {`id: D###`, `title`,
    `date`, `status: proposed | accepted | rejected`,
    `summary`, `rationale`, `evidence`, `session`}. Dual-storage
    (раскрыто в Analyze спеки): markdown в `decisions/D###_*.md`
    (детали) + reference в manifest (summary). CLI: `efactory
    decision add / list / show`.
- **Альтернативы:**
  - **A первым (изолированный Decision aggregate)** — отвергли:
    Decision без Phase / Manifest workflow выглядит как «голый
    CRUD», изолированная фича не на главном пути жизненного
    цикла Project'а. Сначала закрываем основные gaps.
  - **B одним** (Phase + Update, без C/A) — отвергли как
    недостаточный: portable-project (§4.1) — фундаментальный
    принцип, без C проект остаётся прибит к SQL машины.
  - **C первым (Manifest без Phase)** — отвергли: без phases
    manifest содержит мало полезного state'а (только id, name,
    created_at). Phase даёт первый реальный writable-content
    для манифеста.
  - **SQL = primary, manifest = export** — отвергли в пользу
    «manifest = primary, SQL = индекс». Concept §4.1 явно
    позиционирует папку проекта как самодостаточный
    портативный контейнер; SQL — локальный кэш окружения.
    Если SQL = primary, то отправка папки на другую машину
    теряет историю / decisions / status.
  - **Phase как scalar enum + status вместо полноценного VO** —
    отвергли: `started_at` / `completed_at` уже в CONCEPT §4.3,
    методы `start() / complete() / skip()` с инвариантами
    делают domain богаче без перерасхода кода (~30 строк).
  - **PhaseName как whitelist в Settings вместо enum** —
    отвергли: фазы стабильные (6 штук в концепте), не
    open-ended; enum даёт автокомплит и проверку типов
    бесплатно.
- **Последствия:**
  - Domain заметно растёт: +VO `Phase`, +aggregate `Decision`,
    +1 outbound port (manifest), +1 outbound adapter
    (filesystem-yaml), +Update use case на `Project`, +команды
    `update / add-phase / skip-phase / reindex / decision *`.
  - SQL миграция: колонка `status` удаляется (либо сохраняется
    как denormalized cache — уточняется в T098).
  - Backward compatibility: T098 acceptance включает миграцию
    «существующие SQL-only проекты получают manifest».
  - Тестовое покрытие растёт линейно с domain'ом
    (`Phase.start() / complete() / skip()` — изолированные
    domain-тесты; manifest adapter — integration с реальным
    `tmp_path`; Decision aggregate — отдельный набор).
  - Положительная нагрузка на архитектуру: проверим, как
    hexagonal-фундамент держит (а) рост одного агрегата
    (Project с phases), (б) второй адаптер на тот же агрегат
    (manifest рядом с SQL), (в) второй aggregate root
    (Decision). Если что-то скрипит — это сигнал ревизии
    фундамента (отдельный ADR).
  - Decomposition в `BACKLOG.md`: T097 (Phase + derived
    status + Update), T098 (Manifest primary), T099 (Decision).
    Реализуются последовательно. Spec'и крупных задач —
    отдельные `specs/T0XX-*/spec.md` при взятии в работу.

### 2026-05-17 — Auto-install pre-push hook через hatchling custom build hook

- **Контекст:** T091 ввёл `.pre-commit-config.yaml` на 5-step gate,
  но установка hook'а — ручной шаг (`uv run pre-commit install
  --hook-type pre-push`) после клонирования. Если новый разработчик
  забудет — `git push` пройдёт без локального гейта, кривой код
  попадёт на платформу. В ретро `[0.2.0]` запаркован тех-долг T095:
  hook должен ставиться автоматически по `uv sync`, без отдельной
  команды.
- **Решение:** custom build hook hatchling (`hatch_build.py` в корне,
  регистрация `[tool.hatch.build.hooks.custom]` в `pyproject.toml`).
  В методе `initialize()` (срабатывает при сборке editable wheel
  по `uv sync`) делегируем на `uv run --no-sync pre-commit install
  --hook-type pre-push`. Guard'ы: skip при отсутствии `.git/`, skip
  при отсутствии `uv` на PATH (warning в stderr, exit 0 — не
  ломаем build). Идемпотентность достигается естественно: без
  `--reinstall` editable wheel кешируется, hook не вызывается.
- **Альтернативы:**
  - **Скрипт-обёртка `scripts/dev-setup.sh`** (вместо `uv sync`) —
    отвергли: формально не отвечает acceptance «после `uv sync`
    автоматически», требует от разработчика помнить отдельную
    команду — ровно та же проблема, что у `pre-commit install`.
  - **Auto-инициализация в entry-point CLI / `conftest.py`** —
    отвергли: hook ставится только когда пользователь запустит
    приложение/тесты; если сразу делает `git push` — поздно.
    Плюс смешивание слоёв (CLI знает про dev-workflow).
  - **Собственный shell-wrapper в `.git/hooks/pre-push`** без
    pre-commit's `install` — отвергли: дублируем то, что
    pre-commit делает сам, повторно решая
    `INSTALL_PYTHON`/`uv run` логику. Хуже maintainability.
  - **Глобальные git templates** (`git config --global
    init.templateDir`) — отвергли: требует global git config,
    лежит вне репозитория, не воспроизводится между машинами.
- **Последствия:** новый разработчик после `git clone` && `uv sync`
  сразу получает работающий гейт на `git push`. CI без `.git/`
  (artifact checkouts) — silently skip. Smoke-тесты подтвердили:
  hook активируется в editable mode (`version='editable'`,
  `target='wheel'`), `.venv/bin/pre-commit` доступен к моменту
  `initialize()`, `uv run --no-sync` направляет на проектный
  `.venv/`. Цена — введён первый `subprocess.run` в проекте, что
  спровоцировало добавление **`S603`** (subprocess untrusted input)
  в общий `[tool.ruff.lint.ignore]` шаблона: argv-list без
  `shell=True` и без user-input — безопасная форма, false-positive.
  Решение принято по варианту (в) обсуждения T095 — обоснование
  в самой ignore-секции `pyproject.toml`.

### 2026-05-17 — Hexagonal Architecture (Ports & Adapters) как базовый layout

- **Контекст:** долгоживущий проект (~5200 строк собственного кода
  + ещё столько же по периметру) с большим количеством внешних
  адаптеров: 5 MCP-серверов, ИИ-провайдеры (Claude, OpenAI-compat,
  Ollama), CAD-форматы (KiCad/Gerber/STEP), симуляторы (ngspice,
  FEMM), persistence (SQLite, Kùzu). Без явных границ слоёв через
  пару лет получим "big ball of mud".
- **Решение:** Hexagonal Architecture (Alistair Cockburn, Ports
  & Adapters) с пятью верхнеуровневыми слоями в `src/`:
  `domain/` (модели предметной области + поведение),
  `application/` (тонкие use cases),
  `ports/` (`inbound/` + `outbound/`, оба — `typing.Protocol`),
  `adapters/` (`inbound/` + `outbound/`, конкретные реализации),
  `composition/` (composition root: сборка графа зависимостей).
  Изоляция слоёв проверяется автоматически через `import-linter`.
- **Альтернативы:**
  - **Плоский `src/` без слоёв** — отвергли: на масштабе проекта
    превращается в "big ball of mud" в первые же месяцы.
  - **Classic Clean Architecture (Uncle Bob) с явными
    Interactor / Boundary** — отвергли: для Python избыточно,
    лишний boilerplate (отдельные input/output boundary классы),
    то же самое достигается тонким use case + Protocol.
  - **Onion Architecture** — близкий родственник; отвергли
    в пользу Hexagonal как более аскетичной и явно
    симметричной (inbound/outbound как зеркало).
  - **Layered (controllers / services / repositories)** —
    отвергли: не запрещает зависимости сверху вниз через слои,
    легко скатывается к "fat service".
- **Последствия:** новые интеграции добавляются как outbound-адаптеры
  за стабильными port-интерфейсами; замена технологии затрагивает
  только адаптер; domain тестируется без поднятия БД и сети. Цена —
  необходимость держать дисциплину границ (помогает `import-linter`)
  и явный маппинг domain ↔ persistence (без "SQLAlchemy-модель как
  domain"). Подробности — `specs/T085-architecture-foundation/spec.md`.

### 2026-05-17 — TDD-first как методология разработки во всём проекте

- **Контекст:** проект долгоживущий, hexagonal-архитектура с
  множеством слоёв и адаптеров, цель ~5200 строк production-кода
  плюс окружение. Без дисциплины тестирования слоёв легко получить
  баги стыков, которые ловятся только в e2e и плохо
  локализуются.
- **Решение:** **TDD строго (Red → Green → Refactor)**: никакая
  строка production-кода не пишется до падающего теста. Подход —
  **outside-in** для hexagonal: acceptance/e2e-тест → unit-тесты
  application use case с fake-портами → integration-тесты адаптеров.
  Domain тестируется как чистые unit-ы без mock-ов (нет внешних
  зависимостей). Адаптеры — integration с реальными технологиями
  (SQLite в `tmp_path`, Kùzu в `tmp_path`, FS в `tmp_path`).
  Fake-порты — простые in-memory классы, реализующие `Protocol`;
  **без `unittest.mock`**. Bug fix следует тому же шаблону:
  сначала тест, воспроизводящий баг, потом фикс.
- **Альтернативы:**
  - **Test-after** (написал реализацию → покрыл тестами) —
    отвергли: пропускает мёртвые ветки, тесты адаптируются под
    реализацию, а не наоборот; на сложной hexagonal-архитектуре
    регулярно приводит к плохо тестируемым use case.
  - **BDD-first** (`pytest-bdd`, Gherkin) — отвергли как
    обязательный: добавляет slow-test layer и Gherkin-наследие,
    не покрывающее unit-уровень. Может быть введён локально как
    acceptance-DSL, если возникнет потребность.
  - **Mockist (London School) с mock-ами вместо fake-ов** —
    отвергли: `unittest.mock` хрупкие к рефакторингу
    (matchers по строке имени, side_effect-аду); Protocol-fake
    дешевле и устойчивее.
- **Последствия:** дисциплинированное покрытие, низкая
  регрессионная цена, контракт каждого слоя задаётся тестом
  заранее. Coverage на `src/` ≥ 80% (общий threshold проекта),
  на `domain/` ≈ 100%, на `application/` ≥ 90% — естественно
  через TDD. Цена — медленнее на ранней стадии (тест-первый
  цикл), окупается на горизонте проекта. Зафиксировано также
  в auto-memory `feedback_tdd.md` и в mem0.

### 2026-05-17 — Async-first во всём проекте

- **Контекст:** основные операции системы — I/O-bound: вызовы ИИ-
  провайдеров (Claude, OpenAI-compat), MCP-протокол (stdio/HTTP),
  взаимодействие с внешними процессами (KiCad, FreeCAD, ngspice,
  FEMM), сетевые sourcing-API (Mouser, DigiKey, LCSC), файловые
  операции с большими CAD-проектами. Параллелизм через async —
  естественная модель.
- **Решение:** **async везде**. Порты, адаптеры, use cases —
  все методы `async def` по умолчанию. Sync-API внешних библиотек
  (Kùzu Python binding на 2026-05-17 — синхронный) заворачиваются
  в `asyncio.to_thread` внутри адаптера, наружу торчит async
  Protocol. Composition root — async `main()` через
  `asyncio.run(...)`.
- **Альтернативы:**
  - **Sync-first, async только для конкретных операций** —
    отвергли: смешанный режим тянет sync/async-аду, требует
    `nest_asyncio` или ручной event-loop оркестрации; на
    hexagonal-границах превращается в кошмар.
  - **Threading / multiprocessing вместо asyncio** — отвергли
    для I/O-bound нагрузки: asyncio даёт более чистую модель
    отмены и таймаутов, меньше синхронизационных примитивов.
- **Последствия:** единый стиль во всём коде, естественная
  параллельность ИИ-запросов и MCP-вызовов, простой `gather`
  для конкурентных операций. Цена — async-«вирус» (всё, что
  вызывает async, само должно быть async); митигация — он
  введён с первого дня, без legacy sync-кода для миграции.

### 2026-05-17 — Pydantic v2 для domain-моделей, отдельные persistence-модели

- **Контекст:** domain-модели нужно валидировать на входе
  (JSON, MCP-tool-input, CLI-аргументы), сериализовать на выходе
  и хранить в БД. Соблазн использовать SQLAlchemy declarative
  как domain (меньше кода) велик, но размывает границы hexagonal
  и привязывает domain к particular ORM.
- **Решение:**
  - **Domain-модели — Pydantic v2** с поведением (методы, бизнес-
    инварианты в `model_validator`-ах), value objects —
    `model_config = ConfigDict(frozen=True)`. Domain зависит
    **только** от `pydantic` и stdlib; никаких импортов из
    `sqlalchemy`, `kuzu`, `mcp`, `anthropic`, `typer` в domain
    не допускается (проверяется `import-linter`).
  - **Persistence-модели — отдельные** SQLAlchemy 2.0 declarative
    классы в `adapters/outbound/persistence_sql/models.py`.
    Маппинг domain ↔ ORM — явными функциями `to_orm(domain) →
    orm` / `to_domain(orm) → domain` в том же адаптере.
  - **DTO** — отдельные Pydantic-модели в адаптерах, **только
    когда форма расходится** с domain (HTTP-API, MCP-tool со
    сложным JSON-input). Преждевременные mapper-ы не пишем.
- **Альтернативы:**
  - **SQLAlchemy declarative как domain** — отвергли: domain
    привязан к ORM, ленивая загрузка ломает инварианты при
    `refresh()`, нельзя тестировать domain без поднятия engine.
  - **Чистые `@dataclass` для domain без Pydantic** — отвергли:
    теряем валидацию из коробки и сериализацию; пришлось бы
    дописывать ручные `__post_init__`-валидаторы или подключать
    `marshmallow`/`attrs+cattrs`.
  - **Pydantic с автогенерируемыми SQLAlchemy-моделями
    (SQLModel)** — отвергли: SQLModel слепляет domain и
    persistence в один класс, ровно то, чего избегаем.
- **Последствия:** domain тестируется без поднятия БД; смена
  ORM или БД — точечное изменение в `adapters/outbound/
  persistence_sql/`; явность маппинга подсвечивает изменения
  схемы. Цена — больше кода (две модели + маппер); митигация —
  модели обычно близки по форме, маппер тривиальный.

### 2026-05-17 — Ручная DI-композиция в `composition/`, без контейнера

- **Контекст:** hexagonal-архитектура требует сборки графа
  зависимостей (use cases получают порты через конструктор).
  Существуют DI-контейнеры (`dependency-injector`, `punq`,
  `wired`), упрощающие декларативную сборку на больших графах,
  но привносящие магию и обучение.
- **Решение:** **ручная композиция** в `composition/`. Объекты
  адаптеров создаются явно в `main()` / фабричных функциях,
  передаются в конструкторы use case-ов. Граф зависимостей читается
  как обычный Python-код. Без декораторов, без autowiring.
- **Альтернативы:**
  - **`dependency-injector`** — мощный, но магия `Provide[Container.x]`
    и Resource lifecycles требует обучения; на старте проект слишком
    маленький.
  - **`punq` / `wired`** — легче, но всё ещё доп. зависимость и
    обучение ради экономии 20-30 строк ручной сборки.
- **Последствия:** граф зависимостей прозрачен и видим без
  магии; легко переопределить любой адаптер в тестах. Цена —
  если граф разрастётся до 50+ объектов, ручная сборка станет
  громоздкой; **тогда** пересматриваем (новый ADR), вводим
  контейнер.

### 2026-05-17 — SQLAlchemy 2.0 async + aiosqlite + Alembic для метаданных

- **Контекст:** требуется persistence метаданных проектов
  (Project, Component, Run, ...): реляционные связи, миграции
  схемы, надёжная транзакционность. Desktop-приложение, один
  пользователь, embedded.
- **Решение:** **SQLAlchemy 2.0+** (typed declarative с `Mapped[]`,
  `mapped_column`) + **aiosqlite** (async-драйвер SQLite) +
  **Alembic** для миграций (шаблон `alembic init -t async`).
  Persistence-модели живут в `adapters/outbound/persistence_sql/
  models.py`, отдельно от domain Pydantic-моделей. Адаптер
  реализует `MetadataRepository` Protocol из `ports/outbound/`.
- **Альтернативы:**
  - **Raw `sqlite3` или `aiosqlite` без ORM** — отвергли:
    нет миграций из коробки, ручной SQL для нетривиальных
    запросов, типизация хромает.
  - **SQLModel** — отвергли: слепляет domain и persistence
    (см. ADR «Pydantic v2 для domain»).
  - **Peewee, Tortoise ORM** — отвергли: меньше экосистема,
    хуже type-checker support, нет аналога Alembic такого же
    зрелого.
  - **TinyDB / `shelve`** — отвергли: нет реляционных связей,
    нет миграций, не масштабируется на даже умеренный граф
    сущностей.
- **Последствия:** мощный typed ORM, контролируемые миграции,
  переносимость на PostgreSQL без правок domain (только
  адаптер). Цена — кривая обучения SQLAlchemy 2.0 typed-API
  (новый стиль отличается от 1.x); митигация — стандарт с
  2023 года, документация зрелая.

### 2026-05-17 — Kùzu как embedded граф-БД для топологий

- **Контекст:** топология схем и плат — естественный граф:
  узлы (компоненты, выводы, нетлисты), рёбра (соединения,
  цепи). Типичные запросы — обходы и пути ("все компоненты в
  цепи сигнала X", "найди петли", "связные подграфы"). На
  SQLite-CTE такие запросы выражаются плохо.
- **Решение:** **Kùzu** (MIT, embedded, Cypher-совместимый,
  колоночное хранение). Адаптер живёт в
  `adapters/outbound/graph_store/`, реализует
  `TopologyGraphStore` Protocol. Sync Python binding
  заворачивается в `asyncio.to_thread` в адаптере.
- **Альтернативы:**
  - **Neo4j** — server-based, требует JVM, GPLv3 для core
    компонентов, лицензия для коммерции мутная; отвергли для
    desktop-приложения как тяжёлое решение.
  - **Memgraph** — server-based, BSL-лицензия с коммерческими
    ограничениями; отвергли по тем же причинам.
  - **ArangoDB** — server-based multi-model; отвергли как
    тяжёлое.
  - **SQLite + recursive CTE + edge-таблицы** — отвергли как
    основное: для алгоритмов на графах больно, специализированных
    оптимизаций нет. Оставляется как fallback при провале
    Critical-проверки фазы 1.
  - **NetworkX в памяти + persist в SQLite** — fallback-вариант
    при провале Kùzu под Python 3.14.
- **Последствия:** нативные графовые запросы Cypher, embedded
  deployment (как SQLite), MIT-лицензия. Цена — молодая БД (с
  2022), экосистема меньше Neo4j. **Статус:** Critical-проверка
  фазы 1 пройдена — `kuzu==0.11.3` ставится и работает под Python
  3.14 (Linux), sync API корректно оборачивается в
  `asyncio.to_thread`, подтверждено integration-smoke-тестом
  `tests/integration/adapters/graph_store/test_kuzu_smoke.py`.
  Fallback к NetworkX-persisted-в-SQLite больше не активен.

### 2026-05-17 — `pydantic-settings` для конфигурации с первого дня

- **Контекст:** проекту с первого дня нужны конфигурируемые
  пути (SQLite-файл, Kùzu-папка, корень проектов), API-ключи
  (Anthropic и пр.), профили окружения. Хардкод в composition
  root — техдолг с момента создания.
- **Решение:** **`pydantic-settings`** с одним классом `Settings`
  в `composition/settings.py`. Источники: переменные окружения,
  `.secrets` файл в корне (уже в `.gitignore`), значения по
  умолчанию для разработки. Класс валидирует типы и обязательные
  поля при старте.
- **Альтернативы:**
  - **`os.environ` напрямую** — отвергли: нет типизации,
    нет валидации обязательности на старте, легко получить
    `None` в неожиданном месте.
  - **`dynaconf`, `confuse`** — отвергли: дополнительная
    зависимость без выигрыша по сравнению с pydantic-settings,
    который уже family для Pydantic.
  - **`python-decouple`** — отвергли: меньше функциональности,
    нет интеграции с Pydantic.
- **Последствия:** конфиг типизирован, ошибки конфигурации
  ловятся на старте, secret-keys из env. Цена — одна доп.
  зависимость (`pydantic-settings`).

### 2026-05-17 — `import-linter` для автоматической изоляции слоёв

- **Контекст:** правила hexagonal ("domain не импортирует
  application", "ports не импортируют adapters" и т.д.) в spec/
  README легко нарушаются по невнимательности или из-за IDE-
  autocomplete. Без машинной проверки правила деградируют
  через 3-6 месяцев.
- **Решение:** **`import-linter`** (dev-dependency), конфиг
  в `[tool.importlinter]` в `pyproject.toml`. Контракты:
  - **Layers contract** для `src/`: `composition` → `adapters` /
    `application` → `ports` / `domain`, со строгим запретом
    обратных импортов.
  - **Forbidden contract** для domain: запрет импортов
    `sqlalchemy`, `kuzu`, `mcp`, `anthropic`, `typer` из
    `src/domain/`.
  - **Forbidden contract** для adapters: запрет перекрёстных
    импортов между разными adapters/outbound/* и adapters/
    inbound/*.
  Команда `uv run lint-imports` — **пятая обязательная** проверка
  перед `git push` (после ruff / format / mypy / pytest).
- **Альтернативы:**
  - **Ручные тесты на `ast.parse`** — отвергли: дублирует
    решённую задачу, поддерживать сложнее.
  - **Не автоматизировать, держать в правилах** — отвергли:
    правила деградируют без машинной проверки на долгом
    горизонте.
- **Последствия:** нарушения границ слоёв ловятся локально
  до коммита, дисциплина hexagonal удерживается без human
  policing. Цена — одна dev-dependency и поддержание
  контрактов в `pyproject.toml` при добавлении новых слоёв
  /правил.

### 2026-05-15 — Архитектурный принцип: MCP-обвязка готовых инструментов, минимум собственного кода

- **Контекст:** в нише сквозного проектирования РЭА существует
  набор зрелых open-source инструментов (KiCad, ngspice, FreeCAD,
  FEMM, OpenMagnetics) и для большинства из них уже есть готовые
  MCP-серверы либо Python-API. Альтернатива — писать собственный
  монолит на ~50 000+ строк.
- **Решение:** система строится как **тонкий оркестрационный слой**
  (`kicad-sim-bridge` — собственный MCP-сервер) плюс универсальный
  чат-клиент (`kicad-sim-chat`), подключающий **5 MCP-серверов**:
  `mcp-kicad-sch-api`, `kicad-mcp-pro`, `spicebridge`, `freecad-mcp`,
  `kicad-sim-bridge`. Чат-клиент — единственный MCP-клиент в системе;
  LLM-бэкенды (включая Claude Code Max) используются только как
  языковые модели, не исполняют tool calls. Собственный код — только
  то, чего нет ни у одного из готовых серверов: pipeline между
  инструментами, предметно-ориентированные проверки, формирование
  документации. Целевой объём — ~5200 строк (§18 концепта).
- **Альтернативы:**
  - **Собственный монолит** — отвергли: повторное изобретение
    KiCad/ngspice/FreeCAD-обвязки, ~50 000+ строк, неподъёмный
    maintenance burden, потеря совместимости с обновлениями
    upstream-инструментов.
  - **LLM как MCP-клиент (через Claude Desktop или Claude Code в
    качестве хозяина инструментов)** — отвергли: разные бэкенды дают
    разное поведение, проектные функции (DDR, sessions, project.yaml)
    пришлось бы дублировать в каждом, теряем единый лог tool calls
    и привязку к проекту.
- **Последствия:** все бэкенды работают одинаково; проектные функции
  всегда доступны; полный контроль и логирование tool calls; собственный
  код сосредоточен на том, что действительно «своё». Цена —
  необходимость поддерживать оркестрационный слой и совместимость с
  5 внешними MCP-серверами; митигация — `compatibility.toml`.

### 2026-05-15 — kicad-sch-api для создания и модификации схем

- **Контекст:** для программного создания и модификации .kicad_sch
  нужен Python-API. Официальный kicad-python (IPC API) на 2026-05-15
  поддерживает только PCB-редактор, схемы — в планах. Требуется
  работа без запущенного KiCad (headless, CI/CD).
- **Решение:** **kicad-sch-api** (MIT, PyPI) — побайтовое сохранение
  .kicad_sch, поддержка KiCad 7/8/9/10, 70+ тестов, готовые примеры.
  Поверх неё — **mcp-kicad-sch-api** (MIT) с 15 MCP-инструментами.
- **Альтернативы:**
  - **Официальный kicad-python (IPC API)** — отвергли как
    основной: на 2026-05-15 не поддерживает схемы, требует запущенный
    KiCad. Перспективно — пересмотрим, когда поддержка схем появится
    (см. фаза 8 концепта).
  - **Ручная генерация S-expression-ов** — отвергли: хрупко, дублирует
    то, что kicad-sch-api уже делает.
- **Последствия:** headless-генерация и модификация схем,
  совместимость с несколькими версиями KiCad. Цена — community-проект
  (circuit-synth), не official.

### 2026-05-15 — kicad-mcp-pro как комплексный MCP-сервер для KiCad

- **Контекст:** для KiCad нужен MCP-сервер, покрывающий весь
  жизненный цикл: проекты, схемы, PCB, валидация (ERC/DRC/DFM),
  экспорт (Gerber, BOM, STEP, pick-and-place), интеграция с
  FreeRouting, SI/PI/EMC хелперы, gated release производственных
  файлов.
- **Решение:** **kicad-mcp-pro (oaslananka)** (MIT, PyPI) — единый
  сервер с серверными профилями (`minimal`, `pcb_only`, `manufacturing`,
  `agent_full` и др.), VS Code companion `kicad-studio`, CLI-диагностикой
  `health`/`doctor`.
- **Альтернативы:**
  - **Seeed Studio kicad-mcp-server** — отвергли: уже покрыт
    функциональностью kicad-mcp-pro, не имеет quality gates, DFM,
    SI/PI/EMC и gated release.
  - **mixelpixx KiCAD-MCP-Server** — отвергли по той же причине.
  - **Собственный MCP-сервер с нуля поверх kicad-cli и pcbnew API** —
    отвергли: противоречит первому принципу, ~1500-2000 строк
    дублирующего кода.
- **Последствия:** один MCP-сервер вместо набора нишевых; gated
  release не пускает в производство недопроверенные файлы. Цена —
  привязка к темпу релизов oaslananka; митигация — `compatibility.toml`.

### 2026-05-15 — SPICEBridge как основной MCP-сервер моделирования

- **Контекст:** требуется SPICE-моделирование (OP, tran, AC, sweep)
  по командам LLM с прямым взаимодействием через MCP, базовыми
  измерениями (THD, gain, bandwidth) и интеграцией с нашим
  чат-клиентом и Claude Code.
- **Решение:** **SPICEBridge** (MIT) — 18 MCP-инструментов поверх
  ngspice, авторасчёт номиналов по ряду E24, stdio + HTTP/Cloudflare
  транспорты. **PySpice** (PyPI) используется для прямого
  программного доступа к ngspice внутри нашего bridge (KiCadTools для
  чтения .kicad_sch, объектный API нетлистов).
- **Альтернативы:**
  - **Только PySpice без MCP** — отвергли: пришлось бы писать
    собственный MCP-сервер с нуля (~500-1000 строк), дублируя то,
    что SPICEBridge уже даёт «из коробки».
  - **LTSpice / TINA** — отвергли: коммерческие или с ограничениями
    лицензии, нет CLI/MCP-обвязки, не работают headless на Linux,
    противоречат первому принципу.
- **Последствия:** SPICEBridge и PySpice — комплементарны
  (MCP-сервер плюс библиотека), а не конкуренты. Цена — две точки
  обновления и совместимости (но обе MIT, PyPI).

### 2026-05-15 — PyOpenMagnetics + FEMM для намоточных изделий

> **Частично заменено решением от 2026-05-19** (см. «Magnetic
> field verification: Linux-native FEM-solver...» выше). FEMM
> заменяется Linux-native solver'ом (Elmer / GetDP, выбор по
> итогам T113); PyOpenMagnetics + MAS-формат остаются как ядро
> магнитного дизайна.


- **Контекст:** проектирование заказных трансформаторов, дросселей,
  катушек индуктивности — от подбора сердечника до спецификации для
  намотчика. Нужна база сердечников/материалов, расчёт обмоток с
  AC-эффектами, верификация магнитного поля и интеграция с SPICE и
  FreeCAD.
- **Решение:**
  - **PyOpenMagnetics** (MIT, PyPI) — Python-обёртка над MKF: база
    10 000+ сердечников, расчёт потерь, AGENTS.md для LLM.
  - **MAS** (JSON-формат) — стандартизированное описание магнитного
    компонента, совместимое с ngspice/LTSpice/FEMM/Ansys Maxwell.
  - **MVB** — генератор 3D-моделей для FreeCAD из MAS.
  - **FEMM + pyFEMM** — 2D FEA для верификации поля.
- **Альтернативы:**
  - **Только ручной расчёт по McLyman / Erickson** — отвергли:
    отсутствие базы сердечников, нет AC-учёта, не масштабируется на
    автоматический пайплайн.
  - **transformer_designer (Denys)** — рассматривался, отвергнут как
    основной инструмент: веб-приложение без программного API для
    интеграции в MCP-пайплайн. Оставлен как опциональный справочный
    веб-интерфейс для ручной верификации.
  - **Ansys Maxwell, COMSOL** — отвергли: коммерческие, противоречат
    первому принципу.
- **Последствия:** покрыт полный цикл от ТЗ до намотчика.
  Безальтернативно в open-source-нише — PyOpenMagnetics на момент
  2026-05-15 единственный зрелый Python-движок с базой сердечников
  и AI-ready форматом.

### 2026-05-15 — FreeCAD + freecad-mcp для проектирования корпусов

- **Контекст:** требуется параметрическое 3D-моделирование корпусов
  с поддержкой листового металла (шасси ламповых конструкций), сборки
  с PCB (импорт STEP из KiCad), генерации 2D-чертежей и развёрток DXF.
  Управление — программное, через MCP.
- **Решение:** **FreeCAD 1.0+** (LGPL, open source) с workbenches
  Part Design / Sheet Metal / Assembly / TechDraw / Draft и
  **freecad-mcp (neka-nat)** в роли MCP-сервера (MIT, 617 stars).
  Интеграция с KiCad через STEP-импорт.
- **Альтернативы:**
  - **Коммерческие 3D-САПР (SolidWorks, Fusion 360, Autodesk
    Inventor)** — отвергли: не open source, лицензия противоречит
    первому принципу проекта, нет готовой MCP-обвязки, кроссплатформа
    хромает.
  - **OpenSCAD** — отвергли: программная парадигма (без GUI и
    параметрических операций в редакторе), нет Sheet Metal, нет
    Assembly с ограничениями, нет TechDraw — пришлось бы дописывать
    половину функциональности.
- **Последствия:** полностью open-source-стек, кроссплатформенность,
  готовый MCP-сервер. Цена — FreeCAD 1.0 моложе коммерческих
  конкурентов, отдельные workbench (Sheet Metal) — community addon.

### 2026-05-15 — Стратегия версионирования зависимостей: `compatibility.toml` + `--update`

- **Контекст:** система зависит от 5 MCP-серверов, KiCad, ngspice,
  FreeCAD, FEMM, Python — все обновляются независимо. Нужен
  воспроизводимый bootstrap и контролируемый upgrade.
- **Решение:** в корне проекта файл `compatibility.toml` с двумя
  секциями: `[tested]` (точные версии, на которых проект гарантированно
  работает) и `[minimum]` (минимально допустимые). `bootstrap`
  устанавливает `[tested]`; флаг `--update` обновляет до последних
  версий, запускает smoke-тест и при успехе обновляет `[tested]`.
- **Альтернативы:**
  - **Только pin последних версий** — отвергли, любой релиз любой
    зависимости может сломать сборку у нового пользователя без
    возможности отката к проверенной конфигурации.
  - **Только минимальные версии** — отвергли по той же причине плюс
    непредсказуемость поведения при разных «текущих» у разных
    пользователей.
- **Последствия:** новый пользователь получает заведомо рабочую
  систему; апдейт явный и проверяемый. Цена — нужно поддерживать файл
  и smoke-тест. Подробности — §19 концепта.
