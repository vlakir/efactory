# Spec: T097 — Phase VO + derived Project.status + Update use case

**Статус:** Analyzed
**Дата создания:** 2026-05-17
**Связанные документы:**
- `DECISIONS.md` → ADR 2026-05-17 «Domain expansion direction: D»
  (T097 = фаза B этого направления).
- `CONCEPT.md` §4.1 (концепция проекта), §4.3 (манифест с
  enum статусов), §4.6 (CLI-команды управления проектом), §4.7
  (события автоматических переходов).
- `BACKLOG.md` → запись T097 (исходный набросок).
- `specs/T096-domain-expansion/spec.md` (discovery направления D).

---

## 1. Overview

В domain'е efactory сейчас единственный stored атрибут жизненного
цикла Project'а — поле `status` с ровно одним значением `CREATED`.
Это и нормально для walking skeleton, и недостаточно для дальнейшей
работы: реальная жизнь проекта в концепте (§4.3) — это движение
по шести фазам (schematic → simulation → pcb → magnetics →
enclosure → documentation), с возможностью пропускать ненужные.

T097 переводит «фазу» из заглушки в полноценный domain value object,
расширяет `ProjectStatus` до семи значений CONCEPT §4.3 и делает
сам `status` **derived computed property** от состояний фаз. Заодно
появляется первый Update use case, который обкатает шаблон «изменить
агрегат, переписать persistence» на уже работающем CRUD-наборе.

## 2. User Stories

Пользовательский интерфейс — пока только CLI (`efactory ...`),
LLM-чат и веб появятся позже по дорожной карте. Поэтому
формулируем как «сценарии использования».

- Как разработчик РЭА, я хочу видеть, в какой фазе сейчас находится
  каждый из моих проектов (`efactory project show <name>`), чтобы
  не вспоминать «на чём остановился».
- Как разработчик РЭА, я хочу пометить фазу как начатую / завершённую
  / пропущенную (`efactory project update ...`), чтобы вручную вести
  состояние проекта до появления автоматических триггеров (§4.7).
- Как разработчик РЭА, я хочу переименовать проект
  (`efactory project update --name`), не пересоздавая его.
- Как разработчик РЭА, я хочу выбрать «гибкий скоуп» проекта
  (§4.1) — явно пометить ненужные мне фазы как `skipped`, чтобы
  derived `status` корректно дошёл до `production_ready`, минуя
  неиспользуемые ступени.
- Как разработчик efactory, я хочу, чтобы попытка нарушить инвариант
  фазы (`complete()` без `start()`, повторный `start()`, и т.п.)
  падала с понятной ошибкой ещё в domain-слое, не дойдя до SQL.

## 3. Functional Requirements

### Domain

- ДОЛЖНА: появиться embedded value object `Phase` в `src/domain/project.py`
  (или `src/domain/phase.py`) с полями `name: PhaseName`,
  `status: PhaseStatus`, `started_at: datetime | None`,
  `completed_at: datetime | None`.
- ДОЛЖНА: `PhaseName` — `StrEnum` с шестью значениями из CONCEPT §4.3:
  `schematic`, `simulation`, `pcb`, `magnetics`, `enclosure`,
  `documentation`.
- ДОЛЖНА: `PhaseStatus` — `StrEnum` с четырьмя значениями:
  `pending`, `in_progress`, `done`, `skipped`.
- ДОЛЖНА: `Phase` иметь методы `start()`, `complete()`, `skip()` с
  инвариантами, которые при нарушении бросают `ValueError`:
  - `start()` валиден только если `status == pending` →
    переводит в `in_progress`, проставляет `started_at`.
  - `complete()` валиден только если `status == in_progress` →
    переводит в `done`, проставляет `completed_at`.
  - `skip()` валиден если `status in {pending, in_progress}` →
    переводит в `skipped`, `completed_at` **не** проставляется.
- ДОЛЖНА: `Project` содержать `phases: tuple[Phase, ...]` — ровно
  шесть элементов в фиксированном порядке (как в `PhaseName`); по
  умолчанию все `pending`.
- ДОЛЖНА: `Project.status` стать **computed property**, derived от
  `phases` по правилу «последовательной» зрелости (см. ниже маппинг).
- ДОЛЖНА: `ProjectStatus` enum расшириться до семи значений из
  CONCEPT §4.3: `idea`, `schematic`, `simulated`, `pcb_designed`,
  `magnetics_done`, `enclosure_done`, `production_ready`.
- ДОЛЖНА: stored поле `Project.status` исчезнуть — заменяется
  computed property.

**Маппинг derived `Project.status`** (из BACKLOG T097): по списку
фаз `[schematic, simulation, pcb, magnetics, enclosure,
documentation]` идём слева направо; фаза «закрыта» если
`status in {done, skipped}`. `Project.status`:

| Последняя «закрытая» фаза с начала | `Project.status`    |
|------------------------------------|---------------------|
| ничего не закрыто                  | `idea`              |
| `schematic`                        | `schematic`         |
| `simulation`                       | `simulated`         |
| `pcb`                              | `pcb_designed`      |
| `magnetics`                        | `magnetics_done`    |
| `enclosure`                        | `enclosure_done`    |
| `documentation`                    | `production_ready`  |

«Прыжки» через фазы вперёд (например, `pcb done` при `simulation
pending`) → derived status НЕ продвигается дальше последней
непрерывно-закрытой фазы (т.е. остался бы `idea`). См.
Clarify #4 — это закреплено как сознательное решение, а не
default-поведение «без причины».

### Application

- ДОЛЖНА: появиться use case `UpdateProject` в `src/application/`
  с входным DTO, содержащим:
  - `project_id` (или `name` — см. Clarify #6);
  - `new_name: ProjectName | None` (опционально);
  - `phase_updates: tuple[PhaseUpdate, ...]` (опционально), где
    `PhaseUpdate(name: PhaseName, action: Literal['start', 'complete', 'skip'])`.
- ДОЛЖНА: при отсутствии у проекта (по id/name) — бросать
  `ProjectNotFoundError` (уже есть в коде, см. T089).
- ДОЛЖНА: при нарушении инварианта фазы — пробрасывать `ValueError`
  наружу без затирания (CLI его поймает и выведет).
- ДОЛЖНА: запись проекта в persistence идти **атомарно** —
  либо весь Update применился, либо ничего (одна SQL-транзакция).

### Adapters (persistence + CLI)

- ДОЛЖНА: SQL-схема получить новую таблицу `phases` (FK на
  `projects.id`, six rows per project) либо JSON-колонку в
  `projects` — выбор обоснован в Clarify #9.
- ДОЛЖНА: появиться Alembic-миграция, которая:
  - удаляет stored колонку `status` из `projects`;
  - добавляет phase-storage;
  - для существующих строк проектов backfill'ит шесть phase-rows
    со статусом `pending` (idempotent: повторный запуск не
    создаёт дубли).
- ДОЛЖНА: появиться CLI-команда `efactory project update`
  (Typer subcommand) со следующими флагами:
  - `--name <new_name>` — переименование (только display name,
    `path` не трогается, см. Clarify #6);
  - `--phase <name>` + `--status <pending|in_progress|done|skipped>` —
    переход фазы (синтаксис уточняется в Clarify #2/#3).
- МОЖЕТ: появиться CLI-shortcut `efactory project add-phase`
  и `efactory project skip-phase` — синтаксический сахар над
  `update` (поведение определяется в Clarify #2).
- ДОЛЖНА: `efactory project show` отображать таблицу фаз
  (имя, статус, started_at, completed_at) под основной шапкой
  (формат — см. Clarify #8).

## 4. Success Criteria

- TDD outside-in для всех новых use cases / методов: e2e (Red) →
  unit с fake-портами → integration → CLI → e2e Green. Без
  пропусков уровней.
- `uv run pytest` зелёный; coverage ≥ 80% на `src/` (ENforce'ed
  `--cov-fail-under`).
- `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src` — 0 ошибок.
- Alembic migration отрабатывает (a) на чистой БД, (b) на БД с
  существующими SQL-only проектами без потери данных проекта (id,
  name, path, created_at).
- `efactory project create new --path ...` → `efactory project
  show new` показывает `status: idea` и шесть `pending` фаз.
- `efactory project update new --phase schematic --status
  in_progress` затем `--phase schematic --status done` → `show`
  показывает `status: schematic`.
- Полный happy-path-сценарий (schematic → simulation → pcb →
  magnetics → enclosure → documentation, все done через update)
  даёт `status: production_ready` без правок кода.
- Сценарий «гибкий скоуп»: `update --phase magnetics --status
  skipped` и `--phase enclosure --status skipped`, при этом
  schematic/simulation/pcb done, documentation done → status =
  `production_ready` (skipped считается закрытой).
- Нарушение инварианта (`complete()` non-started фазы через CLI)
  → exit code != 0, на stderr — понятное сообщение, БД не
  изменилась.

## 5. Key Entities

- **`Phase`** — embedded value object. Frozen Pydantic-модель
  (immutable; методы `start/complete/skip` возвращают **новую**
  `Phase`, не мутируют — см. Clarify #1).
  - Поля: `name`, `status`, `started_at`, `completed_at`.
  - Инварианты на переходах статуса.
- **`PhaseName`** — `StrEnum`, 6 фаз, фиксированный порядок.
- **`PhaseStatus`** — `StrEnum`, 4 значения.
- **`Project`** — aggregate root. Поля: `id`, `name`, `path`,
  `created_at`, `phases: tuple[Phase, ...]`.
  - `status` — `@computed_field` (Pydantic v2) или обычный
    `@property` (см. Clarify #5).
  - Методы на агрегате: `rename(new_name)` (возвращает новый
    `Project`?), `transition_phase(name, action)` (возвращает
    новый `Project` с обновлённой фазой) — см. Clarify #1
    про mutability strategy.
- **`ProjectStatus`** — `StrEnum`, 7 значений, derived semantics.
- **`UpdateProject`** — application use case, координирует
  load → mutate → save через `ProjectRepository`.

## 6. Assumptions & Constraints

- Single-user CLI; конкурентного доступа к одному проекту нет.
  (Соотв., транзакционность нужна только в рамках одной команды,
  не для оптимистических локов между сессиями.)
- Persistence пока SQL + filesystem (как в walking skeleton).
  Manifest YAML вводится в T098 — здесь не трогаем.
- T097 не вводит автоматических триггеров переходов фаз из
  CONCEPT §4.7 (типа «симуляция прошла → simulation done»).
  Это придёт с реальными bridge'ами в Phase 1a+ дорожной карты.
- `created_at` остаётся как был. Новое поле `updated_at` не
  вводится в T097 — см. Clarify #10 (вернёмся при необходимости
  в T098, где manifest §4.3 содержит `updated`).
- Текущие тестовые проекты в локальном `~/.local/share/efactory/`
  не считаются production data; миграция должна их выдержать,
  но если что-то сломается — можно `rm` и пересоздать.

## 7. Out of Scope

- **Manifest `project.yaml`** — T098 (фаза C направления D).
  Никаких YAML-операций в T097, никакого outbound port
  `ProjectManifestRepository`.
- **Decision aggregate** — T099 (фаза A направления D).
- **Автоматические триггеры** §4.7 (схема изменена → phase auto-
  transition, симуляция завершена → simulated и т.п.). T097 — только
  ручной CLI Update.
- **`updated_at` / revision / author** из CONCEPT §4.3 manifest —
  вернёмся в T098, тут не пилим.
- **`/project import`, `/project archive`** §4.8 — потребуют
  manifest, т.е. T098+.
- **CLI вне `project`** — `efactory decision *` и пр. в T099.
- **Изменение `path` через update** — выход за scope: смена
  каталога проекта = move на диске + перепривязка БД, отдельная
  задача. `--name` НЕ затрагивает `path`.
- **Migration «old code base без status колонки» → новый формат
  на проде** — у нас нет прода. Тестовая БД одна, миграция одна,
  rollback не нужен.

---

## Clarify (заполняется Claude)

### Open questions

#### 1. Phase mutability: frozen VO с возвратом нового или мутируемая модель?

В CLAUDE.md и в зафиксированном feedback'е (mem0) принят принцип
**frozen Pydantic VO** для domain. Это значит, `phase.start()`
возвращает **новый** `Phase` с обновлённым `status` / `started_at`,
а сам `Project.transition_phase(name, action)` возвращает **новый**
`Project` с подменённой фазой в `phases`-кортеже.

Альтернатива — оставить `Project` нефрозен (как сейчас — `frozen=False`
в `ConfigDict`) и мутировать `phases`. Это проще читать, но
расходится с обещанием «frozen-VO» из ADR T085.

**Вопрос:** идём по frozen-VO (даже Project станет immutable —
`rename()` тоже возвращает новый объект)? Или ослабляем правило для
этой задачи, потому что Project — aggregate root, не VO?

**Предлагаемый дефолт:** `Phase` — frozen VO; `Project` остаётся
нефрозен (как сейчас), но методы переходов возвращают `self` после
in-place подмены `phases` (через `model_copy(update={'phases': ...})`).
Это сочетает «VO immutable» и «agg root управляет своим state».

---

#### 2. Семантика `add-phase` при том, что все 6 фаз присутствуют по умолчанию

В CONCEPT §4.6 команды `add-phase` / `skip-phase` подразумевают:
- проект создаётся с **подмножеством** фаз (через `--phases` флаг
  при create), остальные «не входят»;
- `add-phase` дописывает фазу позже, `skip-phase` помечает
  ненужной.

В T097 (ADR направления D) выбран более простой инвариант: «у проекта
**всегда** 6 phase-объектов, по умолчанию все pending». В этой модели
`add-phase` буквально нечего «добавлять».

**Варианты:**
- **(A)** `add-phase` остаётся как ярлык: «вернуть фазу из `skipped`
  обратно в `pending`» (т.е. `unskip`). Симметрично `skip-phase`.
- **(B)** Команды `add-phase` / `skip-phase` НЕ делаем в T097 вообще.
  Только `efactory project update --phase X --status Y`. Сахар
  отложим до T098, где manifest даст «реально гибкий скоуп»
  (если в манифесте отсутствует строка для фазы, она «не входит»).
- **(C)** Сделать оба ярлыка: `skip-phase` = `update --phase X
  --status skipped`, `add-phase` = `update --phase X --status pending`
  (с инвариантом «нельзя add активную фазу»).

**Предлагаемый дефолт:** **(C)** — даёт явный alias, читается лучше,
рискам не противоречит. Внутри CLI это тонкая обёртка над `update`.

---

#### 3. Допустимые транзишены и обратимость

В BACKLOG T097 явно прописаны три перехода: `pending → in_progress`
(`start`), `in_progress → done` (`complete`), `pending/in_progress →
skipped` (`skip`). Что с обратимостью?

Возможные «обратные» переходы:
- `done → in_progress` (reopen, например — переделать симуляцию).
- `skipped → pending` (передумали пропускать — собственно
  `add-phase` в смысле (C) выше).
- `done → pending` (полный сброс фазы).

**Варианты:**
- **(A)** Только три перехода вперёд из BACKLOG. Никакой обратимости.
  Если пользователь ошибся — пересоздаёт проект. Жёстко, просто,
  domain-инварианты минимальны.
- **(B)** `+ skipped → pending` (нужно для `add-phase` в семантике
  (C) #2). Остальное запрещено. Reopen после done считаем редким
  кейсом — отдельная задача потом.
- **(C)** Полная свобода переходов через CLI `update --phase X
  --status Y`: разрешены любые комбинации, в т.ч. произвольный
  reset. При этом `started_at`/`completed_at` пересчитываются по
  правилам (reset → обнуляются).

**Предлагаемый дефолт:** **(B)** — добавляем `skipped → pending`
ради `add-phase` (#2 ответ C), reopen done отложим до реального
кейса (запарковать в BACKLOG как новую задачу). Минимум инвариантов
для решения задачи, минимум места для ошибок.

---

#### 4. «Прыжки через фазы» — что делает derived status

Маппинг в § Functional Requirements — «последняя непрерывно-закрытая
фаза». То есть если `pcb done`, а `simulation pending`, то
`Project.status = idea` (chain прервалась на simulation).

**Альтернативы:**
- **(A)** Так и делаем (предложенный дефолт): chain прерывается,
  pcb «не зачитывается». Жёстко, но соответствует семантике CONCEPT
  §4.3 (где status — это уровень зрелости проекта целиком).
- **(B)** Брать **наибольшую закрытую** фазу — тогда `pcb done`
  при пропущенной simulation даст `Project.status =
  pcb_designed`. Гибче, но «pcb_designed без simulation» —
  странное состояние.

**Предлагаемый дефолт:** **(A)** — chain прерывается. И добавить
такой кейс в acceptance-tests, чтобы поведение было задокументировано
тестом.

---

#### 5. `@computed_field` (Pydantic v2) vs обычный `@property`

`@computed_field` встроится в `model_dump()` и схему модели, что
полезно для будущего YAML-сериализатора (T098). `@property` —
проще, не попадает в dump, но в T098 всё равно понадобится явно.

**Предлагаемый дефолт:** `@computed_field` — он по сути и
существует для именно такого кейса, нужен T098, ставим сразу.

---

#### 6. Identifier в Update CLI: `name` или `id`?

Текущий CRUD оперирует именами (т.к. в файловой системе папка
проекта = `<storage_root>/<name>`). UUID для пользователя не виден.

`update --name <new_name>` тогда конфликтует с identifier'ом.
Возможные варианты CLI-сигнатуры:

- **(A)** `efactory project update <current_name> --new-name <X>
  --phase Y --status Z`. Позиционный аргумент = текущее имя.
- **(B)** `efactory project update <name> --name <new_name> ...`.
  То же, но `--name` обозначает желаемое имя. Менее очевидно.
- **(C)** Identifier по UUID (`--id`). Не пользовательский путь.

**Предлагаемый дефолт:** **(A)** — позиционный `<current_name>`,
именованный `--new-name` для переименования. Чище и согласуется
с уже существующим `efactory project show <name>`.

---

#### 7. Атомарность множественных правок в одной команде

Поддерживаем ли `update mp --phase schematic --status done --phase
simulation --status in_progress` в одной команде (несколько
phase-апдейтов сразу) или одна команда = одна правка?

**Варианты:**
- **(A)** Только одна правка за вызов CLI: либо `--new-name`, либо
  одна пара `--phase --status`. Просто, понятно, validates
  тривиально.
- **(B)** Множественные `--phase/--status` пары в одной команде,
  применяются атомарно. Удобно для скриптов.

**Предлагаемый дефолт:** **(A)** — одна правка за вызов в T097.
Если позже окажется неудобно — расширим без break'а API. (Domain-
методы всё равно atomic; ограничение чисто CLI.)

---

#### 8. Формат `show` после T097

Что добавить в вывод `efactory project show <name>`? Текущий вывод
(минимальный) — id, name, path, status, created_at.

**Варианты:**
- **(A)** Добавить блок «Phases:» — таблица из шести строк с
  колонками `name | status | started | completed`. Datetime в
  ISO-8601 формате.
- **(B)** Только итоговый `Project.status` (derived) — компактно,
  но скрывает то, что фактически появилось.

**Предлагаемый дефолт:** **(A)** — без таблицы фаз `show` теряет
смысл; пользователь должен видеть, в каких фазах что происходит.

---

#### 9. Storage фаз в SQL: row-per-phase или JSON колонка?

T098 переводит SQL на роль индекса/cache, т.е. в долгую структура
SQL-таблиц не критична для бизнес-логики. Но в T097 SQL — ещё
primary, и структура важна.

**Варианты:**
- **(A)** Отдельная таблица `phases (project_id FK, name, status,
  started_at, completed_at, PK = (project_id, name))`. Шесть rows
  per project. Чистая 3НФ.
- **(B)** JSON-колонка `phases` в `projects` (SQLAlchemy `JSON`
  тип, SQLite поддерживает). Один read per project, проще
  миграция, но непригодно для SQL-запросов «найди все проекты с
  pcb=done» (для `list` — пока не нужно).
- **(C)** Шесть колонок в `projects` (`schematic_status`,
  `schematic_started_at`, ...). Денормализовано, тоже один read,
  но 6 × 3 = 18 колонок — некрасиво.

**Предлагаемый дефолт:** **(A)** — отдельная таблица. Чисто, проще
тестировать, миграция чуть-чуть сложнее, но autogenerate Alembic
справится. JSON-колонка казалась бы проще, но «один SQL-read per
project» — преждевременная оптимизация (нет проблемы N+1 на
6 строках).

---

#### 10. Поля `started_at`/`completed_at` фазы и поле `updated_at` проекта

Acceptance тестов и `show` пользуются `started_at` / `completed_at`
у фазы — мы их вводим. А что с `updated_at` у Project'а
(CONCEPT §4.3 manifest имеет `updated`)?

**Варианты:**
- **(A)** В T097 — НЕ вводим. `Project.updated_at` появится в T098
  вместе с manifest YAML, т.к. до манифеста это поле никуда не
  пишется и пользы от него ноль.
- **(B)** Ввести сразу, пусть будет. Использовать для CLI
  `show` («Last updated: ...»). Совсем небольшое изменение.

**Предлагаемый дефолт:** **(A)** — out of scope T097, см. § Out of
Scope. Полей и так много новых; YAGNI до T098.

---

### Resolved (с ответами)

Разработчик подтвердил все 10 предложенных дефолтов (2026-05-17).
Кратко:

1. **Mutability.** `Phase` — frozen Pydantic-VO; `Project` остаётся
   нефрозен (как сейчас), переходы реализуются через
   `Project.model_copy(update={'phases': ...})` или присваивание
   `phases` (тестируется в TDD).
2. **`add-phase` / `skip-phase` — CLI-shortcuts** над `update`:
   - `efactory project add-phase  <name> <phase>` ≡ `update <name>
     --phase <phase> --status pending`.
   - `efactory project skip-phase <name> <phase>` ≡ `update <name>
     --phase <phase> --status skipped`.
   Никакой отдельной логики, кроме маппинга на `update`.
3. **Допустимые транзишены:**
   - `pending → in_progress` (`Phase.start()`)
   - `in_progress → done` (`Phase.complete()`)
   - `pending | in_progress → skipped` (`Phase.skip()`)
   - `skipped → pending` (`Phase.unskip()`) — новый метод, см.
     Analyze 🔴 C1.
   - Любые другие переходы → `ValueError`.
4. **«Прыжки» через фазы.** `Project.status` берёт **последнюю
   непрерывно-закрытую** фазу с начала; chain прерывается на первой
   `pending | in_progress`. Закрепляется acceptance-тестом.
5. **`@computed_field`** (Pydantic v2) для `Project.status`. Войдёт
   в `model_dump`, готовит почву под T098 manifest.
6. **CLI sig:** `efactory project update <current_name> [--new-name
   <X>] [--phase <Y> --status <Z>]`. Позиционный аргумент =
   текущее имя. Mutex: `--new-name` несовместим с `--phase/--status`
   (см. Analyze 🟢 N4).
7. **Одна правка за вызов CLI.** Либо `--new-name`, либо одна пара
   `--phase/--status`. Расширим позже без break'а API при
   реальной необходимости.
8. **`show`** добавляет блок «Phases:» — таблица из 6 строк с
   колонками `name | status | started | completed`.
9. **SQL storage фаз — отдельная таблица `phases`**
   (`project_id` FK, `name`, `status`, `started_at`, `completed_at`;
   PK `(project_id, name)`). Backfill в Alembic upgrade —
   `INSERT OR IGNORE` (SQLite-specific, см. Analyze 🟡 W3).
10. **`Project.updated_at`** — out of scope T097, появится в T098
    вместе с manifest YAML.

---

## Analyze (заполняется Claude)

### 🔴 Critical (фиксим до начала implement)

#### C1. Domain `Phase` нуждается в четвёртом методе `unskip()`

Resolved #3(B) разрешает обратный переход `skipped → pending`, иначе
shortcut `add-phase` из #2(C) не имеет реализации в domain. В § 3
Functional Requirements был перечислен только `start / complete /
skip`. Добавляем:

- `Phase.unskip()` — валиден только при `status == skipped` →
  переводит в `pending`, **сбрасывает** `started_at = None` и
  `completed_at = None`. Резон сброса: фаза «как будто никогда
  не начиналась», следующий `start()` запишет свежий timestamp.
  Если бы `started_at` сохранился — pending с непустым `started_at`
  был бы противоречивым состоянием.
- Соответствующий unit-тест: skip(in_progress) → unskip() →
  start() — финальный объект имеет fresh `started_at`, прошлый
  start стёрт.

#### C2. CLI status-transitions: таблица what-is-allowed

Resolved #6 принимает CLI-сигнатуру `--phase <Y> --status <Z>`. Но
domain методы — атомарные транзишены, не «teleport в произвольный
status». Значит CLI обязан валидировать переход и бросать ошибку
на запрещённых.

Полная матрица (current ↓, target →):

|              | `pending`     | `in_progress` | `done`        | `skipped` |
|--------------|---------------|---------------|---------------|-----------|
| `pending`    | noop (или err)| `start()`     | **err**       | `skip()`  |
| `in_progress`| **err**       | noop (или err)| `complete()`  | `skip()`  |
| `done`       | **err**       | **err**       | noop (или err)| **err**   |
| `skipped`    | `unskip()`    | **err**       | **err**       | noop (или err)|

«noop» — текущий == target, в принципе можно тихо принять
(идемпотентность) или бросить «уже в этом статусе». Выбираем
**бросать ValueError** для noop тоже — пользователь явно просил
переход, ничего не произошло — это ошибка. CLI должна показать
понятное сообщение.

Реализация: в `UpdateProject` use case или в `Phase` появится
ровно одна точка диспетчеризации — функция/метод, который по
`(current_status, target_status)` возвращает соответствующий
domain-method-call или бросает `ValueError`. Обоснование: вся
матрица в одном месте, не размазана между CLI и domain.

#### C3. `ProjectRepository` порт обязан получить метод `update`

Сейчас порт (`src/ports/outbound/project_repository.py` — точное
имя сверим в implement-фазе) имеет `create / get_by_name /
list_all / delete_by_name`. Без `update(project: Project) -> None`
use case `UpdateProject` не сможет сохранить изменения.

В SQL adapter `update` выполнит:
- `UPDATE projects SET name = :name WHERE id = :id`;
- `UPDATE phases SET status=:s, started_at=:sa, completed_at=:ca
  WHERE project_id = :id AND name = :phase` — одной транзакцией.

Filesystem adapter (FileStore) в T097 не вызывается на update'е,
т.к. `path` не меняется (см. § 7 Out of Scope). Это явно
проверяется юнит-тестом (что FileStore не дёргается).

### 🟡 Warning (обсуждаем при implement, не блокируем)

#### W1. Backfill 6 phase-rows для существующих проектов: idempotency

Alembic upgrade должна делать `INSERT OR IGNORE INTO phases
(project_id, name, status) VALUES ..., ..., ...` для каждого
`(project_id, phase_name)` существующего проекта. Это SQLite-
specific синтаксис. У нас SQLite (`ADR T085`), для PostgreSQL
понадобится `ON CONFLICT DO NOTHING` — если когда-то добавим
PG, миграцию придётся patch'ить. Пока — не тратим время на
универсальный синтаксис.

#### W2. `Project.phases: tuple[Phase, ...]` фиксированной длины 6

Type `tuple[Phase, Phase, Phase, Phase, Phase, Phase]` — корректный
strict-type, но уродливый. Альтернатива: `tuple[Phase, ...]` +
runtime AfterValidator проверяет:
- длину == 6,
- порядок имён == список `PhaseName` в declaration order,
- нет дубликатов.

Идём по второму пути; конструктор `Project.with_default_phases(...)`
(или class method) собирает 6 фаз в каноническом порядке.

#### W3. Падение существующих тестов из-за изменения `ProjectStatus`

`ProjectStatus.CREATED` исчезает (заменяется на `idea`). Текущие
тесты `create/show/list/delete` сравнивают на `created`. После
T097 — на `idea` (default derived status у нового проекта).
Это **часть TDD outside-in работы**, не overhead — но diff в
`tests/` будет большой (десятки правок). Не пугаемся: каждая
правка тривиальна.

### 🟢 Note (к сведению)

#### N1. `@computed_field` + `frozen=False` Pydantic v2

Работает без вопросов: computed_field — read-only descriptor,
не зависит от mutability модели.

#### N2. CLI subcommands

Структура остаётся плоской: `efactory project [create | show | list
| delete | update | add-phase | skip-phase]`. Все три новых
subcommand'а — на одном уровне, не вложенные.

#### N3. Domain unit-тесты — без mock-ов

Phase.start/complete/skip/unskip — изолированные unit-тесты на
чистом domain, без участия persistence или CLI. Фиксировано в
`feedback_tdd.md` (mem0).

#### N4. Typer mutex для `--new-name` vs `--phase/--status`

Typer не имеет встроенного «mutually exclusive group». Реализуется
ручной проверкой в callback'е: если указано >1 семейства флагов
или ни одного — `typer.BadParameter`.

#### N5. `started_at` при `skip()` из `in_progress`

`skip()` из `in_progress`: `started_at` **сохраняется** (как
факт «фаза была начата»), `completed_at` не проставляется.
Граничный тест.

#### N6. Composition update

`src/composition/main.py` менять не придётся: `UpdateProject`
use case собирается из тех же портов, что уже есть в DI-композиции.
Только при добавлении нового метода `update` в порт — на стороне
SQL adapter появится новая реализация.
