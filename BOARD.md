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

- **T007** — [taken 2026-05-18] Transformer / load SPICE model
  library. Domain.TransformerModel + TransformerKind (opt | load).
  Outbound port TransformerLibrary + filesystem adapter (parallel
  to TubeModelLibrary, не generalize). CLI `efactory transformer
  list / show`. data/models/transformers/{opt,load}/ с 5 example
  моделей: OPT_SE_5K_8, OPT_PP_6K6_8, SPEAKER_8OHM (с резонансом),
  SPEAKER_8OHM_RES (чистый R), SPEAKER_4OHM. Settings.transformer_*
  + user overlay. ngspice smoke — T008. Спека (Draft, 6 Clarify) —
  `specs/T007-transformer-models/spec.md`. Ветка
  `T007-transformer-models`.

## Done

- **T006** — [closed 2026-05-18, PR #24] Tube SPICE model library
  (framework). Domain.SpiceModel (id, name, tube_type, source,
  file_path, subckt_pins) + enums TubeType / ModelSource.
  Outbound port TubeModelLibrary + FilesystemTubeModelLibrary
  adapter (scan data/models/tubes/{koren,ayumi,duncan,custom}/
  *.{lib,inc,cir}, парсинг .SUBCKT header + tube_type detection
  через header override или pin-count fallback; id = uppercase
  filename stem). Конвертер convert_ayumi_to_ngspice (`^ → **`)
  применяется на read_subckt для Ayumi-источника. Settings.
  tube_library_root + EFACTORY_TUBE_LIBRARY_ROOT env override.
  pyproject force-include для data/models — wheel содержит
  built-in модели. CLI subapp efactory tube list/show. 2 generic
  example models (GENERIC_TRIODE koren + GENERIC_PENTODE ayumi).
  299 passed, coverage 94.04%. Spec Analyzed
  (`specs/T006-tube-library/spec.md`). Out of scope явно: upstream
  скачивание (T002), русские лампы (заполняет bootstrap или
  пользователь), ngspice smoke (T008).

- **T010** — [closed 2026-05-18, PR #23] Открытие Фазы 1a (MVP-
  ядро): `git init` + initial commit при `project create` +
  structured session log (`<session_root>/<session_id>/log.jsonl`).
  Новые outbound порты `GitRepository` (subprocess adapter c env-
  override AUTHOR/COMMITTER и `--no-gpg-sign` — initial commit
  независим от глобального git config) и `SessionLogger`
  (filesystem JSONL, best-effort, `ensure_ascii=False`). `Settings.
  session_root` + `EFACTORY_SESSION_ID` env override (для группировки
  CLI команд в одну сессию — пригодится chat-клиенту Phase 1b).
  `CreateProjectResult{project, git_initialized}` — application
  слой не зависит от логирования (N9). CLI helper `_log_command[T]`
  обернул все 9 команд (project.* + decision.*). 259 passed,
  coverage 94.53%. Spec Analyzed
  (`specs/T010-git-init-and-logging/spec.md`).


<!-- Закрытые задачи, ждущие переноса в CHANGELOG.md при следующем
     релизе или значимой точке. После переноса — очищаем. -->

<!-- Записи T093, T095, T096, T097, T098, T099 перенесены в
     CHANGELOG.md → [0.3.0] release-PR. -->
