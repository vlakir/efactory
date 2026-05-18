## Spec: T010 — git init + structured session logging

**Статус:** Analyzed
**Дата создания:** 2026-05-18
**Связанные документы:**
- `CONCEPT.md` §4.5 (история сессий), §4.6 (команды управления
  проектом → запись событий), §10 (кроссплатформенность).
- `BACKLOG.md` → запись T010 (Фаза 1a — MVP-ядро).
- `specs/T099-decision-aggregate/spec.md` (DDR — отдельный канал
  фиксации; session log — параллельный, но про CLI-операции).

---

### 1. Overview

Открываем **Фазу 1a** двумя инфраструктурными правками:

1. **`git init` при `efactory project create`.** Каждый новый
   проект — git-репозиторий с initial commit, содержащим
   `project.yaml` (manifest). Это фиксирует «t0» проекта в VCS и
   готовит почву для последующих bridges, которые будут писать
   артефакты в подкаталоги (`schematic/`, `sim/`, …) — без VCS
   изменения становятся невидимыми.

2. **Structured session log** (`<storage_root>/sessions/<session_id>/log.jsonl`):
   каждая CLI-операция efactory пишет JSONL-запись `{ts, event,
   project, status, payload, error?}` в файл текущей сессии. Это
   диагностический канал для разработчика и фундамент для Phase 1b
   (чат-клиент будет писать туда же tool_use события).

Оба изменения **расширяют существующий domain-фундамент** (CreateProject,
все use cases) и не зависят от внешних тулчейнов (только `git` CLI
и stdlib `json`).

### 2. User Stories

- **«Что я вчера делал?»** Как разработчик, я хочу
  `tail -f ~/.local/share/efactory/sessions/<latest>/log.jsonl`,
  чтобы видеть хронологию вызовов efactory: какие проекты создавал,
  какие фазы менял, какие решения добавлял.
- **«Что пошло не так в проекте?»** Как разработчик, я открываю
  `git log` в каталоге проекта и вижу историю изменений
  manifest'а + markdown решений — нужна точка старта, отсюда git
  должен быть инициализирован сразу при `create`.
- **Готовность к LLM tool_use.** Как Phase 1b, я знаю, что
  session log уже работает; чат-клиенту останется только писать
  туда свои `tool.call` / `tool.result` события — формат уже
  фиксирован.
- **Отладка падений.** Когда `update` упал с
  `IndexPersistenceError`, запись в session log содержит
  `event=project.update, status=error, error.type=...,
  payload={...}` — этого достаточно для воспроизведения без
  расспроса пользователя.

### 3. Functional Requirements

#### Outbound ports (новые)

- **`GitRepository`** (Protocol) в
  `src/ports/outbound/git_repository.py`:
  ```python
  async def init_with_initial_commit(
      self, project_path: Path, message: str,
  ) -> None: ...
  ```
  - Инициализирует `git init` в `project_path`, делает
    `git add .` + `git commit -m <message>`.
  - Бросает `GitUnavailableError` если `git` нет на PATH.
  - Бросает `GitOperationError` при ненулевом exit code subprocess.

- **`SessionLogger`** (Protocol) в
  `src/ports/outbound/session_logger.py`:
  ```python
  async def log_event(
      self,
      event: str,
      *,
      status: SessionEventStatus,  # 'ok' | 'error'
      project: str | None = None,
      payload: dict[str, Any] | None = None,
      error: str | None = None,
  ) -> None: ...
  ```
  - Пишет JSONL-запись в текущий session-log файл.
  - Append-only, atomic at write boundary (одна запись = один
    `write` + newline; конкурентного доступа в Phase 1a нет).

#### Adapters (новые)

- **`SubprocessGitRepository`** (`adapters/outbound/git_subprocess/`):
  - `git init --quiet`, `git add -A`, `git commit -m <message>
    --quiet --no-gpg-sign` — три subprocess вызова.
  - `shutil.which('git')` для resolved path (S607).
  - Env clean: убираем `GIT_DIR`, `GIT_WORK_TREE` из subprocess env
    (защита от случайного inheritance из родителя).
  - Если git нет на PATH → `GitUnavailableError`.

- **`FilesystemJsonlSessionLogger`**
  (`adapters/outbound/session_jsonl/`):
  - Конструктор принимает `session_root: Path` и `session_id: str`.
  - `mkdir parents=True exist_ok=True` на первый write.
  - Каждый `log_event` → одна JSON-строка с trailing `\n`.
  - `ts` — `datetime.now(UTC).isoformat()` автоматически.
  - Сериализация через `json.dumps(ensure_ascii=False,
    separators=(',', ':'))` (компактно, кириллица читаемо).

#### Domain / Application

- НЕ ДОЛЖНА: появиться новая domain-сущность.  Session — пока
  инфраструктурное понятие (директория + id), без VO.
- ДОЛЖНА: `CreateProject` расширен пятым шагом:
  `create_dir → manifest.save → SQL upsert → git.init_with_initial_commit`.
  При `GitUnavailableError` — игнор + log в session
  (warning); проект всё равно создан.
  При `GitOperationError` — пробрасывается до CLI (exit 2,
  сообщение про возможные права/состояние FS).

#### CLI integration

- ДОЛЖНА: composition root генерирует `session_id` (формат
  `YYYYMMDD-HHMMSS-<rand6>`, ASCII, sortable) для каждого
  запуска CLI; создаёт `FilesystemJsonlSessionLogger(session_root,
  session_id)` и инжектит в `build_app`.
- ДОЛЖНА: каждая CLI-команда оборачивает вызов use case в:
  ```python
  try:
      result = ...use case...
      await session_logger.log_event('project.create', status='ok',
                                      project=name, payload={...})
  except SomeError as exc:
      await session_logger.log_event('project.create', status='error',
                                      project=name,
                                      error=f'{type(exc).__name__}: {exc}')
      raise
  ```
  Имена событий — `project.create`, `project.list`, `project.show`,
  `project.update`, `project.delete`, `project.reindex`,
  `decision.add`, `decision.list`, `decision.show`.

- НЕ ДОЛЖНА: добавляться отдельная CLI-команда. Логирование
  прозрачное.

#### Composition / Settings

- ДОЛЖНА: `Settings.session_root: Path` — новое поле,
  default factory `<storage_root>/sessions`. Можно override
  через `EFACTORY_SESSION_ROOT`.

### 4. Success Criteria

- TDD outside-in.
- 5-step gate зелёный.
- Coverage ≥ 80%.
- **Acceptance (git init).** После `efactory project create
  --name demo`:
  - `<storage_root>/demo/.git/` существует.
  - `git -C <storage_root>/demo log --oneline` показывает один
    коммит с известным сообщением, содержащим `demo`.
  - `git -C <storage_root>/demo ls-files` содержит как минимум
    `project.yaml`.
- **Acceptance (session log).** После любой CLI-команды:
  - `<session_root>/<session_id>/log.jsonl` существует.
  - Содержит ровно одну JSONL-запись для одиночной команды;
    каждая запись валидный JSON с полями `ts, event, status`
    (плюс опциональные `project`, `payload`, `error`).
  - При ошибке (например, `decision add` несуществующему
    проекту) запись содержит `status=error, error=...` и не
    обрывает поток вывода CLI.
- **Acceptance (git unavailable).** В окружении без `git`
  (PATH-stripped в тесте), `project create` корректно завершается
  exit 0; в session log запись `event=project.create, status=ok`
  плюс `event=git.init, status=error, error='git not found'`.
- **Кроссплатформенный namespace** для session_id: формат
  `YYYYMMDD-HHMMSS-<rand6>` (нет двоеточий — Windows-safe).

### 5. Key Entities

- **`GitRepository`** (Protocol) + **`SubprocessGitRepository`**
  (adapter).
- **`GitUnavailableError`** / **`GitOperationError`** — контрактные
  исключения порта.
- **`SessionLogger`** (Protocol) + **`SessionEventStatus`** (StrEnum:
  `ok | error`) + **`FilesystemJsonlSessionLogger`** (adapter).
- **`Settings.session_root: Path`** — composition wiring.
- **Имя события** — простая str-константа в CLI command (`'project.
  create'`, `'decision.add'`, …); enum пока не вводим, чтобы не
  таскать domain-список через слои.

### 6. Assumptions & Constraints

- Single-user CLI; one process per session_id → file-lock не нужен.
- `git` ≥ 2.20 (любой современный), кросс-платформенно (Linux/macOS/Windows).
- JSONL — append-only; ротация / cleanup старых сессий вне scope.
- Session_id генерируется в composition при старте process'а
  CLI. Можно переопределить через `EFACTORY_SESSION_ID` env
  (полезно для будущего chat-клиента и для тестов).
- `payload` логируется как есть; вызывающий следит, чтобы не
  попали секреты (в текущих CLI команд secrets нет — только имена
  проектов и фаз).

### 7. Out of Scope

- **Domain.Session** как aggregate (CONCEPT §4.5). Phase 1b с
  чат-клиентом — там session получит контекст разговора,
  `decisions: [...]`, `files_changed: [...]`, `commits: [...]`,
  `session_index.json` и т. п.
- **Ротация / cleanup session logs.** Сейчас логи копятся; cleanup
  — отдельная задача когда станет проблемой.
- **Per-project session split** (`<project>/sessions/<id>/`).
  Сейчас всё в `<storage_root>/sessions/`; per-project — когда
  появятся реальные изменения в проектах через bridges (Phase 1a
  T004+).
- **Git commit на каждом mutating use case.** Сейчас только initial
  commit при `create`. Auto-commit на `update` / `add-decision` —
  отдельная задача (рискованно: каждое изменение → коммит, шумно;
  обсудим после Phase 1a).
- **`.gitignore` template для проекта.** В initial commit ничего
  не игнорируем. Шаблон `.gitignore` (для artifact-папок типа
  `cache/`, `tmp/`) приедет с реальными bridges, когда будем
  знать что игнорировать.
- **Git author config.** Используем глобальный `git config user.name
  / user.email` пользователя. Если не настроен → git commit упадёт,
  CLI выдаст осмысленное сообщение про `git config --global`.
  Принудительно подменять author не хотим — это нарушит ожидания.
- **structlog / loguru dependency.** Adapter на stdlib json
  достаточно для Phase 1a. Если позже понадобится богатое
  логирование (correlation_id, contextual fields) — мигрируем.
- **MCP tool_use логирование.** Это Phase 1b/2 (когда появится
  чат-клиент); канал готов, наполнение позже.

---

### Clarify (заполняется после draft, перед implement)

#### Open questions

##### 1. Где живёт session log: глобально или per-project?

- **(A) Global `<storage_root>/sessions/<id>/log.jsonl`.** Все
  CLI-команды любого проекта пишут в один общий каталог. Простая
  модель.
- **(B) Per-project `<project_path>/sessions/<id>/log.jsonl`.**
  Команды без проекта (`list`, `reindex`) либо ничего не пишут,
  либо в отдельную «meta»-папку.
- **(C) Hybrid: project-scoped команды пишут в проект, остальное —
  в global.**

**Предлагаемый дефолт:** **(A) Global**. Pro: единый поток для
разработчика; CONCEPT §4.5 говорит про per-project session, но
это про chat-context (Phase 1b), не про CLI-операции. Per-project
split можно ввести позже, когда session обретёт ассоциацию с
конкретной фазой работы над проектом.

##### 2. Format session_id

- **(A) `YYYYMMDD-HHMMSS-<rand6>`** (например, `20260518-103015-a3f9c2`).
  ASCII, sortable, Windows-safe (нет `:`), low collision-risk.
- **(B) `session_<INC>` глобальный счётчик.** Чище для CONCEPT,
  но требует state file для последнего номера; race в single-user
  не страшна, но сложнее.
- **(C) UUID4.** Максимальная уникальность, но не sortable, не
  читается человеком.

**Предлагаемый дефолт:** **(A)**. CONCEPT format `session_001` —
прекрасен для отображения, но нужен глобальный счётчик; (A) проще
и даёт sortable id для `ls -la <session_root>`.

##### 3. Session_id reuse внутри одного `efactory ...` запуска

Каждая CLI-команда — отдельный процесс (Typer не интерактивный
shell). Значит каждый `efactory project create ...` получит новый
session_id и новую папку `log.jsonl` с одной записью.

- **(A) Принять.** Одна запись на сессию — норма для CLI-режима.
  Группировка по человеческой «сессии работы» — задача внешнего
  pipe / `EFACTORY_SESSION_ID`.
- **(B) Поддержать `EFACTORY_SESSION_ID` env override.** Если
  переменная задана — переиспользуем. Иначе генерируем.

**Предлагаемый дефолт:** **(B)** — стоит 3 строк кода, помогает
тестам и будущему chat-клиенту.

##### 4. Что писать в `payload`?

Минимум: имена аргументов CLI (`name`, `phase`, `status`,
`new_name`, `title`, ...). Максимум: полные DTO use case'ов.

**Предлагаемый дефолт:** **минимум** — только то, что нужно для
воспроизведения команды. Полные DTO (с UUIDs, datetime'ами) —
шумно и pollute log.

##### 5. Initial commit message format

- **(A) Фиксированный**: `efactory: create project <name>`.
- **(B) Шаблонизируемый** (`--commit-message`).

**Предлагаемый дефолт:** **(A)**. Шаблонизация — гибкость без
пользы в Phase 1a; стандартный формат полезен для grep.

##### 6. `git commit --no-gpg-sign` обязателен?

Если у пользователя `commit.gpgsign = true`, при отсутствии
настроенного GPG ключа на чистой машине commit упадёт. Initial
commit при `project create` не должен зависеть от GPG.

- **(A) Всегда `--no-gpg-sign`.** Прагматично.
- **(B) Использовать `GIT_CONFIG_PARAMETERS='commit.gpgsign=false'`
  через subprocess env.** Чище, но многословно.
- **(C) Не подавлять.** Если упало — пользователь сам разберётся.

**Предлагаемый дефолт:** **(A)** + warning в session log если
GPG signing был запрошен и отключён. Initial commit — internal
operation, не должен требовать ручной настройки.

##### 7. CLI оборачивание: декоратор или явный try/except?

Логирование во всех CLI-командах — повторяющийся pattern. Можно
вынести в декоратор `@logged_event('project.create')`.

- **(A) Явный try/except в каждой команде.** Boilerplate, но
  читаемо.
- **(B) Декоратор + context manager.** DRY, но скрытая логика.

**Предлагаемый дефолт:** **(B)** — небольшой helper
`async def _log_command(logger, event, project, payload, fn)` или
`@logged` декоратор. ~30 строк boilerplate сэкономлено.

##### 8. Что делать при сбое самого `session_logger.log_event`?

Если запись в log упала (disk full, permission denied) — это
infrastructure проблема. Прерывать ли основной CLI flow?

**Предлагаемый дефолт:** **best-effort** — log failure пишется в
stderr (`echo: failed to write session log: ...`), но CLI
завершается нормально. Логирование не должно мешать основной
работе. (Аналогично syslog/journald на Linux.)

##### 9. Phasing

- **(A) Один phase.** Всё вместе.
- **(B) Два phase:** (1) Ports + adapters; (2) Application/CLI
  wiring + e2e.

**Предлагаемый дефолт:** **(A)** — задача компактнее T098/T099,
два phase — overkill.

##### 10. Тест git init без реального git

Acceptance требует subprocess `git`. На CI / в чистом окружении
git может отсутствовать.

**Предлагаемый дефолт:** **smoke** в integration тесте —
`pytest.importorskip`-аналог через `shutil.which('git')`, skip если
git нет. Unit-тесты adapter'а с monkeypatched `shutil.which` /
`subprocess.run` покрывают логику без реального git.

---

### Resolved

Разработчик подтвердил все 10 предложенных дефолтов (2026-05-18).
Кратко:

1. **Session log** — **(A) global** `<storage_root>/sessions/<id>/log.jsonl`.
   Per-project — отложено в Phase 1b вместе с chat-context'ом
   сессии.
2. **Session_id format** — **(A)** `YYYYMMDD-HHMMSS-<rand6>`.
   ASCII / sortable / Windows-safe. `<rand6>` — `secrets.token_hex(3)`.
3. **Session reuse** — **(B)** default = новый id; есть
   `EFACTORY_SESSION_ID` env override для chat-клиента и тестов.
4. **`payload`** — минимум. Только аргументы CLI, без полных DTO.
5. **Initial commit message** — **(A)** фиксированный
   `efactory: create project <name>`.
6. **`--no-gpg-sign`** — **(A)** всегда при initial commit.
   Документируем как internal operation.
7. **CLI session-log** — **(B)** helper / декоратор. Минимизация
   boilerplate.
8. **Log write failure** — best-effort. stderr warning, основной
   CLI flow не прерывается. Логирование — не критичный путь.
9. **Phasing** — **(A) один phase**. Реализация компактнее
   T098/T099.
10. **git тесты** — skip если `git` нет на PATH (integration);
    unit-тесты adapter'а с monkeypatched subprocess.

---

### Analyze

#### 🔴 Critical

##### C1. Порядок git init относительно остальных шагов CreateProject

После T098 порядок: `create_dir → manifest.save → SQL upsert`.
Куда вставить git init?

- **(A) После всего** (`...→ git.init`). Логично: коммит снимает
  состояние «как только что создано», включая `project.yaml`.
- **(B) После manifest.save, до SQL.** Если SQL упал
  (`IndexPersistenceError`), git коммит уже сделан — repo есть.
  Но реestric: SQL fail сейчас — partial failure (manifest=truth,
  SQL stale, `reindex` recovers); git init после ничего не
  ломает, но добавляет один лишний коммит к partial-failure
  manifest'у.

**Резолюция:** **(A) после всего**. Git init = «фиксация
успешного результата». Если SQL упал — git init не делается;
после `reindex` пользователь может сделать `git init` руками
или мы сделаем это автоматически в future задаче. Trade-off:
очень редкий случай partial failure без git — приемлемо.

##### C2. `git config user.name / user.email` не настроен

`git commit` упадёт с «Please tell me who you are». Это блокер
для свежего bootstrap'а на чистой машине.

- **(A) Hard fail.** Сообщение «настрой `git config --global
  user.name 'X' && user.email 'Y'`». Корректно, но раздражает
  при первом запуске.
- **(B) Передавать temp identity через env**
  (`GIT_AUTHOR_NAME=efactory`, etc). Локально override без
  глобального config.
- **(C) Skip git init если user.* не настроен** (warning в session
  log).

**Резолюция:** **(B)** — `GIT_AUTHOR_NAME=efactory`,
`GIT_AUTHOR_EMAIL=efactory@localhost`, аналогично `GIT_COMMITTER_*`,
только для initial commit. `git log` покажет автора `efactory
<efactory@localhost>` — явно «системный» коммит. Пользовательские
коммиты потом будут от его `git config`. Не подменяем глобально;
override только в subprocess env.

##### C3. Session_id collision

Формат `YYYYMMDD-HHMMSS-rand6` — collision вероятность
6 hex chars = 1/16M на ту же секунду. Single-user CLI — не
проблема. Документируем.

#### 🟡 Warning

##### W1. Существующий e2e `test_create_project_end_to_end` (T085)

Этот тест проверяет SQL запись после `project create`. После
T010 в FS появятся `.git/` и `sessions/<id>/log.jsonl`. Тест
не сломается (он проверяет наличие папки + SQL row), но e2e
output может содержать дополнительные строки (если CLI печатает
session_id или что-то). Решение: CLI новых строк не печатает;
session log пишется молча. Тест без правок.

##### W2. Тестовая изоляция session log

Каждый тест в `tests/e2e/` использует tmp_path → `session_root`
тоже tmp_path. Между тестами нет shared state. Безопасно.

##### W3. `--no-gpg-sign` vs `commit.gpgsign = true` user config

`git commit --no-gpg-sign` перебивает config. Хорошо для
init commit. Pre-commit hook proxy на signature — нерелевантно
для initial commit (он создаёт первый коммит).

#### 🟢 Note

##### N1. Helper `_log_command` сигнатура

```python
async def _log_command(
    logger: SessionLogger,
    event: str,
    project: str | None,
    payload: dict | None,
    fn: Callable[[], Awaitable[T]],
) -> T:
    try:
        result = await fn()
    except Exception as exc:
        await logger.log_event(event, status=SessionEventStatus.ERROR,
                                project=project, payload=payload,
                                error=f'{type(exc).__name__}: {exc}')
        raise
    await logger.log_event(event, status=SessionEventStatus.OK,
                            project=project, payload=payload)
    return result
```

Один helper для всех CLI-команд. Без декоратора, потому что
Typer commands sync а внутри `asyncio.run` — декоратор поверх
sync не работает чисто. Через context-manager (`async with`) —
тоже сложно из-за `asyncio.run` boundary. Простая функция
вызывается внутри `asyncio.run(...)`.

##### N2. Build session_id helper

В `composition/main.py`:
```python
def _make_session_id() -> str:
    if env_id := os.environ.get('EFACTORY_SESSION_ID'):
        return env_id
    ts = datetime.now(UTC).strftime('%Y%m%d-%H%M%S')
    return f'{ts}-{secrets.token_hex(3)}'
```

##### N3. Имена событий

`project.create`, `project.list`, `project.show`,
`project.update`, `project.delete`, `project.reindex`,
`decision.add`, `decision.list`, `decision.show`. Совпадает с
CLI subcommand path; легко grep'ать в логах.

##### N4. JSONL format

Одна запись:
```json
{"ts":"2026-05-18T10:15:00.123456+00:00","event":"project.create","status":"ok","project":"demo","payload":{"name":"demo"}}
```

`status=error` добавляет `error: "ClassName: message"`.

##### N5. Logger: не используем stdlib `logging`

stdlib `logging` — для diagnostic stderr (например, INFO/WARNING
в composition). Session log — отдельный, structured, JSONL,
append-only. Это разные каналы, не путаем.

##### N6. Adapter dir naming

- `adapters/outbound/git_subprocess/` для GitRepository.
- `adapters/outbound/session_jsonl/` для SessionLogger.

Оба добавляются в import-linter independence contract.

##### N7. Settings.session_root

```python
session_root: Path = Field(
    default_factory=lambda: _xdg_data_home() / 'efactory' / 'sessions',
)
```

Independent от `projects_root`: можно положить в другое место (для
очистки лога без удаления проектов).

##### N8. Session log при `create` — порядок

Поток `efactory project create --name demo`:
1. `session_id` сгенерирован.
2. CLI command вызывает `create_project` use case.
3. Use case делает: dir → manifest → SQL upsert → git init.
4. CLI после успеха зовёт `log_event('project.create', ok, project='demo', payload={name:'demo'})`.

То есть session log записывается после успеха use case. Если
use case упал — log_event пишется с `status=error` в catch.
Файл `sessions/<id>/log.jsonl` создаётся at-first-write.

##### N9. `git unavailable` log entry

Если `GitUnavailableError` — CreateProject ловит, логирует
`event=git.init, status=error, error='git not found'` через
session_logger и продолжает (проект создан без VCS). CLI команда
дополнительно логирует `event=project.create, status=ok`.

Соответственно `CreateProject` сам зовёт `session_logger.log_event`
для git failure — нарушение слоистости? Альтернатива: возвращать
дополнительный outcome flag и логировать в CLI. Решение: пробросить
warning через возвращаемое значение `CreateProject` (например,
`CreateProjectResult { project, git_initialized: bool }`). CLI
видит флаг и логирует отдельным событием. Это сохраняет
application слой чистым от инфраструктуры логирования.

##### N10. Composition зависимости

`build_cli_app`:
- `settings = Settings()` — содержит session_root.
- `session_id = _make_session_id()`.
- `session_logger = FilesystemJsonlSessionLogger(settings.session_root, session_id)`.
- `git_repo = SubprocessGitRepository()`.
- `build_app(..., session_logger=..., git_repo=...)`.
