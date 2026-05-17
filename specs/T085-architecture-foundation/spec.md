# Spec: Архитектурный фундамент — Hexagonal layout

**Статус:** Analyzed
**Дата создания:** 2026-05-17
**Связанные документы:** `DECISIONS.md` (новые ADR блоки появятся
после clarify), `CONCEPT.md` §18 (таблица «готовое vs своё»).

---

## 1. Overview

Заложить архитектурный фундамент проекта efactory: **Hexagonal
architecture (Ports & Adapters)** с явным разделением domain /
application / ports / adapters / composition. Зафиксировать
выбор стека persistence (SQLAlchemy 2.0 + SQLite для метаданных,
Kùzu для графа топологий), правила работы с domain-моделями
(Pydantic v2 с поведением) и DTO-моделями (отдельны от domain),
async-первичность.

Цель — задать рамки до того, как начнётся реализация задач
дорожной карты концепта (T002+), чтобы код не превратился в
"big ball of mud" по мере роста до целевых ~5200 строк и за
их пределами.

## 2. Сценарии использования

Эта задача — инфраструктурная, без user-facing функциональности.
Сценарии описывают, как **фундамент влияет на последующую работу**:

- Каждая последующая задача дорожной карты (T002, T004, T010, ...)
  кладёт код в заранее заданный слой согласно правилам, описанным
  в README соответствующей папки.
- Любая новая интеграция (новый ИИ-провайдер, CAD-формат, симулятор,
  ещё один MCP-сервер) добавляется как outbound-адаптер за стабильным
  port-интерфейсом, без правок domain и application.
- Замена технологии (SQLAlchemy → другой ORM, Kùzu → Neo4j, anthropic
  SDK → openai-compat) затрагивает только соответствующий adapter,
  не пробрасывается в верхние слои.
- Юнит-тесты domain и application пишутся без поднятия БД и
  внешних сервисов — порты подменяются in-memory fake-ами через
  Protocol-структурную типизацию.

## 3. Functional Requirements

ДОЛЖНА:

- Структура `src/` соответствовать hexagonal layout с папками
  `domain/`, `application/`, `ports/`, `adapters/`, `composition/`.
- Каждая папка верхнего уровня иметь свой `README.md` с правилами
  «что сюда / что не сюда», чтобы новые задачи могли быть размечены
  без перечитывания spec-а.
- Domain-модели — Pydantic v2, с **поведением** (методы, бизнес-
  инварианты), value objects — `model_config = ConfigDict(frozen=True)`.
- Domain не зависеть ни от чего, кроме Pydantic и stdlib (ни от
  SQLAlchemy, ни от Kùzu, ни от HTTP-клиентов, ни от MCP, ни от
  Typer).
- Application содержать только тонкие use cases — оркестрация портов;
  бизнес-логика живёт в domain.
- Ports быть `typing.Protocol`-интерфейсами, разделёнными на
  `ports/inbound/` (что система предлагает миру) и `ports/outbound/`
  (что система требует от мира).
- Adapters реализовывать ports, изолированы по технологии в подпапках
  (`adapters/inbound/cli/`, `adapters/outbound/persistence_sql/`, ...).
- Composition root собирать граф зависимостей в одном месте
  (`composition/`), без DI-контейнера.
- Async везде: порты, адаптеры, use cases — все методы async по
  умолчанию.
- Persistence-модели SQLAlchemy лежать **только** в outbound-адаптере
  (`adapters/outbound/persistence_sql/models.py`), не утекать в domain.
- Маппинг domain ↔ persistence — явными функциями в том же адаптере.
- Walking Skeleton — один сквозной use case (`CreateProject`),
  проходящий все слои end-to-end, как доказательство, что структура
  стыкуется.
- **TDD-first во всём проекте.** Никакой production-код не
  пишется до падающего теста на эту строку (Red → Green → Refactor).
  Подход — **outside-in**: сначала acceptance/e2e-тест на use case,
  потом тесты application use case с fake-портами, потом тесты
  конкретных адаптеров. См. §5 «Test structure» и отдельный ADR.
- Изоляция слоёв проверяться автоматически через
  **`import-linter`** в обязательной цепочке проверок перед `git
  push` (как 5-я проверка после ruff/format/mypy/pytest).
- Конфигурация — **`pydantic-settings`** с одним классом `Settings`
  в `composition/settings.py` с первого дня (пути к SQLite/Kùzu/
  файлам проекта, API-ключи через env vars).
- Логирование — минимальный `logging.basicConfig(level=INFO)`,
  без структурного формата. Структурное логирование — отдельная
  задача T010 из дорожной карты.

МОЖЕТ:

- В будущем заменить ручную композицию DI-контейнером (dependency-
  injector / punq), если граф зависимостей станет неуправляемым.
- Заменить SQLite на PostgreSQL без изменения domain/application —
  драйвер async SQLAlchemy уже это покрывает.
- Разделить плоский `domain/` на bounded contexts
  (`electrical/`, `mechanical/`, `magnetics/`) — **когда** накопится
  10+ моделей и подкатегории станут очевидны (не сейчас).

НЕ ДОЛЖНА:

- Domain импортировать что-либо за пределами `pydantic`/`stdlib`/
  внутрь самого domain.
- Application импортировать adapters напрямую — только ports.
- Adapters импортировать друг друга (если возникает потребность —
  это сигнал, что общая логика должна жить в domain или application).
- SQLAlchemy declarative-модель использоваться как domain-модель
  (даже «временно для скорости»).
- DTO (входящие/исходящие сериализованные представления) совпадать
  с domain-моделями автоматически — отдельные классы, маппинг
  явный.
- Писать production-код раньше падающего теста (это нарушение
  TDD — фиксится возвратом к Red).

## 4. Success Criteria

- Скелет папок создан, в каждой папке верхнего уровня — `README.md`
  с правилами.
- Walking Skeleton (`CreateProject`) end-to-end сценарий проходит
  зелёным e2e-тестом (CLI → application use case → SQLAlchemy
  persistence + filesystem → domain.Project → CLI output).
- **TDD-дисциплина соблюдена:** для каждого production-модуля в
  git-истории фазы 2 есть commit-предшественник с падающим тестом
  (либо тест и реализация в одном commit-е, но с явным Red→Green
  в commit message). Для фазы 0 и фазы 1 (только инфраструктура,
  без бизнес-кода) TDD не применим — там скелет, конфиги, ADR.
- **5 обязательных проверок** качества зелёные:
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy src`
  - `uv run pytest` (coverage ≥ 80% на `src/`).
  - `uv run lint-imports` (правила изоляции слоёв через
    `import-linter`).
- Coverage на `src/domain/` ≈ 100%, на `src/application/` ≥ 90%
  (TDD-естественно). Общий threshold остаётся 80% (нижняя
  планка для адаптеров и composition root).
- `DECISIONS.md` дополнен новыми ADR-блоками (отдельный блок на
  каждое принципиальное решение: hexagonal layout, Pydantic domain
  + separate persistence, SQLAlchemy 2.0 + SQLite, Kùzu graph
  store, async-first, manual DI, pydantic-settings, import-linter
  для изоляции слоёв, TDD-first).
- `pyproject.toml` содержит новые зависимости: runtime —
  `pydantic`, `pydantic-settings`, `sqlalchemy[asyncio]`,
  `aiosqlite`, `alembic`, `kuzu`, `typer`, `mcp`, `anthropic`;
  dev — `import-linter`.
- Alembic инициализирован, есть стартовая (возможно пустая)
  миграция-плейсхолдер.
- `import-linter` сконфигурирован в `pyproject.toml` с явными
  правилами:
  - `domain` не импортирует `application`, `ports`, `adapters`,
    `composition`.
  - `application` не импортирует `adapters`, `composition`;
    может импортировать `domain`, `ports`.
  - `ports` импортируют только `domain` и stdlib.
  - `adapters` не импортируют друг друга и `composition`.

## 5. Key Entities

### Слои

| Слой | Что лежит | Что НЕ лежит |
|------|-----------|--------------|
| `domain/` | Pydantic-модели предметной области (Component, Schematic, Board, ...), value objects, domain services (поведение), доменные исключения | ORM, HTTP, файловые операции, логирование, конфиги |
| `application/` | Use cases — тонкая оркестрация портов | Бизнес-инварианты (они в domain), детали технологий |
| `ports/inbound/` | `Protocol`-интерфейсы для входящих вызовов (CLI-команды, MCP-tools, HTTP-handlers) | Конкретные реализации |
| `ports/outbound/` | `Protocol`-интерфейсы того, что нужно application от мира (Repository, AIProvider, MCPClient, FileStore) | Конкретные реализации |
| `adapters/inbound/` | Конкретные inbound: `cli/` (Typer), `mcp_server/` (наш MCP-сервер) | Бизнес-логика |
| `adapters/outbound/` | Конкретные outbound: `persistence_sql/` (SQLAlchemy+SQLite), `graph_store/` (Kùzu), `file_store/` (FS), `ai_anthropic/`, `mcp_client/` | Бизнес-логика, перекрёстные импорты других адаптеров |
| `composition/` | Composition root — сборка графа зависимостей, парсинг конфига, main entrypoint | Бизнес-логика |

### Outbound-порты на старте (как Protocol-интерфейсы)

- `MetadataRepository` — CRUD метаданных проектов, компонентов и т.д.
  Реализация: SQLAlchemy 2.0 async + aiosqlite.
- `TopologyGraphStore` — узлы и рёбра топологии, графовые запросы.
  Реализация: Kùzu (sync API обёрнут в `asyncio.to_thread`).
- `ProjectFileRepository` — чтение/запись файлов проекта (KiCad-проекты,
  YAML/JSON). Реализация: filesystem.
- `AIProvider` — отправка сообщений в LLM с tool use. Первая реализация:
  Claude через `anthropic` SDK.
- `MCPClient` — клиент внешних MCP-серверов. Реализация: `mcp` Python
  SDK.

> **Замечание:** на этапе T085 реализуется **только то, что нужно
> Walking Skeleton**. Остальные ports могут быть оставлены как
> Protocol-«заглушки» с TODO-комментарием — их реализация приходит
> в задачах дорожной карты (T004/T010/T012/T013/...).

### Inbound-порты на старте

- `CLI` — командная строка. Реализация: Typer.
- `MCPServer` — наш MCP-сервер для внешних ИИ (обёртка над application
  use cases как MCP-tools). Реализация: `mcp` Python SDK.

### Domain-модели

На старте — **минимальный набор для Walking Skeleton**: один
агрегат `Project` (имя, путь, дата создания) + один enum/VO для
статуса. Реальные domain-модели (Component, Schematic, Board,
Pin, Net, Footprint, BOM, ...) добавляются задачами дорожной карты
по мере появления use cases. Здесь только устанавливаем правила:
Pydantic v2, frozen для VO, методы вместо анемичной модели.

Структура `domain/` — **плоская на старте**
(`domain/project.py`, `domain/<entity>.py`). Разделение на bounded
contexts (`electrical/`, `mechanical/`, `magnetics/`) — отдельной
задачей, когда накопится 10+ моделей и группы станут очевидны.

### Test structure

```
tests/
  unit/
    domain/           # чистые unit, без mock-ов (domain без I/O)
    application/      # use cases с fake-портами (Protocol → in-mem)
  integration/
    adapters/
      persistence_sql/  # реальный SQLite в tmp_path
      graph_store/      # реальный Kùzu в tmp_path (smoke в фазе 1)
      file_store/       # реальная FS в tmp_path
  e2e/
    walking_skeleton/   # сквозной CreateProject через CLI
  architecture/         # опционально, на случай если import-linter
                        # окажется недостаточен
```

Стек: `pytest` + `pytest-asyncio` + `pytest-cov` (уже в проекте).
Fake-порты — простые in-memory классы, реализующие соответствующий
`Protocol`. **Никаких `unittest.mock` для портов** — Protocol-
структурная типизация делает фейки дешевле и яснее моков.

## 6. Assumptions & Constraints

- Python 3.14+ (уже в `pyproject.toml`).
- `uv` как менеджер зависимостей.
- Async I/O везде (asyncio). Sync API внешних библиотек (Kùzu)
  заворачиваются в `asyncio.to_thread` в адаптере.
- Desktop-приложение, не cloud/serverless → embedded persistence
  (SQLite, Kùzu), без серверных процессов.
- Один пользователь, конкурентного доступа на старте нет.
- SQLAlchemy 2.0+ с typed declarative (`Mapped[]`, `mapped_column`).
- Кроссплатформенность: Linux и Windows как минимум.

## 7. Out of Scope

- **Конкретные domain-модели "Component", "Schematic", "Board" и др.**
  — добавляются задачами дорожной карты (T004 и далее) по мере
  появления use cases. Walking Skeleton использует один минимальный
  пример.
- **Полная реализация outbound-адаптеров** AIProvider, MCPClient,
  ProjectFileRepository — каркасные интерфейсы только; реальные
  реализации придут в T012/T013/T010 и т.д.
- **Inbound MCP-сервер** в полноценном виде — каркас и один tool как
  доказательство стыковки; полноценная реализация — отдельная задача.
- **Vector store** (для RAG по каталогу компонентов) — отложено до
  появления конкретных use cases.
- **Очередь долгих задач** (Celery/Dramatiq/Arq) — не сейчас.
- **Многопользовательский режим, аутентификация, авторизация** —
  out of scope для desktop-приложения.
- **Контейнеризация, production deployment** — десктоп, distribution
  через `uv` / wheel — отдельная история.
- **Структурное логирование** — это задача T010 из дорожной карты,
  не дублируем; на этапе T085 используем `print` / минимальный
  `logging.basicConfig`.
- **Полноценный MCP-сервер** в виде inbound-адаптера со всеми
  tool-ами — это задача T013 и далее; здесь только Protocol-каркас.
- **GUI, web-интерфейс** — отдельные задачи фазы 8 (T076).
- **Bootstrap (системные зависимости KiCad/ngspice/FreeCAD/FEMM)** —
  задачи T002/T003.

---

## Clarify (заполняется Claude)

### Resolved

**Первая итерация clarify, 2026-05-17 — фундаментальные выборы:**

- **Q:** Какой диалект слоистой архитектуры?
  **A:** Hexagonal (Cockburn, Ports & Adapters) — самый аскетичный,
  без лишних слоёв «Use Case Interactor» / «Boundary».
- **Q:** Async или sync?
  **A:** Async везде. Sync внешние API заворачиваем в
  `asyncio.to_thread` в адаптере.
- **Q:** Чем описывать domain-модели?
  **A:** Pydantic v2, с методами (не анемичная модель). Value
  objects — `frozen=True`.
- **Q:** Может ли SQLAlchemy-модель использоваться как domain?
  **A:** Нет. Отдельные классы, явный маппинг в адаптере.
- **Q:** Чем persistence?
  **A:** SQLAlchemy 2.0 async + aiosqlite (метаданные) + Alembic
  (миграции) + Kùzu (граф топологий, embedded, MIT, Cypher-like).
- **Q:** MCP — inbound или outbound?
  **A:** Оба. Inbound — мы MCP-сервер для внешних ИИ; outbound —
  мы MCP-клиент внешних серверов.
- **Q:** Чем порты — Protocol или ABC?
  **A:** `typing.Protocol`. Структурная типизация, проще mock-и.
- **Q:** DI-контейнер?
  **A:** Нет на старте. Ручная композиция в `composition/`.

**Вторая итерация clarify, 2026-05-17 — детали реализации:**

- **Q:** Walking Skeleton — какой use case?
  **A:** `CreateProject` (вариант b): `efactory project create --name
  my-amp` → application use case → SQLAlchemy сохраняет запись
  проекта + создаётся папка проекта (filesystem) → возвращается
  `domain.Project`. Без Kùzu (откладывается). Близко к T010
  концепта.
- **Q:** Логирование на этапе T085?
  **A:** Минимальный `logging.basicConfig(level=INFO)` в composition
  root. Полноценное структурное логирование — задача T010.
- **Q:** Settings/config?
  **A:** Сразу `pydantic-settings`. Один класс `Settings` в
  `composition/settings.py` с путями к SQLite/Kùzu/projects-root,
  API-ключи через env vars. Избавляет от хардкода с первого дня.
- **Q:** Sub-папки `domain/` — плоско или bounded contexts?
  **A:** Плоско на старте (`domain/project.py`, `domain/<entity>.py`).
  Разделение на bounded contexts отдельной задачей, когда накопится
  10+ моделей.
- **Q:** ADR — один большой или несколько мелких?
  **A:** Несколько отдельных ADR-блоков (один блок = одно решение).
  Каждое можно отдельно пересмотреть в будущем без затрагивания
  остальных.
- **Q:** Инструмент изоляции слоёв?
  **A:** `import-linter` с правилами в `[tool.importlinter]`
  в `pyproject.toml`. Команда `lint-imports` — пятая в обязательной
  цепочке проверок перед push.
- **Q:** Kùzu в Walking Skeleton?
  **A:** Отложить. На фазе 1 — отдельный smoke-тест адаптера
  (открыть БД, создать узел, прочитать узел), чтобы зависимость
  не лежала «мёртвым грузом». Полноценное использование — в первой
  задаче дорожной карты, которая реально требует графа (T004 /
  T005 / T037).

**Третья итерация clarify, 2026-05-17 — методология разработки:**

- **Q:** Какую методологию разработки применяем во всём проекте?
  **A:** **TDD строго (Red → Green → Refactor).** Никакая строка
  production-кода не пишется до падающего теста. Outside-in для
  hexagonal: acceptance/e2e-тест → тесты application use case
  с fake-портами → тесты адаптеров. Domain — без mock-ов (нет
  внешних зависимостей). Адаптеры — integration с реальными
  технологиями (SQLite в `tmp_path`, Kùzu в `tmp_path`, FS в
  `tmp_path`). Fake-порты — простые in-memory классы, реализующие
  `Protocol`; без `unittest.mock`. Зафиксировано отдельным ADR
  и в `feedback_tdd.md` (auto-memory + mem0).

### Open questions

Нет открытых вопросов. Все решения зафиксированы; spec переведён
в статус **Analyzed** после прогонки Analyze ниже.

---

## Analyze

### 🔴 Critical

1. **Kùzu Python binding под Python 3.14.** `pyproject.toml`
   требует `requires-python = ">=3.14"`. Kùzu публикует wheel-ы
   на PyPI, но поддержка свежих Python-версий иногда отстаёт
   на несколько месяцев. Если на 2026-05-17 нет wheel для 3.14
   — это блокирует выбор Kùzu и потребует либо downgrade Python
   проекта, либо смену графовой БД, либо сборку из исходников
   (нежелательно). **Митигация:** в фазе 1, **первым шагом** при
   `uv add kuzu` — проверить, что устанавливается без ошибок
   под 3.14 на Linux и (по возможности) Windows. Если падает —
   немедленно стоп, обсуждение с Владимиром: рассматриваем
   варианты (NetworkX-persisted-в-SQLite как fallback на старте;
   Neo4j embedded не существует; downgrade Python — нежелателен,
   так как 3.14 — целевой по `requires-python`). До этой проверки
   ADR по Kùzu в `DECISIONS.md` помечен как «провизорный, см.
   T085 фаза 1».

### 🟡 Warning

2. **Alembic + async SQLAlchemy.** Стандартный `alembic init` даёт
   sync-шаблон `env.py`. Под async-engine нужен немного другой
   `env.py` (через `connection.run_sync(do_migrations)`). Шаблон
   `alembic init -t async` это покрывает — использовать именно
   его при инициализации в фазе 1.

3. **mypy + SQLAlchemy 2.0 typed declarative.** Чтобы mypy корректно
   понимал `Mapped[]` / `mapped_column`, нужен plugin
   `sqlalchemy.ext.mypy.plugin` (он deprecated в пользу новой
   нативной поддержки PEP 484 в SQLA 2.x, но на части типов
   pyright/mypy всё ещё спотыкаются). **Действие:** при первой
   `mapped_column` модели в фазе 1 проверить вывод mypy; при
   необходимости добавить `plugins = ["sqlalchemy.ext.mypy.plugin"]`
   в `[tool.mypy]`. Это **не** «обходной манёвр» (не `# type:
   ignore`, не расширение ignore-секции), а штатная конфигурация
   plugin-а — без отдельного согласования.

4. **`mcp` Python SDK и `anthropic` SDK — версии и наличие.**
   `mcp` — официальный SDK MCP-протокола (от Anthropic / opensource).
   `anthropic` Python SDK — для Anthropic API. Оба на PyPI, но
   нужно проверить актуальные версии в фазе 1 при добавлении.
   Для Walking Skeleton они **не нужны** (CreateProject ходит
   только в SQLAlchemy + FS) — можно добавить как dependencies
   с обоснованием «каркас для будущих фаз» или отложить добавление
   до первой задачи, которая их использует. **Рекомендация:**
   отложить — добавляем dependency, когда есть код, который её
   импортирует. До тех пор Protocol-каркас в `ports/outbound/`
   и пустой адаптер не требуют SDK.

5. **`import-linter` и cyclic-detection.** Конфиг через
   `[tool.importlinter]` в `pyproject.toml`, контракты типа
   `layers` (`high level → low level`) — стандартное. Слой
   `composition` импортирует ВСЕ остальные (он же composition
   root), это допустимо и явно описывается в контракте как
   «верхний слой». При первом запуске возможны false positive-ы
   на `__init__.py` — фиксим конкретными исключениями в контракте,
   не расширением правил.

6. **Walking Skeleton без Kùzu vs «smoke-тест Kùzu в фазе 1».**
   В фазе 1 Kùzu добавляется как dependency и пишется simplest-
   возможный integration-тест адаптера. Если в Critical #1 Kùzu
   падает на 3.14 — этот smoke-тест становится Red, что мгновенно
   подсвечивает проблему. Это **намеренное** дублирование
   страховки: smoke-тест в фазе 1 + полноценное использование
   позже.

### 🟢 Note

7. **`Project` ID в Walking Skeleton.** UUID4 (нативный
   `uuid.uuid4()`) — простой и достаточный для старта. Name-based
   constraints (unique по `name`) можно добавить позже отдельным
   index/constraint. Решение по детали — в фазе 2 при
   имплементации.

8. **TDD и фаза 0/1.** TDD-дисциплина применима к production-коду
   (фаза 2 Walking Skeleton — `application/use_cases.py`,
   `adapters/.../repository.py` и т.д.). Фаза 0 (spec + ADR) и
   фаза 1 (скелет папок, README, конфиги, миграция-плейсхолдер) —
   инфраструктура и документация, без бизнес-кода; TDD здесь не
   применим. Это **не** компромисс TDD, это область применения.

9. **Coverage threshold ≥ 80% уже сейчас.** Walking Skeleton —
   маленький, тестов будет немного, но они должны давать ≥ 80%
   на свой код. После фазы 2 coverage оценивается на `src/`
   как обычно.

10. **`pydantic-settings` для secrets.** API-ключи (Anthropic
    и др.) читаем через env vars (`ANTHROPIC_API_KEY`), не из
    файлов в репо. `.secrets` в корне проекта (уже в
    `.gitignore`) — допустимое место для local-only env-файла,
    загружаемого через `SettingsConfigDict(env_file='.secrets')`.

11. **MCP-сервер inbound — что внутри.** Полноценный inbound
    MCP-server (`adapters/inbound/mcp_server/`) с реальными
    tool-ами — задача отдельная (близка к T013). В T085 от него
    нужен только Protocol-каркас `MCPServer` в `ports/inbound/`
    и `__init__.py`-заглушка адаптера. Без зависимости на `mcp`
    SDK (она появится с реализацией).

12. **CLI как inbound в Walking Skeleton.** Реализуется только
    один CLI-command (`efactory project create`). Typer
    добавляется как dependency. Минимальный CLI в `main.py`
    (точка входа `uv run efactory ...`) — настраивается через
    `[project.scripts]` в `pyproject.toml`.

13. **Pydantic в domain vs DTO — где провести границу.** В
    адаптерах inbound (CLI/MCP) DTO **не нужен** для CreateProject:
    Typer сам валидирует CLI-аргументы как примитивы (str), мы
    собираем из них domain-модель прямо в адаптере перед вызовом
    use case. DTO как отдельный класс появится, когда формы
    реально разойдутся (HTTP-API, MCP-tool со сложным JSON-input).

14. **`__init__.py` в каждой папке слоя.** Python 3.14 поддерживает
    namespace packages, но для явных импортов и работы import-linter
    кладём `__init__.py` в каждую папку слоя (`src/__init__.py`,
    `src/domain/__init__.py` и т.д.). Пустые.
