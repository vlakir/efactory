# Container boundary — what lives inside the image, what stays on the host

**Этот документ — single source of truth для границы между образом
`efactory:linux` и host-машиной пользователя.** При расхождениях с
`specs/T110-containerization/spec.md` §5, `README.md` или
`DECISIONS.md` 2026-05-19 — **верит этот документ**; остальные правятся
ссылкой сюда.

История архитектурного решения и обоснование альтернатив остаются в
`DECISIONS.md` 2026-05-19 («Distribution: Linux Docker image») и в
spec T110; здесь — только актуальная карта.

---

## Принцип

> **Образ ≈ инструменты, volumes ≈ данные.**

Внутри образа — только то, что нужно для запуска тулчейна efactory:
KiCad, ngspice, FreeCAD, FEM-solver (Elmer + GetDP+Gmsh), Python
3.13 + uv, Claude Code CLI (T013, npm), runtime-агентский system
prompt в `/efactory/CLAUDE.md`, код efactory editable install. Всё,
что специфично для пользователя (проекты, библиотеки, персистентное
состояние приложений, секреты) — на хосте, монтируется в контейнер
volume mount'ами.

**MCP-серверы efactory не использует** — tool surface runtime-агента
= `Bash` + `efactory` CLI + filesystem (см. `DECISIONS.md` 2026-05-24
«Tool surface = Bash + efactory CLI + filesystem, не MCP»). Door для
конкретного stateful MCP (например, `freecad-mcp` T124) остаётся
открытой через separate task с явным обоснованием.

Контейнер **stateless**: `docker rm` оставляет на хосте только то,
что в host-volumes; ничего пользовательского не теряется.

---

## Что вынесено на host (volume mounts)

| Категория | Host | Container | Mode | Кто пишет |
|---|---|---|---|---|
| Проекты пользователя | `$HOME/efactory-projects/` | `/workspace/` | rw | пользователь + efactory |
| KiCad symbols | `$HOME/efactory-libs/symbols/` | `/usr/share/kicad/symbols/` | ro | bootstrap из `efactory-libs` image |
| KiCad footprints | `$HOME/efactory-libs/footprints/` | `/usr/share/kicad/footprints/` | ro | bootstrap |
| KiCad templates | `$HOME/efactory-libs/template/` | `/usr/share/kicad/template/` | ro | bootstrap |
| KiCad 3D models (опц., `--with-3dmodels`) | `$HOME/efactory-libs/3dmodels/` | `/usr/share/kicad/3dmodels/` | ro | bootstrap |
| KiCad persistent state | `$HOME/efactory-state/{config,cache,local}/` | `/opt/efactory/.{config,cache,local}/` | rw | KiCad GUI (settings, setup wizard) |
| **Claude Code state** | `$HOME/efactory-state/claude/` | `/efactory/.claude/` | rw | runtime-агент (auto-memory, settings, todos, projects, `.credentials.json` после первого `claude login`) |
| X11 socket | `/tmp/.X11-unix/` | `/tmp/.X11-unix/` | rw | X server |
| X11 auth cookie | `$XAUTHORITY` (или `~/.Xauthority`) | `/efactory/.Xauthority` | ro | host X session |
| Wayland socket (опц.) | `/run/user/$UID/wayland-0` | `/run/user/$UID/wayland-0` | rw | Wayland compositor |
| Пользовательские SPICE / custom libs | `$HOME/efactory-libs/custom/` | `/libs/custom/` | rw | пользователь |
| Editable source (dev, `--dev`) | `./src/` | `/opt/efactory/src/` | rw | разработчик efactory |

### Persistent index (внутри `/workspace`)

efactory кладёт `db.sqlite` (метаданные проектов, индекс) в
`/workspace/.efactory/db.sqlite` — не отдельный mount, а часть
projects-директории. Это значит: каждая проектная директория
«носит свой индекс с собой», переезжает с пользователем при
архивации / переносе на другую машину.

`EFACTORY_DATABASE_URL=sqlite+aiosqlite:///workspace/.efactory/db.sqlite`.

---

## Что НЕ выносим на host и почему

### `~/.claude/CLAUDE.md` разработчика (Гвидо)

**Не пробрасываем.** Это глобальные инструкции хостового
Claude Code, которым пользуется Гвидо для разработки efactory:
методика dreamteam, обращение «Владимир», mem0-настройки, tools-MCP.
Runtime-агент efactory — другая роль (РЭА-проектировщик, говорит
с конечным пользователем), у него **свой** системный prompt
(проектный `CLAUDE.md` в `/workspace/<project>/` или в образе).

Это явное решение из ADR 2026-05-19: «Изоляция runtime-агента от
dev-инстанса — закрыта бесплатно как побочный эффект Docker».

### mem0 (общая память Vladimir + Гвидо)

**Не пробрасываем.** mem0 хранит личные предпочтения Vladimir-а,
сведения о его инфраструктуре, обсуждения с Гвидо — это
**dev-knowledge**, не контекст efactory-агента. Конечный
пользователь efactory не знает про Гвидо и mem0.

### tools MCP (время, погода, журнал сессий)

**Не пробрасываем.** Это персональный MCP-сервер Vladimir-а на
`10.66.66.1:8084` для journaling-нужд разработки. Конечный
пользователь efactory не имеет к нему доступа и не должен иметь.

### Хостовые `~/.claude/projects/`, `~/.claude/todos/`, `~/.claude/settings.json`

**Не пробрасываем хостовые.** Вместо них — отдельная директория
`$HOME/efactory-state/claude/`, которая для runtime-агента
выглядит как чистый `$CLAUDE_CONFIG_DIR`. Это сохраняет
изоляцию (efactory не видит ни сессии Гвидо, ни наоборот).

### Хостовый `~/.claude/.credentials.json` разработчика

**Не пробрасываем.** Авторизация runtime-агента в контейнере — через
интерактивный `claude login` при первом запуске `efactory-up --agent`;
полученный `.credentials.json` сохраняется в
`$HOME/efactory-state/claude/.credentials.json` через тот же state-mount,
что и остальное состояние. Это даёт **полную изоляцию** между моим
хостовым Claude Code (dev-инстанс с глобальным `~/.claude/CLAUDE.md`,
mem0, tools MCP) и контейнерным runtime-агентом — у них разные
credentials, разные projects/sessions, разные системные prompt'ы.

### API-ключи провайдеров (OpenAI, Anthropic API key)

**Не пробрасываем автоматически.** Если пользователь хочет работать
без subscription (через usage-based billing), `efactory-up --agent`
поддерживает env-passthrough: `ANTHROPIC_API_KEY` с хоста подхватывается
в контейнер, если переменная задана. По умолчанию — не share'им
хостовые ключи (security).

### Хостовый Docker socket

**Не пробрасываем.** Контейнер не должен запускать другие контейнеры
(security; security boundary компрометируется при mount'е
`/var/run/docker.sock`).

---

## Container env vars

| Var | Значение | Назначение |
|---|---|---|
| `DISPLAY` | проброс с хоста | X11 target для GUI |
| `WAYLAND_DISPLAY` | проброс с хоста (опц.) | Wayland socket |
| `XDG_RUNTIME_DIR` | проброс с хоста (опц.) | Wayland socket location |
| `XAUTHORITY` | `/efactory/.Xauthority` | где X11-клиенты ищут auth cookie (user-agnostic) |
| `CLAUDE_CONFIG_DIR` | `/efactory/.claude` | где Claude Code ищет state (user-agnostic) |
| `EFACTORY_PROJECTS_ROOT` | `/workspace` | где efactory ищет проекты |
| `EFACTORY_LIBS_ROOT` | `/libs` | где efactory ищет custom libraries |
| `EFACTORY_DATABASE_URL` | `sqlite+aiosqlite:///workspace/.efactory/db.sqlite` | persistent index |
| `EFACTORY_VERSION` | `linux-X.Y.0` или `linux-latest@<sha-short>` | runtime introspection |
| `LANG` / `LC_ALL` / `LANGUAGE` | проброс с хоста (опц.) | локали |

---

## Жизненный цикл host-директорий

| Директория | Создаётся | Заполняется | Очищается |
|---|---|---|---|
| `$HOME/efactory-projects/` | `efactory-up` через `mkdir -p` | пользователь (через efactory или вручную) | вручную |
| `$HOME/efactory-libs/` | `efactory-up bootstrap_libs` | `docker cp` из `efactory-libs` image | `--update-libs` затирает + пересоздаёт |
| `$HOME/efactory-state/{config,cache,local}/` | `efactory-up` через `mkdir -p` | KiCad GUI | вручную (потеря KiCad settings) |
| `$HOME/efactory-state/claude/` | `efactory-up` через `mkdir -p` | runtime-агент Claude Code | вручную (потеря auto-memory и settings) |

Контейнер всегда `docker run --rm` — после выхода в нём ничего не
остаётся. Persistent state живёт только на хосте, в указанных
директориях.

---

## Где это применяется в коде

- **`efactory-up`** (корень репо) — реализует mount'ы из таблицы выше.
  Режимы: дефолтный (KiCad GUI), `--demo` / `--demo-freecad` (демо-
  фикстуры), `--headless` (CI/pytest), **`--agent` (runtime Claude
  Code, T013)** — последний отключает X11 pre-flight и libs mount,
  выделяет TTY (`-it`), запускает `claude --dangerously-skip-permissions`
  как `LAUNCH_BIN`.
- **Dockerfile** (корень репо) — создаёт mount-points
  (`/efactory/.claude`, `/efactory/.Xauthority`) с правами
  `0755 root:root`; runtime-юзер читает/пишет через mount.
  `ENV CLAUDE_CONFIG_DIR=/efactory/.claude`, `claude` CLI ставится
  через `npm install -g @anthropic-ai/claude-code@<version>` в final
  stage (T013). `/efactory/CLAUDE.md` — read-only system prompt
  runtime-агента (роль РЭА-проектировщика).
- **`Dockerfile.libs`** (корень репо) — собирает `efactory-libs`
  image, из которого `bootstrap_libs` копирует KiCad libraries.

## См. также

- `DECISIONS.md` 2026-05-19 «Distribution: Linux Docker image» —
  обоснование архитектуры дистрибутива.
- `DECISIONS.md` 2026-05-24 «Tool surface = Bash + efactory CLI +
  filesystem, не MCP» — почему в карте нет MCP overrides.
- `specs/T110-containerization/spec.md` — спецификация Phase 0.9
  Containerization, history Open questions и Analyze.
- `specs/T013-claude-code-runtime/spec.md` — спецификация runtime-
  агента в контейнере.
- `README.md` § «Запуск KiCad GUI из контейнера» / «Запуск runtime-
  агента» — пользовательский quick start.
