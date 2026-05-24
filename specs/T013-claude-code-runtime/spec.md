# Spec: T013 — Claude Code runtime в контейнере

**Статус:** Analyzed
**Дата создания:** 2026-05-24
**Связанные документы:**
- `docs/container-boundary.md` (SSOT границы образ/host — обновляется этой задачей)
- `DECISIONS.md` 2026-05-19 «Distribution: Linux Docker image»
- `DECISIONS.md` (новый ADR этой задачи) «Tool surface = Bash + efactory CLI + filesystem, не MCP»
- `BACKLOG.md` → Phase 1b (старая формулировка T013 «Регистрация efactory MCP-серверов» — заменяется этой спекой)

---

## 1. Overview

Установить Claude Code CLI внутри образа `efactory:linux`, обеспечить
авторизацию через interactive `claude login` изнутри контейнера
(credentials персистятся на host через уже готовый mount T140), завести
новый режим запуска `efactory-up --agent` с минимальным stub `CLAUDE.md`
в роли РЭА-проектировщика. Это **нулевая задача Phase 1b** — без неё
runtime-агента в контейнере не существует, и последующие T014
(slash-команды) / T016 (project context) не имеют поверхности для
интеграции.

Сопутствующее архитектурное решение: efactory **не использует MCP** —
tool surface для runtime-агента — `Bash` + `efactory` CLI + filesystem
(Read/Edit/Write). Обоснование в новом ADR `DECISIONS.md` 2026-05-24
«Tool surface = Bash + efactory CLI + filesystem, не MCP» (см. §
Resolved-7 ниже).

## 2. User Stories

- **Как конечный пользователь efactory**, я хочу запустить
  `./efactory-up --agent` после fresh `docker pull`, авторизоваться
  один раз при первом запуске (через интерактивный OAuth-flow), и
  оказаться в TUI-чате с runtime-агентом, понимающим контекст
  efactory.
- **Как пользователь, переустанавливающий контейнер** (`docker rm` +
  fresh `docker run` через `efactory-up`), я хочу **не повторять
  login** — auth должен переживать пересоздание контейнера, потому
  что credentials лежат на host через mount.
- **Как разработчик efactory (Гвидо/Vladimir)**, я хочу **полную
  изоляцию** между моим хостовым Claude Code (с dev-инструкциями,
  mem0, tools MCP) и контейнерным runtime-агентом — у них разные
  системные prompt'ы, разные credentials (после первого login),
  разные projects/sessions/history.

## 3. Functional Requirements

### Образ `efactory:linux`

- **ДОЛЖНА** содержать `claude` CLI, установленный через
  `npm install -g @anthropic-ai/claude-code` (с подходящей pinned
  версией; см. §6).
- **ДОЛЖНА** содержать Node.js + npm в final stage Dockerfile
  (runtime-зависимость `claude`).
- **ДОЛЖНА** выставлять `ENV CLAUDE_CONFIG_DIR=/efactory/.claude` в
  final stage.
- **ДОЛЖНА** содержать stub `CLAUDE.md` в `/efactory/CLAUDE.md` —
  read-only system prompt runtime-агента (5-10 строк: роль
  РЭА-проектировщика, доступные инструменты, тон общения с
  конечным пользователем).
- **ДОЛЖНА** создавать mount-points `/efactory/.claude/` и
  `/workspace/` (если не созданы T140) с правами `0755 root:root`;
  runtime-юзер читает/пишет через host-mount.
- **НЕ ДОЛЖНА** содержать MCP-сервера efactory (closed ADR'ом — см.
  §Resolved-7).
- **НЕ ДОЛЖНА** содержать кастомные slash-команды (T014) и
  SessionStart hooks (T016).

### `efactory-up`

- **ДОЛЖНА** поддерживать новый флаг `--agent`, который:
  - переключает `LAUNCH_BIN` с `kicad` на `claude`;
  - пропускает pre-flight для X11 (`DISPLAY`, `xhost`, `XAUTHORITY`)
    — агент работает в TTY, не GUI;
  - НЕ mount'ит X11 socket / Xauthority / 3dmodels libs (не нужны
    для агента);
  - mount'ит `STATE_DIR/claude:/efactory/.claude:rw` (как сейчас) и
    `PROJECTS_DIR:/workspace:rw`;
  - mount'ит KiCad symbol/footprint/template libs (агент может их
    использовать через `kicad-cli` / Python sexp-фасады).
- **ДОЛЖНА** запускать `claude --dangerously-skip-permissions`
  (Vladimir clarify-6: безопасность обеспечивается scope mount'ов,
  не interactive prompts).
- **МОЖЕТ** пробрасывать `ANTHROPIC_API_KEY` из host env, если
  переменная задана (opt-out для пользователей без subscription).
- **НЕ ДОЛЖНА** пробрасывать хостовый `~/.claude/.credentials.json`
  (изоляция dev/runtime: контейнерный агент — отдельный субъект).
- **НЕ ДОЛЖНА** совмещаться с `--demo` / `--demo-freecad` (взаимно-
  исключающие режимы, как сейчас между демо-режимами).

### Документация

- **ДОЛЖНА** обновить `docs/container-boundary.md`:
  - убрать строку `Claude Code auth (Phase 1b, T013)` (overlay
    отменён в пользу login-изнутри);
  - убрать строку `MCP overrides (dev, опц.)` (MCP не используем);
  - снять «aspirational» статус с `Claude Code CLI внутри образа` и
    `CLAUDE_CONFIG_DIR=/efactory/.claude` (стр. 23, 119) — это
    реализуется этой задачей;
  - добавить пункт «runtime-агент = `efactory-up --agent`» в раздел
    «Где это применяется в коде».
- **ДОЛЖНА** добавить новый ADR в `DECISIONS.md` 2026-05-24:
  «Tool surface = Bash + efactory CLI + filesystem, не MCP».
- **ДОЛЖНА** обновить README.md: новая секция «Запуск runtime-агента»
  с однострочной инструкцией.

## 4. Success Criteria

- **CLI installed.** `docker run --rm efactory:linux claude --version`
  возвращает версию Claude Code (без error).
- **First-time login.** `./efactory-up --agent` на машине без
  `$HOME/efactory-state/claude/.credentials.json` запускает
  интерактивный OAuth-flow; после login TUI чата открывается.
- **Persistent auth.** После `docker rm` (любой контейнер уже завершился
  через `--rm`) повторный `./efactory-up --agent` открывает TUI **без
  повторного login** — credentials прочитаны из mount'а.
- **End-to-end tool-use.** Внутри TUI prompt «выведи содержимое
  /workspace» возвращает листинг (Bash tool call), **без request
  разрешения** (`--dangerously-skip-permissions` активен).
- **System prompt active.** Агент в первом ответе упоминает свою роль
  («РЭА-проектировщик» / «efactory») — подтверждает, что `/efactory/
  CLAUDE.md` подхватывается.
- **Image size.** `efactory:linux` ≤ ~7.5 GB после T013 (текущий 7.31 GB
  + ~80-150 MB на Node.js + npm + Claude Code). Жёсткой границы нет
  (CONCEPT §13 «потолок 6 GB» уже формально превышен после T112 —
  Vladimir подтвердил приемлемость 2026-05-20), но прирост документируется.
- **Pre-push gates.** `ruff check . && ruff format --check . && mypy src
  && pytest` — все зелёные. Coverage не падает ниже baseline 86.16%
  (T140).
- **Backwards compatibility.** Текущие режимы `efactory-up` (без флагов
  → KiCad, `--demo`, `--demo-freecad`, `--headless`) работают как
  раньше — никаких breaking changes.

## 5. Key Entities

- **`claude` CLI** — Node-based приложение от Anthropic, ставится через
  `npm install -g @anthropic-ai/claude-code`. Точка входа в runtime-
  агента.
- **`/efactory/.claude/`** — `CLAUDE_CONFIG_DIR`, mount'ится на host
  `$HOME/efactory-state/claude/` (rw, mount готов из T140). Содержит:
  - `.credentials.json` (после первого login),
  - `settings.json` (опционально, пользователь может править),
  - `projects/`, `todos/`, `sessions/`, `history.jsonl`,
  - auto-memory runtime-агента (если/когда заведёт).
- **`/efactory/CLAUDE.md`** — read-only stub system prompt в образе.
  Содержимое (~10 строк):
  - Роль: РЭА-проектировщик efactory.
  - Доступные инструменты: `efactory` CLI (когда T014 поднимется),
    `kicad-cli`, `ngspice`, `freecadcmd`, `ElmerSolver`, Python use
    cases через `uv run`, базовые Bash/Read/Write/Edit.
  - Тон: помогаешь пользователю спроектировать РЭА-устройство от
    схемы до production package.
  - Ограничения: проекты живут в `/workspace`, custom libs — в
    `/libs/custom`.
- **`efactory-up --agent`** — новый режим скрипта-обёртки. `LAUNCH_BIN
  = claude`, CWD внутри контейнера = `/workspace`.

## 6. Assumptions & Constraints

- **Subscription как основной auth-path.** Vladimir и большинство
  пользователей будут логиниться через subscription (OAuth flow).
  `ANTHROPIC_API_KEY` остаётся как opt-out (env-passthrough), но не
  default path.
- **Concurrent sessions допустимы.** Один subscription — хостовый
  Claude Code (dev) + контейнерный runtime-агент могут работать
  параллельно (Vladimir clarify-5). Rate limit делится между ними,
  это принятое ограничение.
- **Node.js runtime — runtime-зависимость.** Принимаем +~80 MB к
  образу. Альтернативные пути установки (curl-installer, статический
  бинарь) Vladimir отверг в пользу канонического `npm` (clarify-2).
- **Pinned версия Claude Code.** Будем pin'ить конкретную версию
  (через `npm install -g @anthropic-ai/claude-code@X.Y.Z`) ради
  репродуцируемости — иначе `docker build` будет недетерминирован.
  Текущая stable версия определится во время implementation
  (`npm view @anthropic-ai/claude-code version` на момент работы).
  Bumping версии — отдельный коммит с явным намерением.
- **OAuth-flow в контейнере требует браузер на хосте.** Claude Code
  OAuth обычно использует device-flow (показывает URL + код,
  пользователь открывает в любом браузере). Это работает изнутри
  headless-контейнера. Если Anthropic использует другой механизм
  (например, requires localhost callback) — это всплывёт на smoke и
  потребует уточнения.

## 7. Out of Scope

- **MCP-сервера** (любого вида: наши efactory-собственные, сторонние
  типа kicad-mcp-pro). Закрыто новым ADR `DECISIONS.md` 2026-05-24.
  Возврат к MCP — только для конкретного stateful use case
  (например, freecad-mcp в Tech Debt T124).
- **Кастомные slash-команды efactory** (`/project create`, `/sim run`,
  `/export-production`) — T014.
- **Dynamic project context / SessionStart hooks** — T016.
- **Полный system prompt РЭА-агента.** В T013 — только stub
  (5-10 строк). Полноценный системный prompt с детальным
  описанием workflow / методики / acceptance criteria для
  пользователя — отдельная задача после T014 + T016 (когда понятно,
  какие инструменты у агента действительно есть).
- **Permissions allowlist через `settings.json`.** Используем
  `--dangerously-skip-permissions` (Vladimir clarify-6). Если в
  будущем возникнет реальный security risk (например, агент
  triggered `rm -rf` на `/workspace`) — refinement allowlist'а как
  отдельная задача.
- **Multi-arch образ (arm64 для Apple Silicon).** Phase Cross-platform,
  отдельные задачи T116/T117.
- **Эмпирический probe OAuth-portability host→container.** Отменён
  выбором (b) в clarify-1 — credentials не копируются с host'а, а
  создаются login'ом изнутри контейнера.
- **GitHub token / Anthropic API key bundled provisioning.**
  ANTHROPIC_API_KEY поддерживается через env-passthrough, но не
  hardcoded и не provisioned автоматически.

---

## Clarify (заполняется Claude)

### Open questions

- (нет — все вопросы получили ответы Vladimir-а 2026-05-24)

### Resolved (с ответами)

1. **OAuth-token portability** — host→container mount credentials
   **отменён**. Выбран путь (b): interactive `claude login` изнутри
   контейнера; credentials сохраняются в `/efactory/.claude/.credentials.json`
   и персистятся через mount T140. Дополнительный fallback —
   `ANTHROPIC_API_KEY` env-passthrough для пользователей без
   subscription.
2. **Источник Claude Code CLI** — `npm install -g @anthropic-ai/claude-code`
   с pin версии. Принимаем +~80 MB на Node.js в образе.
3. **System prompt контейнерного агента** — в T013 пишем минимальный
   stub `/efactory/CLAUDE.md` (5-10 строк: роль + инструменты +
   ограничения). Полноценный prompt — отдельная задача после T014/T016.
4. **Entrypoint** — `efactory-up --agent` (вариант a). Не делаем
   breaking change `efactory-up без флагов → агент`; KiCad GUI
   остаётся дефолтом (как сейчас).
5. **Concurrent host vs container sessions** — допустимо как
   ограничение (вариант b). Не блокер.
6. **Permissions mode** — `--dangerously-skip-permissions`.
   Безопасность обеспечивается scope mount'ов (`/workspace`,
   `/libs/custom`), не interactive prompts.
7. **MCP overrides в `container-boundary.md` стр. 47** — убираем.
   Заодно зафиксируем общее решение «MCP не используем» новым ADR
   `DECISIONS.md` 2026-05-24 «Tool surface = Bash + efactory CLI +
   filesystem, не MCP» (отдельный артефакт этой задачи).
8. **Acceptance** — полный: интерактивный TUI запускается через
   `efactory-up --agent`, виден чат, делается реальный tool-use
   call (например, `ls /workspace`) → работает.

---

## Analyze (заполняется Claude)

Прошёлся по спеке + factual probe текущего образа (`docker run --rm
efactory:linux bash -c "id; pwd; ls -ld /efactory /workspace"`). Нашёл
следующее:

**Контекст образа (важно для нескольких пунктов ниже):**
- USER `ubuntu` (UID 1000), HOME `/opt/efactory`, default CWD
  `/opt/efactory`.
- `/efactory/` — root:root, 0755 (mount-point для `.claude/`).
- `/workspace/` — root:root, 0755 (mount-point для проектов).
- Контейнер **не root** — это важно для `--dangerously-skip-permissions`
  (см. issue ниже).

### 🔴 Critical

1. **OAuth-flow в headless-контейнере — самый большой риск задачи.**
   Спека §6 утверждает «Claude Code OAuth обычно использует device-flow
   (URL+код)... работает изнутри headless». **Я этого не верифицировал
   фактически.** Если на самом деле flow требует `localhost callback`
   (`http://127.0.0.1:PORT/callback` open in browser), то изнутри
   контейнера это сломается: браузер на хосте не сможет достучаться
   до порта внутри `--rm` контейнера без явного `-p` proxy.

   **Mitigation для implementation:** первый шаг — `docker run -it
   --rm efactory:linux-test claude login` (после установки CLI),
   эмпирически проверить, что показывает CLI и какой URL генерируется.
   Если localhost-callback — добавить `-p 127.0.0.1:PORT:PORT` в
   `efactory-up --agent` (порт CLI генерирует случайно? либо фикс?).
   Если фикс не реализуем — fallback на `ANTHROPIC_API_KEY` (env-
   passthrough) становится **обязательным** для смок-завершения, не
   опциональным как сейчас в спеке.

2. **System prompt CLAUDE.md — путь подгрузки нужно верифицировать.**
   Claude Code канонически подгружает `CLAUDE.md` из CWD + parent-trail
   + `~/.claude/CLAUDE.md` (user-level). У нас в контейнере:
   - CWD будет `/workspace` (с `-w /workspace` в `efactory-up --agent`),
   - parent-trail: `/workspace` → `/` (sibling `/efactory` **не на
     пути**),
   - `$HOME/.claude/CLAUDE.md` = `/opt/efactory/.claude/CLAUDE.md` —
     но `CLAUDE_CONFIG_DIR=/efactory/.claude` (override), и этот mount
     приходит **с хоста пустым** при первом запуске → user-level
     CLAUDE.md теряется.

   **Варианты решения** (выбрать на implementation):
   - **(a)** Положить `/CLAUDE.md` в корень образа (root + read-only).
     CWD=`/workspace`, parent-trail найдёт. Простой, но «грязный».
   - **(b)** Поставить `-w /efactory` (CWD внутри `/efactory/`), `/efactory/CLAUDE.md`
     найдётся, агент пишет в `/workspace` явными путями. Минус:
     не intuitive для агента.
   - **(c)** Использовать флаг `claude --append-system-prompt "..."`
     или `--system-prompt-file=/efactory/CLAUDE.md` (если CLI это
     поддерживает — нужно проверить `claude --help`). Самое чистое.

   **Action:** в начале implementation `claude --help` → определить
   подходящий флаг; иначе fallback (a).

3. **`--dangerously-skip-permissions` имеет ограничения.** В upstream
   Claude Code этот флаг **отказывается работать под root**. У нас
   USER `ubuntu` (UID 1000) — это OK. Но если кто-то запустит
   `efactory-up --agent` через `sudo` (или env override `--user 0:0`),
   флаг будет отвергнут CLI и команда упадёт. Не блокер — но **в
   `efactory-up --agent` стоит добавить explicit check** `[[ $(id -u)
   != 0 ]]` с fail-сообщением.

### 🟡 Warning

4. **Совместимость флагов в `efactory-up`.** Текущий
   pre-flight проверяет `DISPLAY` / `XAUTHORITY` / `xhost` безусловно
   (стр. 220-224). Для `--agent` режима эти проверки нужно **пропустить**
   (агент в TTY, не GUI). Также `--agent` нужно сделать
   взаимоисключающим с `--demo` / `--demo-freecad` / `--headless` —
   `--headless` особенно (он запускает pytest, не launch_bin).
   **Add check:** `(( AGENT_MODE )) && ( DEMO_MODE || DEMO_FREECAD_MODE
   || HEADLESS ) → fail`.

5. **TTY/stdin allocation для `claude` TUI.** `docker run --rm
   efactory:linux claude` без `-it` не выделит TTY → TUI развалится.
   Текущий `efactory-up` в финальном `exec docker run --rm ...` **не
   указывает `-it`** (это OK для GUI, где X11 — а не TTY). Для
   `--agent` режима нужно добавить `-it`. **Add:** `(( AGENT_MODE ))
   && DOCKER_TTY_ARGS=(-it)`.

6. **Pinned версия Claude Code в Dockerfile.** Спека §6 фиксирует
   pin, но не указывает **где именно хранится номер версии** —
   inline в Dockerfile (`@X.Y.Z`)? ARG в начале файла (как
   `FREECAD_VERSION` в T112)? Я бы выбрал ARG — единообразно с
   FREECAD_VERSION, легче bump'ать одной правкой.

7. **Stub `CLAUDE.md` упоминает `efactory` CLI.** Но T014 (efactory
   CLI и slash-команды) ещё не сделан — CLI ещё не существует.
   Если в stub'е написать «у тебя есть `efactory` CLI» — агент
   попытается его вызвать и получит `command not found`. **Stub
   должен ограничиться тем, что реально доступно в `efactory:linux`
   *сейчас***: `kicad-cli`, `ngspice`, `freecadcmd`, `ElmerSolver`,
   `getdp`, `gmsh`, `uv run python -m efactory.*` через editable
   install. После T014 — пересмотр stub'а.

### 🟢 Note

8. **Image size impact.** Спека §4 указывает «≤ ~7.5 GB после T013».
   Реальный замер: Node.js LTS + npm ≈ 50 MB, `@anthropic-ai/claude-
   code` (CLI + deps) — порядка 30-50 MB. Итого +80-100 MB поверх
   7.31 GB → ~7.4 GB. В пределах ожидания, фиксируем после `docker
   build`.

9. **Coverage threshold (86.16%) ничего не меняется.** T013 —
   Dockerfile + bash + docs, никакого нового Python кода в `src/`.
   Pytest прогон останется на 587+6 тестах. Coverage не изменится.
   В Success Criteria указано «не падает ниже» — это формально
   соблюдается без активных усилий.

10. **MCP overrides — нужно убрать не только из container-boundary.md.**
    Запись `~/efactory-mcp.d/` → `/etc/efactory/mcp.d/` ro может быть
    также упомянута в spec T110 §5. **Action:** при правке
    container-boundary.md grep'нуть «mcp» по всему `docs/` и `specs/`
    — удалить остаточные упоминания или явно указать «закрыто T013».

---

### Verdict

**Critical issues 1-3** имеют чёткие mitigation, прописываемые в
implementation flow. **Critical issue 1 (OAuth flow)** требует
эмпирического probe **первым шагом** — если flow несовместим с
headless-контейнером, scope расширится (`ANTHROPIC_API_KEY` становится
mandatory, или нужен port-proxy через `efactory-up`). Эту развилку
обсуждаем по факту probe.

Спека готова к implementation. Сначала Critical 1 → потом всё остальное
поэтапно.
