## Spec: T100 — programmatic schematic generation (`efactory.schematic` facade)

**Статус:** Analyzed
**Дата создания:** 2026-05-18
**Связанные документы:** `CONCEPT.md`, `DECISIONS.md` (новый ADR будет добавлен), `BACKLOG.md` (запись T100), ретроспектива в `CHANGELOG.md` для T008.

---

## 1. Overview

Сегодня для каждого нового SPICE-сценария (RC-фильтр, SE-amp, выпрямитель) нужно
руками писать `.kicad_sch` в s-expression. На T008 ручной s-expr оказался
хрупким: Y-down vs Y-up, кастомные `lib_symbols`, GND через power-symbol с
substitution на net 0, KiCad SPICE pin order quirks — каждая фикстура
становилась отдельным микропроектом по «обучению» Гвидо. Это блокирует
автоматизацию: T011-T014 (LLM chat-client) **должен вызывать функции
проектирования**, а не генерировать s-expr через text completion.

Цель T100 — внутренний фасад `efactory.schematic` с простым императивным API
(`Schematic`, `Component`, `connect()`, `GND`, `save()`), скрывающий все
координатно-форматные детали `.kicad_sch`. Реализация — поверх существующей
библиотеки или собственной (см. §6 Constraints — будет решено в ADR на основе
pre-spike).

## 2. Сценарии использования

- **C1.** Гвидо (или будущий LLM-агент) собирает RC-фильтр в ≤30 строках
  Python: `R`, `C`, `Vsrc`, `GND`, `connect()`, `save()`. Файл открывается в
  KiCad 10.0 GUI без ошибок, проходит ERC=0, экспортируется в SPICE netlist
  через `kicad-cli` и прогоняется в ngspice (T008-пайплайн).
- **C2.** Тот же путь для типового SE-амплификатора на лампе 6П14П (тубовая
  модель из T006: V+, R анодная, OPT-первичка, лампа `XV1`, катодный
  R+C, источник 250 В на анод) и для двухполупериодного выпрямителя на
  6Ц4П / 5U4G (лампа из T006: VAC, два диода, CLC-фильтр).
- **C3.** Существующие фикстуры из `tests/fixtures/` (rc_filter и далее)
  переписываются через новый API. Это и есть e2e smoke-тест фасада: «то, что
  раньше было ручным s-expr на 200 строк, теперь скрипт на 25-30 строк, и
  поведение в ngspice идентично».

## 3. Functional Requirements

- **ДОЛЖНА** предоставлять API уровня:
  - `Schematic(name)` — создание пустой схемы.
  - `Schematic.add(component_kind, reference, value, ...)` — добавление
    компонента (R, C, L, V_DC, V_AC, V_PULSE, V_SIN, NPN/PNP/NMOS/PMOS,
    Diode, Subcircuit/Tube). Список kinds покрывает minimum
    набор T006/T007.
  - `Schematic.connect(pin_a, pin_b)` — wire между двумя
    pin-handles, либо `connect_to_ground(pin)` для GND.
  - `Schematic.add_tube(reference, model_id)` — поверх T007 `SpiceModel`:
    ставит сабсимвол `XV1` с правильным mapping pin → SPICE-узел,
    переносит `subcategory`/`tube_type`.
  - `Schematic.save(path)` — атомарный write `.kicad_sch`.
- **ДОЛЖНА** скрывать координаты pin'ов: пользователь не указывает мм. Auto-
  layout — простой grid placement (sequential) или manual hints через
  `position=(grid_col, grid_row)` в логических единицах.
- **ДОЛЖНА** генерировать валидный для KiCad 10.0 `.kicad_sch`:
  - ERC = 0 при открытии в `kicad-cli sch erc` или KiCad GUI;
  - SPICE-экспорт через `kicad-cli sch export netlist --format spice`
    проходит без ошибок;
  - ngspice выполняет netlist без `Error in netlist parsing`.
- **ДОЛЖНА** скрывать GND-convention: пользователь пишет
  `connect_to_ground(pin)`, фасад ставит правильный `power:GND` symbol
  + label, чтобы T004-адаптер (`KicadCliSchematicExporter`) с
  `GND → 0` substitution получил рабочий netlist.
- **МОЖЕТ** поддерживать многоюнитные символы (например, операционник
  TL072 — два OPA в одном корпусе) — but Phase 2 (после MVP).
- **МОЖЕТ** генерировать `lib_symbols` секцию инлайн (как делает KiCad eeschema),
  либо оставлять её пустой и полагаться на глобальную symbol library
  (KiCad сам подгружает на load). Стратегия — решение ADR.
- **НЕ ДОЛЖНА** поддерживать PCB (`.kicad_pcb`) — это Phase 4 (T037+).
- **НЕ ДОЛЖНА** реализовывать full schematic editor — нет undo/redo, нет
  selection-based ops, нет визуализации. Это write-only build → save.

## 4. Success Criteria

- C1/C2 примеры собраны и сохранены; KiCad GUI открывает их без ошибок;
  ERC = 0; SPICE-экспорт → ngspice OP/TRAN/AC соответствует ожидаемым
  значениям (для RC f_c=159 Hz ±5%, для SE-amp gain≈усиление лампы по
  даташиту в пределах ±15%).
- Все ручные фикстуры `tests/fixtures/*.kicad_sch` из T004/T008 переписаны через
  новый API; старые файлы удалены (или оставлены как «golden» reference на
  byte-level diff, см. ADR).
- Coverage ≥ 80% на `src/<facade module>/`; 4 gate'а (ruff/format/mypy/pytest)
  зелёные.
- `DECISIONS.md` содержит ADR T100, где зафиксирован выбор подхода (см. §6),
  отвергнутые альтернативы, риски и план миграции при breaking changes в
  KiCad 11.

## 5. Key Entities

- **`Schematic`** — root объект: имя проекта, список компонентов, список
  net'ов (имплицитно — через wire connections), serializer в s-expr.
- **`Component`** — базовый класс: `reference`, `value`, `lib_id`,
  `position` (логические grid units), `pin_map` (от логического имени к
  физическому KiCad pin number — изолирует «pin 2 vs pin 1» quirk'и).
  Подтипы: `Resistor`, `Capacitor`, `Inductor`, `VoltageSource{DC,AC,SIN,PULSE}`,
  `BJT`, `MOSFET`, `Diode`, `TubeSubcircuit` (через T007).
- **`Pin`** — handle от компонента; `(component, pin_name)` tuple. Возвращается
  из `component.pin_a` / `.pin_k` / `.anode` / `.cathode` / `.plate` etc.
- **`Net`** — implicit (формируется при `connect()` транзитивно); явное
  использование только в `ground_net = Net("GND", power=True)`.

## 6. Assumptions & Constraints

- Целевая версия KiCad — **10.0.2** (она же у Разработчика, и future-proof
  на горизонте текущей дорожной карты до Phase 8). Поддержка KiCad ≤ 9 — не
  цель.
- Python 3.14+ (соответствует efactory).
- Никаких внешних MCP-серверов в pipeline (фасад — pure Python lib,
  тестируется без сети, без сторонних процессов кроме `kicad-cli`).
- **Pre-spike результаты (2026-05-18, проверено живым тестом)**:
  - `kicad-sch-api 0.5.6` (PyPI, MIT, 29 релизов за 3 месяца, requires
    Python ≥3.10 без верхней границы) **устанавливается под Python 3.14**
    с `UV_LINK_MODE=copy`.
  - Зависимости — **78 пакетов** (втягивает `mcp`, `fastmcp`, `uvicorn`,
    `starlette`, `sse-starlette`, `pydantic`, `jinja2`) — толсто; MCP-сервер
    нам не нужен, это «лишний бэкенд» в pyproject. Force-избавиться можно
    только форком.
  - `load_schematic()` **читает** наш KiCad 10 файл
    `tests/fixtures/rc_filter.kicad_sch` корректно (5 компонентов: 2×
    `power:GND`, `Simulation_SPICE:VDC`, `Device:R`, `Device:C`). Файл-формат
    KiCad 10 (`version 20240128`, generator `eeschema`) совместим с
    парсером 0.5.6 на чтение.
  - Round-trip `load → save` не даёт byte-identical файл (заявление "exact
    format preservation" в README — натяжка; на минимальном файле есть
    расхождения). Для нас не критично, если KiCad GUI открывает результат.
  - **Критическое ограничение:** `Schematic.components.add(lib_id="Device:R",
    ...)` **падает** с `LibraryError: Symbol 'Device:R' not found`. Причина —
    в KiCad 10 файлы библиотек **переехали в `*.kicad_symdir/` директории с
    бинарными per-symbol `.kicad_sym` файлами**, а парсер 0.5.6 ожидает
    legacy текстовый формат «один `Device.kicad_sym` со всеми символами»
    (как KiCad ≤8). Никакой workaround через `cache.add_library_path`/
    `discover_libraries` не помог: cache видит файл, но парс возвращает
    пустоту. Сообщение: `Invalid library path from KICAD_SYMBOL_DIR: ... (does
    not exist or contains no .kicad_sym files)`.
  - Альтернатива **SKiDL** (devbisme) генерирует netlist для PCB, а не
    `.kicad_sch` — нам не подходит (теряется визуальная схема, KiCad GUI не
    нужен).
  - **Upstream `kicad-python` IPC API** для `.kicad_sch` пока не существует
    (это T079, фаза 8 backlog).
- **Открытые архитектурные варианты** (выбор фиксируется в ADR T100 после
  Clarify):
  - **(A) Форк `kicad-sch-api`** с поддержкой `*.kicad_symdir/` (binary
    per-symbol) формата KiCad 10. MIT license это разрешает. Минусы:
    параллельный maintenance, толстая dependency-цепочка (78 пакетов с
    MCP-балластом).
  - **(B) Bundled fallback library**: положить рядом с фасадом «freeze»-копию
    легаси KiCad 8 / 9 текстовых `.kicad_sym` библиотек (только Device,
    Simulation_SPICE, power — ~5-10 файлов) и feed-ить их в `kicad-sch-api`
    cache. Сами файлы при сохранении ссылаются `Device:R` — KiCad 10 GUI
    подтянет уже из своей библиотеки. Минусы: библиотеки KiCad 8 != KiCad 10
    (UUID, properties) — на load в KiCad 10 могут проскакивать warnings.
  - **(C) Bypass cache** — пропатчить `kicad-sch-api` через monkey-patch /
    наш subclass `Components`, чтобы `add()` не валидировал существование
    символа в cache. Минимально инвазивно, но хрупко на upgrade.
  - **(D) Собственный фасад поверх `sexpdata`** — мы пишем `.kicad_sch`
    напрямую через s-expr serializer, без `kicad-sch-api`. Полный контроль,
    нулевой dependency-балласт, KiCad 10 формат сразу. Минусы: ~неделя
    работы на корректный wire routing + lib_symbols inline-блок + UUID
    generation; повторяет всё, что мы только что обожглись делать вручную.
  - **(E) Подождать upstream `kicad-python` IPC**: не вариант для MVP-ядра,
    это явно Phase 8 (T079).

## 7. Out of Scope

- PCB layout (`.kicad_pcb`) — это Phase 4.
- Полноценный editor (визуализация в TUI, undo/redo, ERC inside facade) —
  ERC делает `kicad-cli`, не мы.
- Auto-routing wire'ов между произвольными точками. Допустим только
  ортогональные wires «pin → pin» + явные Y-line / X-line через
  промежуточную junction.
- Поддержка KiCad ≤ 9 (формат файла, библиотеки).
- Многолистные иерархические схемы — Phase 2 (после MVP).
- Симуляция самого фасада в headless KiCad (без `kicad-cli`).

---

## Clarify (заполняется Гвидо)

### Open questions для Владимира

— все resolved (см. ниже).

### Open questions (исходный список, для истории)

- **Q1 (главный, архитектурный — нужен ответ до начала Implement).** Какой
  вариант из §6 (A/B/C/D) тебе ближе на старте? Моя интуиция — **D**
  (собственный фасад), потому что:
  - Один раз больно, потом наша зона контроля.
  - 78 транзитивных deps от `kicad-sch-api` (mcp/fastmcp/uvicorn) — лишний
    шум в supply chain efactory; CI станет толще; security surface шире.
  - Phase 2-8 концепта добавят свои требования (многолистные схемы, PCB
    нетлисты-кросс-референсы, символы кастомных tube-моделей с разными pin
    layouts) — фасад под нас будет управляемее, чем форк чужой библиотеки.
  - Pre-spike показал: эффективно используется только `load_schematic`
    (1 функция из 78-deps цепочки). Это не «стоим на плечах гиганта», это
    «таскаем гиганта за компанию».
  Но это означает спрятать в efactory **больше специфики KiCad 10
  s-expr**, что = больше работы по поддержке при KiCad 11/12. Возможно, ты
  предпочитаешь (A) — общим усилием помочь open-source community
  с patches. Решение — твоё.
- **Q2.** Auto-layout. Минимальная стратегия — sequential grid: каждый
  компонент в следующую клетку 25.4×25.4 мм, wire'ы рисуются по ближайшим
  pin'ам. Для C1 (RC-фильтр на 3 компонента) — ок. Для C2 (SE-amp ~10
  компонентов) — может получиться нечитаемо в GUI. Допустимо ли «нечитаемо в
  GUI, но валидно по ERC и netlist», или хотим placement-engine, который
  старается компактно разносить power/signal? Моя ставка — допустимо: схема
  для ngspice, не для печати в журнал; визуализация — отдельная задача
  (есть в backlog T032 рендер SVG для LLM-vision).
- **Q3.** GND и net 0. Сегодня в T004-адаптере есть `GND → 0`
  substitution. Должен ли фасад писать сразу `(global_label "0")`
  (упрощает netlist, но менее «человечно» для GUI), или продолжать ставить
  `power:GND` symbol и держать substitution в адаптере (как сейчас)?
  Моя ставка — оставить как сейчас: ground выглядит как ground в GUI,
  substitution — деталь pipeline'а.
- **Q4.** Лампы из T007 — как фасад биндится к `SpiceModel`? Я вижу два
  пути: (а) на стороне фасада объявить базовый `TubeSymbol(pin_count=8,
  octal=True)` с произвольным lib_id (хоть кастомный — мы убедились на
  T008, что кастомные `lib_symbols` валят GUI, так что лучше брать из
  стандартной библиотеки KiCad — `Simulation_SPICE:OPAMP` для общего
  subckt-stand-in?); (б) генерить XV1 как subcircuit instance с уже
  заданными пинами из `SpiceModel.subckt_pins`. Какой путь предпочтительнее?
- **Q5.** Тестовая стратегия. План:
  - Domain unit-тесты на `Schematic` / `Component` (без I/O).
  - Adapter integration: round-trip через `kicad-cli sch erc` + `sch export
    netlist` + `ngspice -b` на каждой из 3 фикстур (RC, SE-amp,
    выпрямитель). GUI-открытие — ручной шаг Владимира перед merge (как мы
    договорились в `feedback_kicad_fixtures`).
  - Coverage ≥ 80% на новом пакете.
  Возражения? Хочешь дополнительно golden-file тесты на байт-уровне (на
  каждой регрессии будут перегенериться, но дают сигнал «формат поменялся»)?
- **Q6.** Имя фасада: я предложил `efactory.schematic` (как порт). По
  hexagonal-конвенции (T085) outbound порт лежит в `src/ports/outbound/
  schematic_writer.py`, а конкретный адаптер — в
  `src/adapters/outbound/schematic_kicad/`. Подойдёт такой layout?
  Альтернатива — поставить весь фасад в одно место без hexagonal-разбивки,
  если он строго infrastructure. Я голосую за hexagonal — упростит будущую
  замену реализации (например, на upstream kicad-python в Phase 8).

### Resolved (с ответами)

- **Q0 — upstream `kicad-python` IPC API (вариант E) как fallback «подождать».**
  **Отвергнуто (2026-05-18).** Причины:
  - `kicad-python` 0.7.1 (17.04.2026) покрывает **только PCB** (`.kicad_pcb`);
    `.kicad_sch` не поддерживается, в roadmap KiCad 10 не входит.
  - GitLab issue #2077 «Schematic Editor Python API» **открыт с 28.10.2017**
    (8.5 лет), без milestone и без заявлений KiCad-команды о target-релизе.
  - Реалистичный горизонт появления — KiCad 11 (~март 2027) в оптимистичном
    сценарии; KiCad 12 (~2028) — реалистичнее. 1–2 года ожидания без гарантий.
  - Архитектурно IPC API требует **running KiCad с API server** (Protobuf
    через socket) — плохо ложится на наш headless CI / batch-LLM / kicad-cli
    pipeline. Будет уместен для **T026** (staged-modifications при открытом
    GUI) и для части **T079** (Phase 8) **рядом** с генератором, а не вместо.
  - Запись T079 в BACKLOG надо переформулировать соответственно (отдельной
    правкой, не в scope T100).

- **Q1 — выбор архитектурного варианта из §6 (A/B/C/D).** **Решено: D
  (собственный фасад поверх `sexpdata`) с fallback на B** (bundled freeze
  KiCad 8/9 текстовых библиотек + `kicad-sch-api` как backend) при провале
  Phase 0. (2026-05-18.) Обоснование:
  - Pre-spike показал: из `kicad-sch-api` мы реально используем 1 функцию
    (`load_schematic`) ради 78 транзитивных deps (mcp/fastmcp/uvicorn) —
    плохой supply chain trade-off.
  - Форк (A) потребует разобрать **бинарный per-symbol формат** KiCad 10
    `*.kicad_symdir/*.kicad_sym` — нетривиально и не закроет наши задачи
    лучше, чем D.
  - Bypass cache (C) — хрупко на upgrade библиотеки.
  - D позволяет сделать API под наш use case (LLM-driven Phase 1b — функции
    должны быть «как LLM хочет», не «как библиотечный maintainer хочет»).
  - Будущая миграция на upstream IPC API (когда созреет, годы вперёд)
    выполняется заменой адаптера под капотом — пользовательский фасад
    `efactory.schematic` остаётся.
  - **Kill-switch / fallback план:** если Phase 0 не сходится за ~6 часов
    реальной работы (двойная моя оценка) — переключаемся на B без
    переписывания пользовательского API. Фасад изначально проектируется так,
    чтобы внутренний backend подменялся.
  - **Фазовая разбивка** (фиксируется здесь как обязательство дисциплины
    Phase 0 = одна сессия):
    - **Phase 0** (1 сессия): минимальный фасад — `Resistor`, `Capacitor`,
      `VoltageSource(DC)`, `Ground`, `Wire`. Acceptance: переписать
      существующую `tests/fixtures/rc_filter.kicad_sch` через API, ngspice
      OP/TRAN/AC выдают идентичные значения T008.
    - **Phase 1** (1 сессия): `Inductor`, `Diode`, `VoltageSource(AC/Sin)`,
      acceptance — half-wave rectifier фикстура.
    - **Phase 2** (1 сессия): `BJT`, `MOSFET`, `TubeSubcircuit` через
      T007 `SpiceModel`. Acceptance — SE-amp на 6П14П из библиотеки T006.
    - **Phase 3** (1 сессия): coverage ≥ 80%, ADR T100 в `DECISIONS.md`
      (фиксирует выбор D + альтернативы + миграционный план), переписать
      все оставшиеся `tests/fixtures/*.kicad_sch` через API.
  - **Приём `golden-as-template`:** Phase 0 — это рефакторинг
    «hardcoded `rc_filter.kicad_sch` (уже работающий) → параметризованная
    функция, генерирующая тот же файл». НЕ дизайн с нуля. Это снимает
    основной риск.

- **Q2 — auto-layout стратегия.** **Решено: sequential grid 25.4×25.4 мм.**
  «Нечитаемо в GUI» при N > ~10 компонентов допустимо: схема для ngspice,
  не для журнальной публикации. Красивая визуализация — отдельная задача
  T032 (рендер SVG для LLM-vision, Phase 3 backlog).

- **Q3 — GND и net 0.** **Решено: оставить как сейчас.** Фасад ставит
  `power:GND` symbol в схеме; `GND → 0` substitution делает T004-адаптер
  `KicadCliSchematicExporter`. Ground выглядит как ground в GUI; SPICE-
  совместимость — деталь pipeline'а, не часть API.

- **Q4 — Лампы T007.** **Решено: путь (б) уточнён.** `TubeSubcircuit`
  использует **стандартный N-pin generic symbol** из KiCad библиотек
  (`Connector_Generic:Conn_01_xNN`, где NN = число пинов из
  `SpiceModel.subckt_pins`), с simulation properties (`Sim.Device=subckt`,
  `Sim.Library=<path>`, `Sim.Name=<model_id>`) — KiCad 10 SPICE
  framework подцепит subckt из библиотеки T006. Reference `XV1/XV2/...`,
  value = `model_id`. **Кастомных `lib_symbols`-блоков не создаём**
  (chronicle T008: handmade lib_symbols валили KiCad GUI; нужно перейти
  через checked примеры из upstream KiCad — пока используем готовое).
  *Точный механизм Sim properties для KiCad 10 уточняется в начале
  Phase 2 (отдельный мини-спайк ≤30 минут).*

- **Q5 — Тестовая стратегия.** **Решено.**
  - Domain unit-тесты на builder API без I/O (что фасад складывает
    правильное дерево).
  - Adapter integration: каждая фикстура прогоняется через `kicad-cli sch
    erc` (0 ошибок) → `kicad-cli sch export netlist --format spice` →
    `ngspice -b` (батч-режим из T008). Ожидаемые значения (OP/TRAN/AC)
    сравниваются с T008 baseline.
  - **GUI-открытие** — ручной step Владимира перед merge каждой phase
    (закреплено в `feedback_kicad_fixtures`).
  - Coverage ≥ 80% на `src/adapters/outbound/schematic_kicad/`.
  - **Без байт-golden-file** (формат `.kicad_sch` меняется на minor-
    апгрейдах KiCad; golden создаст шум).

- **Q6 — Layout пакетов (hexagonal).** **Решено.**
  - Port: `src/ports/outbound/schematic_writer.py` — Protocol с методами
    типа `build_schematic(spec: SchematicSpec) -> Path`.
  - Adapter: `src/adapters/outbound/schematic_kicad/` — пакет с
    builder'ами компонентов, layout-engine, s-expr serializer, embedded
    `lib_symbols`-snippets (как package data, по аналогии с T006
    `data/models/`).
  - Domain types (если нужны value object'ы вроде `Pin`, `Net`,
    `Reference`) — в `src/domain/schematic.py`.
  - Use case (inbound) — **не вводим в T100**. Фасад в T100 используется
    напрямую из тестов и (позже) из chat-client; формальный use case
    появится при T004b / T021 (bridge_edit_and_resim) или в Phase 1b при
    интеграции LLM tool-use.
  - Будущая миграция на upstream IPC API — заменой адаптера, port и
    domain типы остаются.

---

## Analyze (заполняется Гвидо)

Прогон после Clarify-resolve (2026-05-18). Список issues:

### 🔴 Critical (фиксим до начала Phase 0)

- **C1 — Phase 0 списка компонентов недостаточно для repro `rc_filter`.**
  Spec заявляет Phase 0 = `Resistor`, `Capacitor`, `VoltageSource(DC)`,
  `Ground`, `Wire`. Но текущий `tests/fixtures/rc_filter.kicad_sch`
  содержит ещё **junction**'ы (4 шт, проверено через `load_schematic` —
  5 components: V1/R1/C1 + два `#PWR0x` power:GND) и **net labels**
  (для именования input/output). Без них acceptance «байт-аналог OP/TRAN/AC
  T008» не достижим даже на минимуме.
  **Фикс:** расширить Phase 0 списком до `Resistor`, `Capacitor`,
  `VoltageSource(DC)`, `Ground` (= `power:GND`-instance helper), `Wire`,
  `Junction`, `Label` (optional, если KiCad ERC требует имена цепей).
  Зафиксировано в Plan ниже.

- **C2 — Pre-spike не подтвердил, что фасад может писать без обращения к
  symbol cache.** `kicad-sch-api` падает на `components.add()` без cache;
  но мы пишем **не через `kicad-sch-api`**, а через свой serializer. Тем
  не менее: в нашем выводе нужно сложить `lib_symbols` блок INLINE
  (как KiCad eeschema делает) — иначе KiCad GUI на load сбегает в свою
  глобальную library table, которая на чужой машине может отличаться, и
  файл станет non-portable.
  **Фикс:** Phase 0 включает шаг «выдрать `lib_symbols` блок из текущего
  `rc_filter.kicad_sch` (там точные KiCad-валидные snippets для
  `Device:R`, `Device:C`, `Simulation_SPICE:VDC`, `power:GND`) и сохранить
  как embedded templates в `src/adapters/outbound/schematic_kicad/
  lib_symbols/*.sexp`». Это и есть «freeze-copy», упомянутая в §6 Q1.

### 🟡 Warning (обсудить / зафиксировать риск)

- **W1 — Q4 механизм Sim properties для tube ещё не подтверждён живым
  тестом.** В Q4 я предположил, что KiCad 10 SPICE framework позволяет
  навесить на `Connector_Generic:Conn_01_xNN` симуляционные properties
  (`Sim.Device=subckt`, `Sim.Library`, `Sim.Name`) и export подцепит
  subckt из библиотеки T006. Это правдоподобно (KiCad 10 ввёл новый Sim
  Model dialog), но **не подтверждено**. Без подтверждения Phase 2
  блокируется.
  **Mitigation:** в начале Phase 2 — мини-спайк (≤30 мин): создать в KiCad
  GUI один компонент с tube subckt вручную, посмотреть какие properties
  KiCad записывает в `.kicad_sch`, реплицировать программно. Этот спайк
  УЖЕ есть в Resolved Q4, фиксирую сюда явно как риск Phase 2.

- **W2 — Manhattan-router для wires на 10+ компонентов может пересекаться
  с другими wire-сегментами.** KiCad GUI допускает пересечения, но они
  создают визуальный шум и могут породить ложные junction'ы (KiCad
  generously ставит junction на любой visual touch). Для Phase 0 (3
  компонента) и Phase 1 (4-5) — не проблема. Для Phase 2 (SE-amp ~10
  компонентов) — может всплыть.
  **Mitigation:** если на Phase 2 пересечения станут породить ложные
  net-merges, добавим примитивный «канальный» router (вертикальные/
  горизонтальные «коридоры» между рядами grid'а). Это ≤50 LOC, не блокер.

- **W3 — Settings нового пакета.** Spec не упоминает, нужны ли env-vars
  или config для адаптера (например, путь к KiCad symbol library, если
  захотим валидировать lib_id против реальной KiCad-установки). Пока
  embedded snippets закрывают use case без внешней зависимости.
  **Решение:** **не добавляем settings в T100.** Все embedded. Если
  понадобится — отдельная задача.

### 🟢 Note (к сведению)

- **N1 — TDD outside-in.** По `feedback_tdd` каждая phase начинается с
  e2e теста (red), который описывает acceptance целиком. Для Phase 0:
  `test_facade_rc_filter_produces_same_ngspice_op()` — собрать через API,
  сохранить, kicad-cli erc, netlist export, ngspice OP, сравнить с T008
  baseline. Сначала красный → реализация делает зелёным. Зафиксировано в
  Plan ниже.

- **N2 — Embedded `lib_symbols`-snippets — формат хранения.** Решение:
  каждый snippet — отдельный файл `.sexp` (text, не binary) в
  `src/adapters/outbound/schematic_kicad/lib_symbols/`, force-include в
  `pyproject.toml` (`[tool.hatch.build.targets.wheel.force-include]`
  или эквивалент), читается через `importlib.resources` (как в T006 для
  tube models). Не строковые константы в Python (раздуют файлы и
  затруднят diff при KiCad upgrade).

- **N3 — `lib_symbols` блок при KiCad upgrade.** При переходе на KiCad
  11 формат может расшириться (новые поля). Тесты через `kicad-cli
  10.0.2 sch erc` упадут немедленно при апгрейде CI на новый KiCad.
  Фикс: открыть фикстуру в новом KiCad GUI один раз, пересохранить,
  обновить snippets. Время — 1-2 часа на minor.

- **N4 — Hexagonal layout: тонкость.** Domain types (`Pin`, `Net`,
  `Reference`, `ComponentSpec`, `SchematicSpec`) живут в
  `src/domain/schematic.py`, **не** в адаптере. Адаптер только сериализует
  domain spec в `.kicad_sch`. Это даёт чистую заменимость (если в Phase 8
  переедем на upstream IPC, domain не трогаем).

---

## Plan (Phase 0 detailed, остальные — заголовки)

### Phase 0 — Minimal RC reproducer (1 сессия)

**Цель:** переписать `tests/fixtures/rc_filter.kicad_sch` через фасад,
acceptance — ngspice OP/TRAN/AC идентично baseline T008.

**Шаги (outside-in TDD):**

1. **e2e red:** `tests/integration/schematic_kicad/test_rc_facade.py` —
   полный сценарий: фасад → save → kicad-cli erc → netlist → ngspice OP
   → assert `|V_out| ≈ 1V`. Тест красный (фасада нет).
2. **Выдрать `lib_symbols` snippets** из текущего
   `tests/fixtures/rc_filter.kicad_sch` через `sexpdata.loads`, разрезать
   на отдельные `.sexp`-файлы: `Device.R.sexp`, `Device.C.sexp`,
   `Simulation_SPICE.VDC.sexp`, `power.GND.sexp`. Сохранить в
   `src/adapters/outbound/schematic_kicad/lib_symbols/`.
3. **Domain types** в `src/domain/schematic.py`:
   `ComponentSpec(lib_id, reference, value, position, properties)`,
   `WireSpec(start, end)`, `JunctionSpec(at)`, `Net(name, power)`,
   `SchematicSpec(name, components, wires, junctions, labels)`. Frozen
   dataclasses или pydantic — по vibe-style остальных доменных типов
   (проверю).
4. **Port** `src/ports/outbound/schematic_writer.py`: `Protocol` с
   `write(spec: SchematicSpec, path: Path) -> None`.
5. **Adapter skeleton**
   `src/adapters/outbound/schematic_kicad/writer.py`:
   - sexpr-builder (поверх `sexpdata.dumps` + ручной форматтер с
     tab-индентацией под KiCad eeschema style).
   - assembler: header (version 20240128, generator "efactory"), uuid,
     paper, embedded `lib_symbols` (из snippets), symbol blocks
     (components с UUID, properties, default fields), wires, junctions,
     labels, sheet_instances.
   - atomic write через tmp + `Path.replace`.
6. **Facade** `src/adapters/outbound/schematic_kicad/facade.py`:
   - `Schematic(name)` — fluent API.
   - `add_resistor(ref, value)` / `add_capacitor(...)` / `add_v_dc(...)` /
     `add_ground()` / `connect(pin_a, pin_b)`.
   - Sequential grid layout под капотом (25.4 мм step).
   - `save(path)` — материализует `SchematicSpec` и вызывает writer.
7. **Phase 0 e2e зелёный.** Coverage ≥ 80% на новом пакете.
8. **Phase 0 closing:** перенос BOARD T100 в Done с пометкой про phase,
   но T100 целиком ещё не закрывается — продолжаем на Phase 1+ в
   следующей сессии.

**Kill-switch:** если Phase 0 не сходится за ~6 часов реальной работы
(двойная оценка) — pause, switch to fallback B (bundled freeze KiCad 8/9
+ `kicad-sch-api`), фасад остаётся, реализация подменяется.

### Phase 1 — Diode/Inductor/V_AC + half-wave rectifier (1 сессия)

Заголовок; детальный план — после Phase 0.

### Phase 2 — BJT/MOSFET/TubeSubcircuit + SE-amp 6П14П (1 сессия)

Включает мини-спайк по KiCad 10 Sim properties (W1). Заголовок;
детальный план — после Phase 1.

### Phase 3 — Cleanup, ADR T100, переписать оставшиеся фикстуры

Заголовок; детальный план — после Phase 2.
