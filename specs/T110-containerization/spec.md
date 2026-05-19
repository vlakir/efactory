# Spec: T110 — Containerization (Phase 0.9 efactory)

**Статус:** Draft
**Дата создания:** 2026-05-19
**Покрываемые задачи:** T110 (базовый Dockerfile), T111 (KiCad GUI passthrough),
T112 (FreeCAD CLI + GUI), T113 (FEM-solver pilot + integration), T114
(`efactory-up` wrapper), T115 (CI + GHCR publish), T120 (cleanup
AppImage-detection в `platform_layer`).
**Связанные документы:**
- `DECISIONS.md` 2026-05-19 «Distribution: Linux Docker image с полным
  стеком, включая GUI»
- `DECISIONS.md` 2026-05-19 «Magnetic field verification: Linux-native
  FEM-solver (Elmer / GetDP), FEMM как legacy»
- `DECISIONS.md` 2026-05-15 «MCP-обвязка готовых инструментов, минимум
  собственного кода» (фундаментальный принцип)
- `BACKLOG.md` Phase 0.9 — Containerization

---

## 1. Overview

efactory распространяется как **один Linux Docker image** с полным
тулчейном (KiCad, ngspice, FreeCAD, Linux-native FEM-solver, Python
3.14 + uv, Claude Code, наши MCP-серверы). GUI приложений выкидывается
на хост через X11/Wayland passthrough. Пользователь запускает рабочую
станцию efactory одной командой `./efactory-up`; не устанавливает
пятёрку независимых тулов вручную, не координирует версии через
`compatibility.toml`. CI собирает тот же образ и публикует в GHCR.

Phase 0.9 фактически закрывает дистрибутивный вопрос проекта на
горизонте Linux; кроссплатформенность (Mac/Windows) уходит в
отдельную Phase Cross-platform после стабилизации Linux-only
workflow.

## 2. User Stories

### Конечный пользователь efactory

- Как радиолюбитель / инженер РЭА, я хочу **поставить efactory одной
  командой `docker pull` + `./efactory-up`** и сразу получить работающее
  окружение, потому что я не хочу собирать KiCad 10 + FreeCAD 1.0 +
  ngspice + FEM-solver + Python 3.14 + uv-stack из исходников или
  жонглировать пятью apt-репозиториями.
- Как пользователь, я хочу **открывать схемы и платы в нативно
  выглядящем KiCad GUI**, который запускается из контейнера, но
  отображается как обычное окно на моём Linux рабочем столе.
- Как пользователь, я хочу **переключаться между версиями efactory**
  через `docker pull efactory:linux-0.5.0` vs `:linux-latest` без
  необходимости откатывать установку.

### Разработчик efactory (Vladimir, Гвидо)

- Как разработчик, я хочу **запускать тесты и пайплайны внутри того
  же образа, что публикуется пользователям**, чтобы не было
  «у меня работает, у пользователя нет».
- Как разработчик, я хочу **продолжать локальный dev-workflow через
  `uv sync` на хосте** (host-mode для скорости итераций), а в Docker
  гонять только smoke / regression / release builds.
- Как разработчик, я хочу **изолированный runtime-агент** для чистых
  экспериментов с LLM — Docker даёт изоляцию от моего `~/.claude/`
  как побочный эффект.

### CI

- Как CI-runner, я хочу **собрать образ за разумное время** (≤ 15
  мин cold build, ≤ 5 мин warm с кэшем слоёв) и прогнать smoke-тест
  внутри.
- Как CI-runner, я хочу **публиковать образ в GHCR** с двойным тегом
  (git SHA + `linux-latest`) на каждый merge в `main`, и
  дополнительно `linux-X.Y.0` на релизы.

## 3. Functional Requirements

### Образ `efactory:linux`

- ДОЛЖЕН быть **самодостаточным**: внутри есть всё, что нужно для
  end-to-end пайплайна efactory (schematic build → ngspice → ERC/DRC
  → FEM verify → PCB export → enclosure).
- ДОЛЖЕН использовать **Ubuntu 24.04 LTS** как base (multi-stage
  build с финальным stage на slim variant).
- ДОЛЖЕН ставить **KiCad 10 из официального KiCad apt-репозитория**
  (`ppa:kicad/kicad-10.0` или его dpkg-эквивалент в Ubuntu).
- ДОЛЖЕН ставить **Python 3.14 через uv** в `/usr/local/` (не из
  apt — мы хотим контроль над минорной версией и venv-настройку).
- ДОЛЖЕН ставить **ngspice**, **FreeCAD 1.0+** (с Sheet Metal
  workbench как addon), **Linux-native FEM-solver** (выбор по T113 —
  Elmer FEM primary или GetDP+Gmsh fallback).
- ДОЛЖЕН содержать **Claude Code CLI** как frontend агента
  (`claude` в PATH).
- ДОЛЖЕН содержать **наши MCP-серверы** + сам код efactory,
  установленные как editable wheel (для возможности патчей через
  bind-mount при разработке).
- ДОЛЖЕН поддерживать **GUI passthrough** через X11 и/или Wayland
  socket mount + Xauthority forwarding.
- ДОЛЖЕН поддерживать **GPU acceleration** через `/dev/dri` (Intel/AMD)
  опционально nvidia-runtime (NVIDIA). При отсутствии — software
  rendering как fallback.
- ДОЛЖЕН поддерживать **volume mounts**: `/workspace` (проекты
  пользователя), `/libs` (пользовательские библиотеки моделей /
  компонентов), `~/.claude/.credentials.json:ro` (Claude Code auth).
- ДОЛЖЕН запускаться под `--user $(id -u):$(id -g)` для корректных
  прав на host-volume'ах.
- НЕ ДОЛЖЕН содержать AppImage-форматы инструментов (всё через apt
  или uv).
- НЕ ДОЛЖЕН содержать секреты, API-ключи, пользовательские данные.
- МОЖЕТ публиковаться в двух вариантах: `efactory:linux-{ver}` (полный
  с GUI) и `efactory:linux-headless-{ver}` (slim для CI без X-libs /
  GUI приложений).

### Wrapper `efactory-up`

- ДОЛЖЕН быть shell-скриптом в корне репозитория efactory.
- ДОЛЖЕН проверять наличие `docker` в PATH, наличие нужных volume-
  директорий, наличие `~/.claude/.credentials.json`.
- ДОЛЖЕН делать `xhost +local:docker` (или эквивалент Wayland) для
  X-permissions перед запуском.
- ДОЛЖЕН поднимать контейнер через `docker run` со всеми правильными
  флагами (env / volumes / device / user).
- МОЖЕТ принимать флаги: `--pull` (обновить образ), `--version <X.Y.0>`
  (запустить конкретную версию), `--headless` (использовать slim
  variant без GUI).
- НЕ ДОЛЖЕН делать `sudo` без явного флага (только `xhost` если
  пользователь сам в docker-группе).

### CI

- ДОЛЖЕН собирать образ на каждый merge в `main` через GitHub
  Actions с использованием Docker Buildx и слоёвого кэша.
- ДОЛЖЕН прогонять inside-container smoke-test после сборки:
  `kicad-cli sch erc <fixture>`, ngspice OP на тестовом circuit'е,
  `freecadcmd --version`, `<fem-solver> --version`,
  `uv run pytest -m smoke` (если такой mark введён).
- ДОЛЖЕН публиковать в GHCR (`ghcr.io/vlakir/efactory`) с тегами:
  `linux-latest` + `git-sha-<short>` на каждый merge; `linux-X.Y.0`
  на каждый release-tag.
- МОЖЕТ публиковать slim-variant отдельным тегом
  (`linux-headless-latest` + `linux-headless-X.Y.0`).

### FEM-solver pilot (T113)

- ДОЛЖЕН протестировать **Elmer FEM (primary)** и **GetDP+Gmsh
  (fallback)** на трёх референсных задачах:
  - SE OPT 6П14П (audio output transformer, magnetostatic 2D).
  - Силовой трансформатор 50 Гц (magnetostatic 2D / magnetodynamic
    2D с учётом потерь).
  - Flyback SMPS дроссель (magnetostatic 2D + magnetodynamic с
    AC-эффектами).
- ДОЛЖЕН зафиксировать критерии выбора:
  1. Качество результатов vs PyOpenMagnetics-аналитики (target —
     ≤10% расхождение).
  2. API-удобство для LLM-orchestration (Python wrapper, CLI
     simplicity, error reporting).
  3. Время счёта на 8-core CPU (≤30 сек на reference задачу).
  4. Размер solver-стека в образе (target ≤500 MB).
  5. Документация / community / активность развития.
- ДОЛЖЕН закончиться **ADR в `DECISIONS.md`**: «FEM-solver:
  Elmer / GetDP — окончательный выбор, обоснование».
- МОЖЕТ ввести solver-agnostic port
  `ports/outbound/magnetic_field_solver.py` + adapter
  `adapters/outbound/fem_solver/<chosen>/`, если по итогам пилота
  оба кандидата дают сравнимое качество (тогда мы оставляем
  возможность переключить в будущем).

## 4. Success Criteria

### T110 — Базовый Dockerfile

- `docker build .` без ошибок на чистой машине.
- Размер итогового образа (slim CI variant, без GUI) **≤ 3 GB**.
- Размер полного образа (с GUI-стеком) **≤ 10 GB** (приемлемо для
  desktop distribution).
- `docker run efactory uv run pytest` зелёный — тот же тест-набор,
  что на хосте (≥ 80% coverage сохраняется).
- Cold build (без layer cache) **≤ 20 мин** на 8-core CI runner.
- Warm build (с layer cache) **≤ 5 мин**.

### T111 — KiCad GUI passthrough

- KiCad eeschema, pcbnew, KiCad project manager, 3D viewer
  запускаются из контейнера, отображаются на хосте через X11/Wayland.
- На dev-машине Vladimir'а — 50 циклов open/save/close SE-amp
  фикстуры без падений / OOM / зависаний.
- Шрифты, clipboard, drag-and-drop работают (basic UX-проверки).
- GPU acceleration через `/dev/dri` активен на Intel/AMD; software
  rendering как fallback (без `/dev/dri`) не падает на тестовых
  3D-моделях.

### T112 — FreeCAD

- `freecadcmd --version` отвечает.
- FreeCAD GUI запускается через X11.
- Sheet Metal workbench (addon) доступен в Workbench-меню GUI.
- `freecad-mcp` (наш Python wrapper) запускается, базовые tool-calls
  работают.

### T113 — FEM solver

- Один из кандидатов (Elmer или GetDP) выбран и интегрирован.
- Pilot прошёл на трёх референсных задачах с расчётной индуктивностью
  совпадающей с PyOpenMagnetics в пределах **±10%**.
- ADR в `DECISIONS.md` зафиксирован.
- Solver-стек в финальном образе **≤ 500 MB**.

### T114 — `efactory-up` wrapper

- `./efactory-up` на чистой Linux-машине (с установленным Docker
  Engine) запускает работающую сессию efactory **за ≤ 60 секунд**
  (от запуска до интерактивного prompt'а агента).
- Без `sudo` на хосте (кроме `xhost +local:docker`, если запускается
  не из docker-группы).
- Скрипт **≤ 150 строк** bash с явным error-handling.

### T115 — CI / GHCR

- На каждый merge в `main` GHCR содержит `ghcr.io/vlakir/efactory:
  linux-latest` и `ghcr.io/vlakir/efactory:git-<sha-short>`.
- Релиз-теги (`0.X.0`) дополнительно создают
  `ghcr.io/vlakir/efactory:linux-0.X.0`.
- Pull этого образа на чистой машине → `./efactory-up` работает
  end-to-end.

### T120 — AppImage cleanup

- 0 строк кода специфичных для AppImage в `src/`.
- Все integration-тесты в `tests/integration/adapters/platform_native/`
  переписаны под apt-distribution (KiCad через PATH из apt).
- `pytest.mark.skipif` в e2e / integration тестах используют только
  «kicad in PATH» как условие.
- Spec T009 помечен как partially-replaced ссылкой на этот spec.

## 5. Key Entities

### Dockerfile layers (multi-stage)

```
Stage 1: base (Ubuntu 24.04 LTS)
  ├── apt: kicad, ngspice, freecad, freecad-addon-sheetmetal, <fem-solver>,
  │        xauth, x11-apps, libgl1, mesa-utils
  └── system Python — НЕ используем, чистим apt cache

Stage 2: python-build
  ├── COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
  ├── uv venv /usr/local/efactory-venv --python 3.14
  └── uv pip install --python /usr/local/efactory-venv pyproject.toml

Stage 3: efactory-code
  ├── COPY src/ /opt/efactory/src/
  ├── COPY pyproject.toml uv.lock /opt/efactory/
  └── uv pip install -e . (editable install для bind-mount overrides)

Stage 4: claude-code
  └── curl https://... | sh  (или npm install -g)

Stage 5 (final): efactory:linux (full GUI)
  ├── Copy artifacts из всех previous stages
  ├── User: efactory (uid 1000) — переопределяется через --user в runtime
  ├── WORKDIR /workspace
  └── ENTRYPOINT: thin wrapper, который запускает Claude Code

Stage 5-alt (slim CI): efactory:linux-headless
  ├── Без x11-apps, без freecad-GUI пакетов
  └── Тот же entrypoint
```

### Volume mounts при запуске

| Host | Container | Mode | Назначение |
|---|---|---|---|
| `$HOME/efactory-projects/` | `/workspace/` | rw | Проекты пользователя (Project YAML, decisions, схемы, симуляции) |
| `$HOME/efactory-libs/` | `/libs/` | rw | Пользовательские SPICE-модели, KiCad-библиотеки |
| `$HOME/.claude/.credentials.json` | `/root/.claude/.credentials.json` | ro | Claude Code auth (refresh token) |
| `/tmp/.X11-unix/` | `/tmp/.X11-unix/` | rw | X11 socket |
| `$XAUTHORITY` (или `~/.Xauthority`) | `/root/.Xauthority` | ro | X auth cookie |

### Container env vars

| Var | Source | Назначение |
|---|---|---|
| `DISPLAY` | host `$DISPLAY` | X11 target |
| `WAYLAND_DISPLAY` | host (опц.) | Wayland socket |
| `XDG_RUNTIME_DIR` | host (для Wayland) | Wayland socket location |
| `EFACTORY_PROJECTS_ROOT` | `/workspace` | где efactory ищет проекты |
| `EFACTORY_LIBS_ROOT` | `/libs` | где efactory ищет custom libraries |
| `EFACTORY_DATABASE_URL` | `sqlite+aiosqlite:///workspace/.efactory/db.sqlite` | persistent index |

### GHCR tags

| Tag | Когда обновляется |
|---|---|
| `ghcr.io/vlakir/efactory:linux-latest` | Каждый merge в `main` |
| `ghcr.io/vlakir/efactory:git-<sha-short>` | Каждый merge в `main` |
| `ghcr.io/vlakir/efactory:linux-X.Y.0` | Каждый release-tag |
| `ghcr.io/vlakir/efactory:linux-headless-latest` | Каждый merge в `main` |
| `ghcr.io/vlakir/efactory:linux-headless-X.Y.0` | Каждый release-tag |

## 6. Assumptions & Constraints

- **Целевая ОС пользователя:** Linux с Docker Engine ≥ 24.0
  (нативный Docker, не Docker Desktop). Ubuntu 22.04+ / Fedora
  39+ / Arch / NixOS — все ОК.
- **Не поддерживается:** Mac (Docker Desktop через Linux VM),
  Windows (Docker Desktop / WSL2). Это **Phase Cross-platform**
  (T116-T117), не текущая фаза.
- **GPU:** Intel/AMD через `/dev/dri` — out-of-the-box. NVIDIA через
  `nvidia-container-toolkit` (если установлен на хосте). Software
  rendering как fallback.
- **Сеть:** требуется outbound HTTPS для Anthropic API (Claude Code),
  для `docker pull`, для пользовательских sourcing-API (Mouser /
  DigiKey — Phase 7). Внутренние MCP-серверы — все через stdio (без
  network exposure).
- **Хранилище пользователя:** проекты и библиотеки живут на хосте в
  `$HOME/efactory-projects/` и `$HOME/efactory-libs/`. Контейнер
  stateless: после `docker rm` остаются только host volumes.
- **Версионная политика:** semver через CHANGELOG milestones (как
  было); каждая `[X.Y.0]` release дополнительно теггирует образ.
  Backward compatibility между minor-версиями не гарантируется в
  alpha-фазе (до 1.0.0); breaking changes документируются в
  CHANGELOG.

## 7. Out of Scope

- **Mac/Windows distribution.** Перенесено в Phase Cross-platform
  (T116, T117).
- **Native FEMM fallback.** Если возникнет запрос индустрии на
  совместимость с FEMM-моделями — Phase Cross-platform T118 (opt-in).
- **Native install path без Docker.** Если у пользователя corporate
  restrictions против Docker — Phase Cross-platform T119.
- **Web UI / remote access.** Уже в Phase 8 (T076, T080); не
  смешиваем с containerization.
- **Изоляция runtime-агента через `CLAUDE_CONFIG_DIR`** на хосте —
  отпадает, Docker делает изоляцию автоматически как побочный
  эффект.
- **Реализация LLM chat-client задач T011-T019** — отдельная Phase
  1b, после Phase 0.9.
- **Кодовый рефакторинг platform_layer.py** — это **T120 внутри
  Phase 0.9**, но **не** в Phase 0 spike (T110). Откладывается до
  стабилизации T110-T115.

---

## Implementation Phases (внутри Phase 0.9)

### Phase 0 — Базовый Dockerfile (T110)

**Цель:** минимальный работающий образ с CLI-стеком (без GUI).
Validate: `docker build` + `docker run pytest`.

**Содержание:**
- `Dockerfile` в корне репозитория efactory.
- Multi-stage build: `base` → `python-build` → `efactory-code` →
  `claude-code` → `efactory:linux-headless` (final).
- Только slim variant (headless, без X-libs / FreeCAD GUI / kicad
  GUI зависимостей).
- Базовый `.dockerignore` (исключить `.venv/`, `.git/`, `tests/
  fixtures/output/`, etc.).

**Acceptance:** `docker build -t efactory:linux-headless .` ≤ 20
мин cold; `docker run efactory:linux-headless uv run pytest`
прогоняет весь тестовый набор зелёный (KiCad через apt в PATH,
ngspice работает, FreeCAD CLI работает).

### Phase 1 — KiCad GUI passthrough (T111)

**Цель:** добавить X11/Wayland поддержку, проверить KiCad GUI из
контейнера.

**Содержание:**
- Расширить final stage: добавить `x11-apps`, `libgl1`,
  `dbus-x11`, `xauth`, KiCad GUI зависимости.
- В runtime — env `DISPLAY` + volume `/tmp/.X11-unix` +
  `$XAUTHORITY`.
- Опциональный `--device /dev/dri:/dev/dri` для GPU.
- Smoke-test: открыть SE-amp фикстуру, сохранить, закрыть.

**Acceptance:** на dev-машине Vladimir'а 50 циклов open/save/close
без падений; шрифты / clipboard работают.

### Phase 2 — FreeCAD (T112)

**Цель:** FreeCAD CLI + GUI + Sheet Metal addon.

**Содержание:**
- apt: `freecad`, `freecad-doc`, addon Sheet Metal через
  скачивание из FreeCAD addons-repository в build-time.
- `freecadcmd` + GUI passthrough.
- Smoke: `freecadcmd --version`, открыть тестовую модель
  enclosure.

**Acceptance:** Sheet Metal workbench доступен в GUI;
`freecadcmd` запускается; freecad-mcp подключается.

### Phase 3 — FEM solver pilot + integration (T113)

**Цель:** выбрать между Elmer FEM и GetDP+Gmsh; интегрировать
выбранный.

**Содержание:**
1. **Pilot (вне Dockerfile, ~1 сессия):**
   - Развернуть Elmer + GetDP на dev-машине Vladimir'а (apt).
   - Прогнать три референсные задачи на каждом.
   - Заполнить сравнительную таблицу (см. §3.FEM-solver pilot).
   - **ADR в `DECISIONS.md`** с выбором.
2. **Integration (после ADR):**
   - Добавить выбранный solver в Dockerfile final stage.
   - `adapters/outbound/fem_solver/<chosen>/` adapter.
   - `ports/outbound/magnetic_field_solver.py` port.
   - Реализация `mag_verify_field` use case.

**Acceptance:** на тестовом OPT 6П14П расчётная L через solver
совпадает с PyOpenMagnetics ±10%; ADR закрыт.

### Phase 4 — `efactory-up` wrapper (T114)

**Цель:** один shell-скрипт для запуска efactory-сессии.

**Содержание:**
- `./efactory-up` в корне репо.
- Pre-flight: проверка docker, volume-dirs, claude credentials.
- `xhost +local:docker` (если нужно).
- `docker run` с правильными env / volumes / devices.
- Флаги: `--pull`, `--version`, `--headless`.

**Acceptance:** на чистой Linux-машине `./efactory-up` за ≤ 60s
поднимает работающую сессию.

### Phase 5 — CI / GHCR publish (T115)

**Цель:** автоматическая сборка и публикация образа.

**Содержание:**
- GitHub Actions workflow в `.github/workflows/docker.yml`.
- Сборка через `docker/build-push-action@v5` с buildx cache.
- Сборка двух вариантов: `linux` (full) + `linux-headless` (slim).
- Smoke-test inside container перед публикацией.
- Push в GHCR с tags (см. §5).

**Acceptance:** первый успешный merge в main → GHCR содержит
pull-able образ; `docker pull` на чистой машине работает.

### Phase 6 — AppImage cleanup (T120)

**Цель:** удалить dead AppImage-detection код из `platform_layer`.

**Содержание:**
- Удалить `_scan_appimage_locations`,
  `_detect_kicad_cli_via_kicad_appimage`, multi-call AppImage
  logic из `src/adapters/outbound/platform_native/platform_layer.py`.
- Подправить `ports/outbound/platform_layer.py` (убрать
  multi-call AppImage комментарии).
- Очистить тесты в `tests/integration/adapters/platform_native/`
  от AppImage reality-tests, добавить apt-distribution tests.
- В e2e / integration тестах `pytest.mark.skipif`: оставить только
  «kicad in PATH» условие.
- Spec T009 пометить как «Частично заменено» (footer reference на
  этот spec).

**Acceptance:** 0 строк кода с AppImage-detection в `src/`; все
тесты зелёные при KiCad из apt; T009 footnote ставит ссылку.

---

## Clarify (заполняется Claude после прочтения Vladimir'ом)

### Open questions

1. **GHCR visibility.** Делаем `ghcr.io/vlakir/efactory` public
   (anyone can pull) или private (требуется auth)? По первому
   принципу efactory (open-source-first) — public кажется
   естественным.

2. **Phase 0 size target — 3 GB реалистично?** KiCad libraries
   alone ~3 GB (по моему опыту с official Ubuntu repo). Если
   tight — возможно вынести libraries в отдельный image layer и
   подгружать только по запросу; либо принять 5–6 GB для slim
   variant.

3. **Editable install vs frozen wheel.** Делаем `uv pip install -e .`
   для возможности override через bind-mount при разработке, или
   frozen wheel для воспроизводимости? Я бы шёл editable + опция
   bind-mount `src/` в runtime для dev-режима.

4. **MCP-серверы внутри образа — какие именно?** Пока efactory
   содержит kicad-sch-api facade + SPICEBridge wrapper (наши). В
   roadmap (Phase 1a/2/3) добавятся ещё. В Phase 0 кладём то, что
   есть сейчас, или закладываем slot'ы под будущие?

5. **Phase 3 (FEM-solver pilot) до или после Phase 1-2?** Логически
   pilot независим от GUI passthrough и FreeCAD. Можно делать
   параллельно. Но в одну сессию вместе с Dockerfile — слишком
   большой scope. Я бы держал линейный порядок (Phase 3 после
   Phase 2), но pilot эксперимент можно запустить раньше — на
   хосте, без образа.

6. **Versioning для образа vs кода.** Релиз `[0.7.0]` в CHANGELOG
   тегирует Docker image как `linux-0.7.0`. Что делаем, если в
   между релизами нужно срочно пересобрать образ из-за апдейта
   KiCad apt (баг-фикс)? Сейчас в roadmap нет понятия «patch
   release» (только minor); может, ввести `linux-0.7.0-r1`
   суффикс?

### Resolved (с ответами Vladimir'а от 2026-05-19)

- **Q: Base image для контейнера?**
  **A:** Ubuntu 24.04 LTS — yes.

- **Q: Python в образе?**
  **A:** uv-managed Python в `/usr/local/` (НЕ через apt).

- **Q: Container registry?**
  **A:** `ghcr.io/vlakir/efactory` (рядом с репо).

- **Q: Multi-stage build?**
  **A:** Yes, multi-stage с отдельными слоями для базы / Python venv /
  efactory code / Claude Code / final.

---

## Analyze (заполняется Claude после Clarify)

<!-- Pending — будет заполнено после ответов Vladimir'а на Open
     questions Clarify. Категории: Critical (🔴) — фиксим до начала
     реализации; Warning (🟡) — обсуждаем; Note (🟢) — к сведению. -->

- ...

---

## Notes / Plan for next steps

1. Vladimir отвечает на 6 Open questions Clarify.
2. Гвидо обновляет spec (вшивает ответы в Resolved + поднимает
   соответствующие разделы выше).
3. Гвидо проходит Analyze — ищет противоречия и упущения.
4. Если Analyze чист — T110 переходит в BOARD → Doing.
5. Phase 0 (минимальный Dockerfile) — первая реальная implementation
   PR. Acceptance: `docker build` + `docker run pytest` зелёный.
6. Дальше последовательно Phase 1 → Phase 6.
