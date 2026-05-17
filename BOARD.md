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

- **T086** — [closed 2026-05-17, PR #7] Обновить `README.md`
  «Быстрый старт» под Walking Skeleton CLI
  (`uv run efactory project create --name <name>` + `.secrets`-блок
  с `EFACTORY_PROJECTS_ROOT` / `EFACTORY_DATABASE_URL`). Запаркован
  follow-up T087 на нормальные default'ы Settings. Уточнена ошибочная
  запись в Retrospective `[0.1.0]` про Kùzu ADR (статус был снят
  ещё в T085). Запись о изменениях — в `CHANGELOG.md` `[Unreleased]`.
- **T087** — [closed 2026-05-17, PR #8] Дать `Settings`
  (`composition/settings.py`) разумные default'ы для `projects_root`
  / `database_url` (XDG-стиль). Composition root автоматически
  создаёт storage-каталоги до запуска Alembic-миграций. README
  «Быстрый старт» упрощён обратно до двух строчек. По TDD: 3 unit-теста
  Settings (default / XDG override / env override) + integration-тест
  composition без env. Запись о изменениях — в `CHANGELOG.md`
  `[Unreleased]`.
- **T088** — [closed 2026-05-17, PR #9] Second use case
  `ListProjects` — проверка hexagonal-фундамента на втором сквозном
  срезе. Расширение `MetadataRepository.list_all() -> list[Project]`,
  `application.list_projects`, SQLAlchemy-реализация (сортировка
  `created_at DESC`), CLI `efactory project list` (TSV-вывод,
  «No projects found.» на пустом). По TDD outside-in: 2 e2e + 3 unit
  с fake-портом + 2 integration. 23 passed, coverage 98.84%. Запись
  о изменениях — в `CHANGELOG.md` `[Unreleased]`.
- **T089** — [closed 2026-05-17, PR current] Third use case
  `GetProject` (по имени). Расширение
  `MetadataRepository.get_by_name(name) -> Project | None`,
  `application.get_project` + `ProjectNotFoundError`, SQLAlchemy
  `select().where(name).limit(1)`, CLI `efactory project show
  --name <name>` (multi-line вывод метаданных; при отсутствии —
  stderr + `exit_code=1`). По TDD outside-in: 2 e2e (happy + unknown)
  + 2 unit (found / raises) + 2 integration. 29 passed, coverage
  99.02%. Запись о изменениях — в `CHANGELOG.md` `[Unreleased]`.

