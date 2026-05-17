# Spec: T096 — Расширение domain'а: выбор следующего шага

**Статус:** Done
**Дата создания:** 2026-05-17
**Связанные документы:** `CONCEPT.md` §4 (Project как базовая
сущность), `[0.2.0]` Retrospective в `CHANGELOG.md` (источник),
`DECISIONS.md` → ADR `2026-05-17 — Domain expansion direction: D
(Phase VO → Manifest primary → Decision aggregate)`.

---

## 1. Overview

После 0.2.0 у нас закрыт минимальный CRUD по `domain.Project`
(Create / List / Show / Delete). Архитектурно фундамент подтвердил
работоспособность, но имеет два неисследованных угла:

1. **Нет Update use case** — единственное поле, которое могло бы
   меняться (`status`), сейчас имеет ровно одно значение
   `CREATED`. Это значит, путь «изменить состояние агрегата →
   commit» в hexagonal-стеке ни разу не пройден.
2. **Нет второго агрегата** — domain содержит только `Project`.
   Не проверено: composition root с несколькими репозиториями,
   взаимодействие агрегатов, growth архитектуры с увеличением
   количества доменных сущностей.

Цель T096 — **выбрать дизайн-направление** для расширения, записать
его в `DECISIONS.md` как ADR, и декомпозировать на отдельные
T-задачи. **Реализация — out of scope T096.**

## 2. Сценарии использования (рассматриваемых направлений)

### Направление A: новый агрегат `Decision` (журнал решений)

CONCEPT.md §4.4 — Design Decision Record. Каждое значимое решение
проекта фиксируется как markdown в `decisions/` плюс краткая запись
в `project.yaml`. CRUD на Decision — реальная функциональность из
концепта.

- `efactory decision add --project <name> --title "Triode mode"`
  → создаёт `decisions/D001_triode_mode.md` + запись в manifest.
- `efactory decision list --project <name>` → таблица решений.
- `efactory decision show --project <name> --id D001`.

### Направление B: `Phase` как embedded value object внутри `Project` + Update use case

CONCEPT.md §4.1, §4.3 — phases-driven scope. Фазы (schematic,
simulation, pcb, magnetics, enclosure, documentation) — каждая
со статусом `pending | in_progress | done | skipped`. Статусы
меняются по жизни проекта.

- `efactory project update --name <name> --phase pcb --status in_progress`
  → реальный Update на агрегат (меняется поле phases collection).
- `efactory project add-phase --name <name> --phase pcb`
  (добавление новой фазы в already-existing project; см. §4.1).
- `efactory project skip-phase --name <name> --phase enclosure`.

Phase — embedded value object внутри Project aggregate (нет
независимого lifecycle, нет global uniqueness). Расширяет
`domain.Project` collection'ом фаз.

### Направление C: `Manifest` (project.yaml) как outbound адаптер

CONCEPT.md §4.3 — каждый Project имеет manifest `project.yaml`.
Сейчас persistence у Project'а только SQL; YAML-сериализация в
проектный каталог — отдельный outbound адаптер (`ProjectManifestRepository`).

- При `project create` — генерируется `project.yaml` рядом со
  схемами.
- При `project show` — manifest читается рядом с SQL (dual-source с
  consistency check, или manifest становится primary, SQL — индекс).
- Update use case появляется естественно: «обновить ТТХ»,
  «добавить decision-reference», «изменить статус фазы» — всё
  через manifest.

### Направление D: гибрид

Например, **B → A → C** (Phase first для writable cases, потом
Decision для проверки второго агрегата, потом Manifest для full
CONCEPT-соответствия).

## 3. Functional Requirements

T096 — discovery / design, поэтому FR относятся к артефактам, а не
к функциональности кода:

- ДОЛЖНА: выбрать одно из 4 направлений (A / B / C / D) или
  предложить альтернативу.
- ДОЛЖНА: записать выбор в `DECISIONS.md` как ADR с рассмотренными
  альтернативами и обоснованием отвержения.
- ДОЛЖНА: декомпозировать выбранное направление на отдельные
  T-задачи в `BACKLOG.md` (с acceptance criteria каждой).
- НЕ ДОЛЖНА: содержать реализацию (даже минимальную) — реализация
  идёт отдельными T-задачами.

## 4. Success Criteria

- ADR в `DECISIONS.md` написан, минимум 4 альтернативы рассмотрены
  с обоснованиями.
- Декомпозиция в `BACKLOG.md` — минимум 1 новая T-задача с
  acceptance.
- Spec обновлён до статуса Done с финальным выбором (заполнена
  секция Clarify).

## 5. Key Entities (рассматриваемые)

- **`Project`** (текущий aggregate root) — может расширяться
  (направление B) или оставаться неизменным (A, C).
- **`Decision`** — новый aggregate (направление A).
  Поля: id (`D001`-style), title, date, status (proposed /
  accepted / rejected), summary, rationale, evidence, session.
  Lifecycle: создаётся, может менять status (Update use case).
- **`Phase`** — embedded value object (направление B).
  Поля: name (enum: schematic / simulation / pcb / magnetics /
  enclosure / documentation), status (pending / in_progress / done
  / skipped), started_at, completed_at.
- **`Manifest`** — YAML-сериализация Project'а (направление C).
  Не aggregate, а format. Outbound адаптер.

## 6. Assumptions & Constraints

- Архитектура hexagonal уже фиксирована (ADR `T085`).
- TDD outside-in для всех новых задач (`feedback_tdd.md`).
- DI-композиция ручная, новый репозиторий регистрируется в
  `composition/main.py`.
- import-linter контракты не должны нарушаться при росте domain.
- Каждая новая T-задача — отдельный PR, правило T093 закрытия
  применяется.

## 7. Out of Scope

- **Реализация** выбранного направления — отдельные T-задачи.
- **Component / Schematic / Library** агрегаты — это фазы 1a/2
  дорожной карты, требует KiCad-интеграции; слишком крупный шаг.
- **Session / LLM-агрегаты** — требует MCP/LLM интеграции (фаза 1b).
- **Multi-board** (§4.3 `boards:` в manifest) — следующий уровень
  сложности после single-board Project.

---

## Clarify (для Владимира)

### Открытые вопросы

1. **Какое направление приоритетно для тебя?** Моя рекомендация
   снизу — но domain-экспертиза твоя.

2. **Direction A (Decision)** — насколько важно «второй агрегат
   ради второго агрегата»? Decision — концептуально-важная
   сущность, но без полноценного workflow (без интеграции с
   симуляцией / решениями ИИ) выглядит как «голый CRUD».

3. **Direction B (Phase + Update)** — фазы из §4.1 / §4.3 явно
   завязаны на feature-cuts (`/project new --phases ...`,
   `add-phase` / `skip-phase`). Логично сделать Phase управление
   ДО любых других расширений domain'а, потому что от текущей
   фазы зависит, какие папки создавать (`pcb/` vs `p2p/`,
   `enclosure/` vs нет).

   Под-вопросы:
   - **Phase как enum или как полноценный VO?** Enum проще,
     VO даёт расширяемость (например, `tags`, `priority`).
   - **Статусы фазы из концепта:** `pending | in_progress | done |
     skipped`. Принимаем как есть, или нужны промежуточные
     (`blocked`, `review`)?
   - **Default набор фаз** при создании проекта — из концепта
     `--phases all` = `{schematic, simulation, pcb, magnetics,
     enclosure, documentation}`. Создаём папки только под
     активные фазы или все сразу?

4. **Direction C (Manifest)** — это фундаментальная развилка.
   Сейчас Project живёт только в SQL. В концепте manifest = source
   of truth, портативный (можно переслать папку проекта).
   Вопрос: **SQL — это индекс (для list / search), а Manifest —
   primary storage?** Или **SQL — primary, manifest — экспорт?**
   Это влияет на consistency model.

5. **Direction D (гибрид)** — если согласен с моей рекомендацией
   B → C → A, нужно зафиксировать порядок и пометить в BACKLOG
   как зависимости.

6. **Update use case на `project.status`** — рассматривать
   отдельно? Сейчас `ProjectStatus` — single value (CREATED).
   В концепте §4.3 — `status: idea | schematic | simulated |
   pcb_designed | magnetics_done | enclosure_done | production_ready`.
   Можно ввести семантические статусы независимо от phases.
   Или статус — derived field от phases (если все фазы done →
   `production_ready`)?

7. **Acceptance для декомпозированных задач** — мы пишем
   acceptance в `BACKLOG.md` сразу при декомпозиции, или ждём
   взятия в работу?

### Моя рекомендация (для дискуссии)

**Направление D, в порядке B → C → A.**

- **B сначала**: Phase + Update use case — закроет gap «нет
  writable-цели», задаст паттерн для Update в hexagonal-стеке,
  концептуально-фундаментальное (phases-driven scope в §4.1).
- **C вторым**: Manifest как outbound адаптер — синхронизирует
  состояние со СВЯЗНОЙ концепцией портативного проекта (§4.1
  Принципы → «Портативность»); даёт второй outbound адаптер на
  том же агрегате (проверяет dual-repo persistence).
- **A третьим**: Decision как новый агрегат — проверяет рост
  domain'а с несколькими aggregate roots; concept-богатый
  domain'ный объект.

Альтернатива «A сначала» (рекомендация Гвидо ранее в обсуждении
T096) отвергнута: Decision без Phase / Manifest workflow — это
изолированная фича, не на главном пути жизненного цикла Project'а.

### Resolved (с ответами Владимира)

1. **Направление: D** (гибрид, порядок B → C → A).
   Обоснование принято — закрываем gap «нет writable-цели» (B),
   синхронизируем с принципом портативности концепта (C), затем
   проверяем рост domain'а вторым агрегатом (A).
2. **A (Decision)** — последним, как «второй агрегат». Окей.
3. **B (Phase + Update)** — первым.
4. **C (Manifest)** — `project.yaml` = **primary storage**;
   SQL = индекс / cache для быстрого `list` / `search`. Полная
   реиндексация SQL возможна перечитыванием всех manifest'ов.
   Это согласовано с CONCEPT §4.1 «Портативность» — можно
   заархивировать папку проекта, перенести, расшарить; SQL —
   локальный артефакт окружения, не source of truth.
5. **D order** — B → C → A зафиксирован.
6. **Project.status** — **derived field** от phases. Stored
   `ProjectStatus.CREATED` снимается, status вычисляется как
   computed property на агрегате. Полный enum из CONCEPT §4.3:
   `idea | schematic | simulated | pcb_designed | magnetics_done |
   enclosure_done | production_ready`. Mapping (фиксируется в T097):
   - все phases pending → `idea`;
   - schematic done, остальное pending → `schematic`;
   - schematic + simulation done → `simulated`;
   - + pcb done → `pcb_designed`;
   - + magnetics done → `magnetics_done`;
   - + enclosure done → `enclosure_done`;
   - + documentation done → `production_ready`.
   Фазы со status=`skipped` не блокируют переход
   (skipped считается «закрытой» для derivation).
7. **Acceptance в BACKLOG сразу** при декомпозиции — пишем при
   создании T-задачи, по методике («без acceptance не зрелая для
   взятия»).

**Под-вопросы (после первого ответа):**

- **Phase: полноценный VO** (не просто enum + scalar status).
  Поля: `name: PhaseName (enum)`, `status: PhaseStatus (pending |
  in_progress | done | skipped)`, `started_at: datetime | None`,
  `completed_at: datetime | None`. Методы: `start()`, `complete()`,
  `skip()` — управляют timestamps + invariants (нельзя complete не
  started, нельзя re-start completed, и т.д.). Phase = embedded
  inside Project aggregate (нет independent lifecycle).
- **Default phases при `project create`:** все 6 (schematic,
  simulation, pcb, magnetics, enclosure, documentation) со
  status=`pending`. Ненужные фазы конвертируются в `skipped`
  через `efactory project skip-phase` (тоже из концепта §4.1).
- **Status mapping** — принят в виде, описанном выше.

---

## Analyze

T096 — discovery, реализации нет. Analyze применим к декомпозиции
и к самому ADR.

- 🟡 **Refactor существующих миграций.** Текущая `create_projects_table`
  миграция содержит колонку `status`. После T097 (status derived):
  колонка либо удаляется (новая миграция), либо остаётся как
  denormalized cache (на T098 это будет уточнено: при primary=Manifest,
  SQL — индекс, и status в SQL — denormalized read-only поле).
  Помечаем как «ожидаемое отягощение T097 / T098» — не блокер.

- 🟡 **Backward compatibility для существующих projects на чистом
  SQL.** Сейчас проекты `efactory project create` создают только
  каталог + SQL row, без manifest. После T098 manifest становится
  primary — нужна migration «существующие SQL-only проекты получают
  manifest». Фиксирую как явный пункт acceptance T098.

- 🟡 **Phase domain coupling с CONCEPT phases.** PhaseName enum
  фиксирует список фаз — добавление новой требует domain-изменения.
  Альтернатива — string-based с whitelist в Settings. По CONCEPT
  фазы стабильные (6 штук), не open-ended → enum. Зафиксировано
  в T097.

- 🟢 **Параллельный fallback CLI:** `project show` после T098 читает
  из manifest; `project list` — из SQL. UX-расхождение возможно
  если SQL out-of-sync с manifest'ами (например, manifest вручную
  отредактирован, индекс не пересчитан). T098 acceptance включает:
  `efactory project reindex` команда для перестроения SQL из
  manifest'ов.

- 🟢 **Decision aggregate (T099) — interaction с manifest.** В
  концепте §4.3 manifest содержит `decisions:` секцию со ссылками
  на файлы `decisions/D###_*.md`. То есть Decision имеет
  dual-storage: markdown файл (детали) + reference в manifest
  (summary, evidence). T099 спроектирует адаптеры под эту dual-
  storage; T098 (Manifest) должен заранее поддержать optional
  `decisions:` секцию в schema.
