# Board

Лёгкая Kanban-альтернатива на одном markdown-файле: три колонки
(To Do / Doing / Done) под git, без внешних сервисов и инструментов.

## Соотношение с другими файлами

- `BACKLOG.md` — длинная очередь идей и побочных находок. Сюда падает
  «потом подумаем», «не сейчас». Парковка scope.
- `BOARD.md` (этот файл) — активный рабочий поток. Задачи, которые мы
  уже взяли или собираемся брать в ближайшее время.
- `specs/T<NNN>-*/spec.md` — куда вырастает крупная задача из BOARD, если
  она оказывается фичей >1 дня работы.

Жизненный цикл задачи: идея в `BACKLOG.md` → созрела → переезжает в
`To Do` здесь → берётся в работу (`Doing`) → закрывается (`Done`) →
после релиза переходит в `CHANGELOG.md` (запись обязательно содержит
T-ID), отсюда удаляется. **`CHANGELOG.md` — единственное persistent-
хранилище T-ID завершённых задач**, без него правило «ID не
переиспользуется» сломается.

## Формат задачи

Каждая задача — `- **T<NNN>** — <короткое описание>`. ID присваивается
при создании: новый = `max(существующих T-ID в BOARD.md, BACKLOG.md и
CHANGELOG.md) + 1`. ID никогда не переиспользуется. ID общий для
`BOARD.md` и `BACKLOG.md` — при перетекании задачи между ними
сохраняется; после релиза задача попадает в `CHANGELOG.md` с тем же
T-ID, что гарантирует уникальность номеров между релизами.

Имя ветки: `T<NNN>-<slug>` (без namespace типа `fixes/` / `feature/` —
ID уже даёт идентификацию). Имя PR: `T<NNN>: <title>`. Спецификация
крупной фичи: `specs/T<NNN>-<slug>/spec.md`.

По вкусу можно добавлять:

- метку даты взятия,
- ссылку на спеку,
- имя ветки.

Пример:

```
- **T<NNN>** — Превью постов в Telegram
  (`specs/T<NNN>-telegram-preview/`, ветка `T<NNN>-telegram-preview`).
```

---

## To Do

<!-- Готово к взятию. Очередь FIFO по умолчанию, можно поднимать
     приоритетное наверх. -->

<!-- Записи задач в формате `- **T<NNN>** — описание`. См. раздел
     «Формат задачи» выше. -->

## Doing

<!-- В работе прямо сейчас. Держим короткой: максимум 1-2 задачи на
     разработчика, иначе теряется фокус (классическое WIP-limit
     правило из Kanban). -->

## Done

<!-- Закрытые задачи, ждущие переноса в CHANGELOG.md при следующем
     релизе или значимой точке. После переноса — очищаем. -->

- **T099** — [closed 2026-05-17, PR #20] Decision как новый
  aggregate root (CONCEPT §4.4). Реализация фазы D направления D
  из ADR T096. `Decision` frozen-VO + `DecisionRef` + `DecisionId`
  (Annotated D### / D1000+) + `DecisionStatus` enum
  (proposed | accepted | rejected). Dual-storage: markdown
  `decisions/D###_<slug>.md` (truth, CONCEPT §4.4 шаблон) +
  reference в `project.yaml → decisions:` (index). Outbound port
  `DecisionRepository` + filesystem markdown adapter (atomic
  write, anchor-парсинг, NFKD slugify). Use cases
  `AddDecision / ListDecisions / GetDecision` + новый
  `DecisionPersistenceError` (N3). Расширение `ReindexProjects`:
  optional `decision_repo` пересобирает `Project.decisions`
  из реальных markdown файлов. CLI subapp `efactory decision
  add / list / show`. ID auto-increment per project. 238 passed,
  coverage 94.18%. Spec Analyzed
  (`specs/T099-decision-aggregate/spec.md`). Manual-edit
  acceptance (ручной `D001_*.md` → reindex → list) — e2e
  тест.
- **T098** — [closed 2026-05-17, PR #19] Manifest (`project.yaml`)
  как primary storage; SQL = индекс / cache. Реализация фазы C
  направления D (ADR T096). Outbound port
  `ProjectManifestRepository` + filesystem YAML adapter (PyYAML
  safe_load, atomic os.replace, exclude path для портативности,
  schema_version=1). Write pattern: manifest first → SQL upsert
  (idempotent save C1). Read pattern: `show` из manifest, `list`
  из SQL. Новые application errors: `IndexPersistenceError` (C2
  partial failure), `ProjectManifestMissingError` (desync).
  `ReindexProjects` use case + `ReindexSummary {indexed,
  bootstrapped, orphans, failed}` работает в обе стороны
  (manifest→SQL primary + SQL→manifest bootstrap для pre-T098).
  CLI `efactory project reindex [--storage-root]
  [--remove-orphans]`. SQL миграция `cc78f2ee52bb`
  (projects.updated_at + backfill = created_at). 176 passed,
  coverage 96.92%. Spec Analyzed
  (`specs/T098-manifest-primary/spec.md`). Portability и
  partial-failure acceptance — e2e на tmp_path.
- **T097** — [closed 2026-05-17, PR #18] Phase VO + derived
  `Project.status` + Update use case. Реализация фазы B направления
  D из ADR T096. Domain: `Phase` frozen-VO (6 фаз × методы
  start/complete/skip/unskip + transitioned_to dispatcher); `Project.
  status` = `@computed_field` derived от phases; `ProjectStatus` ×7
  CONCEPT §4.3. Application: `UpdateProject` use case + `Metadata
  Repository.update`. Persistence: SQL `phases` table + Alembic
  миграция с backfill для existing проектов. CLI: `efactory project
  update / add-phase / skip-phase` + `show` с таблицей фаз. 130
  passed, coverage 99.58%. Спека Analyzed
  (`specs/T097-phase-vo/spec.md`). Соглашения по pyproject (typer
  immutable-calls) и type-ignore (computed_field + property)
  согласованы в процессе PR — оба зафиксированы в auto-memory как
  reusable feedback для T098/T099.
- **T096** — [closed 2026-05-17, PR #17] Расширение domain'а:
  выбрано направление **D** (Phase VO + derived status + Update
  → Manifest primary → Decision aggregate). ADR в `DECISIONS.md`
  с 6 альтернативами. Декомпозиция в `BACKLOG.md`: T097, T098,
  T099 (depends-chain T097 → T098 → T099). Spec
  `specs/T096-domain-expansion/spec.md` (Done со smoke/analyze).
- **T095** — [closed 2026-05-17, PR #16] Auto-install pre-commit
  pre-push hook через hatchling custom build hook (`hatch_build.py`).
  После `git clone && uv sync` хук установлен автоматически.
  Acceptance: ✓ (auto-install после `uv sync`, README обновлён,
  e2e восстановления hook'а из ничего, ADR в `DECISIONS.md`,
  spec Done). Сайд-эффект: S603 в общий `ruff.lint.ignore`
  (первый subprocess в проекте, false-positive).
- **T093** — [closed 2026-05-17, PR #15] BOARD-запись закрытия
  задачи: выбран подход (а) — closing-правка BOARD отдельным
  финальным commit'ом **после** `gh pr create`, в том же PR.
  Зафиксировано в `CLAUDE.md` § Git workflow → подраздел
  «Closing-правка `BOARD: Doing → Done`». Подход (б) (placeholder
  + fix-up в следующем PR) отвергнут как причина повторявшейся
  ×6 в `[0.2.0]` помарки.

