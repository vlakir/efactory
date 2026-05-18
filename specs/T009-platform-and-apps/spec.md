## Spec: T009 — platform_layer + app_manager (infrastructure для bridges)

**Статус:** Draft (готов к Clarify)
**Дата создания:** 2026-05-18
**Связанные документы:**
- `CONCEPT.md` §2 (внешние тулчейны: KiCad, ngspice, FreeCAD, FEMM),
  §10 (кроссплатформенность Linux/Windows).
- `BACKLOG.md` → запись T009 (Фаза 1a — MVP-ядро).
- Будущее: T004/T005 (KiCad↔SPICE bridges) — потребители platform
  + app_manager.

---

### 1. Overview

T009 — **инфраструктурный фундамент** для будущих bridges Фазы 1a.
Без него каждый bridge (T004 KiCad pipeline, T055 FEMM verify,
T060+ FreeCAD enclosure) изобретал бы свою platform abstraction +
process management. Делаем один раз, переиспользуем.

Содержит:
1. **`platform_layer`** — абстракция платформы (Linux / Windows /
   macOS): пути, исполняемые имена, env-переменные.
2. **`app_manager`** — управление процессами внешних приложений
   (запуск GUI / headless, остановка, перезапуск, статус, PID
   tracking).
3. **CLI `efactory app status / start / stop / restart`** — для
   диагностики и интерактивной работы.
4. Реальная интеграция — minimum один app в acceptance тесте
   (например, `python --version` как safe proof-of-concept что
   pipe работает; KiCad/FreeCAD — skip-if-not-installed).

### 2. User Stories

- **«Где у меня kicad-cli?»** Как разработчик после bootstrap, я хочу
  `efactory app status` — таблица known applications с найденными
  путями (или «not found»).
- **«Запусти KiCad чтобы я открыл проект.»** `efactory app start kicad`
  — поднимает KiCad GUI. `efactory app stop kicad` — закрывает.
- **«Bridge нужен kicad-cli путь.»** T004 KiCad pipeline получает
  `platform_layer.resolve_executable('kicad-cli')` без хардкода путей.
- **«Перезапустить KiCad после crash.»** `efactory app restart kicad`.

### 3. Functional Requirements

#### Domain

- ДОЛЖНА: появиться `ApplicationKind` (StrEnum) в
  `src/domain/application.py`:
  ```python
  class ApplicationKind(StrEnum):
      KICAD = 'kicad'
      KICAD_CLI = 'kicad-cli'
      FREECAD = 'freecad'
      FEMM = 'femm'
      NGSPICE = 'ngspice'
  ```
- ДОЛЖНА: `ApplicationStatus` (StrEnum):
  ```python
  class ApplicationStatus(StrEnum):
      NOT_INSTALLED = 'not_installed'   # не найден на PATH
      INSTALLED_STOPPED = 'installed_stopped'  # установлен, не запущен
      RUNNING = 'running'  # запущен (PID известен)
      ```
- ДОЛЖНА: `ApplicationInfo` (frozen VO):
  ```python
  class ApplicationInfo(BaseModel):
      kind: ApplicationKind
      executable_path: Path | None  # None если not_installed
      status: ApplicationStatus
      pid: int | None  # для RUNNING
      version: str | None  # extracted from --version, optional
  ```

#### Outbound port `PlatformLayer`

- ДОЛЖНА: `src/ports/outbound/platform_layer.py`:
  ```python
  class PlatformLayer(Protocol):
      """Абстракция за платформенными различиями."""

      def os_kind(self) -> OsKind: ...  # linux | windows | macos

      def resolve_executable(self, kind: ApplicationKind) -> Path | None:
          """Вернуть путь к executable; None если не найден.
          Проверяет PATH через shutil.which + known install locations.
          """
          ...

      def get_default_install_paths(
          self, kind: ApplicationKind,
      ) -> list[Path]:
          """Known places для kind на текущей OS."""
          ...

      def get_clean_env(
          self, kind: ApplicationKind,
      ) -> dict[str, str]:
          """env для запуска kind — наследует os.environ + app-specific
          tweaks (например, для KiCad — KICAD_USER_TEMPLATE_DIR).
          """
          ...
  ```

- ДОЛЖНА: `OsKind` enum: `linux | windows | macos`.

#### Outbound port `AppManager`

- ДОЛЖНА: `src/ports/outbound/app_manager.py`:
  ```python
  class AppManager(Protocol):
      async def status(self, kind: ApplicationKind) -> ApplicationInfo: ...

      async def start(
          self,
          kind: ApplicationKind,
          *,
          args: list[str] | None = None,
      ) -> ApplicationInfo:
          """Запустить app (GUI: detach как background process)."""
          ...

      async def stop(self, kind: ApplicationKind) -> None:
          """Graceful TERM, через таймаут — KILL."""
          ...

      async def restart(self, kind: ApplicationKind) -> ApplicationInfo: ...
  ```

- ДОЛЖНЫ: контрактные исключения `ApplicationNotInstalledError`,
  `ApplicationStartError`, `ApplicationStopError`.

#### Adapters

- **`NativePlatformLayer`** (`adapters/outbound/platform_native/`):
  - `os_kind()` через `sys.platform`.
  - `resolve_executable()`: `shutil.which(<binary_name>)`; если нет,
    проверка `get_default_install_paths()` (например, Windows
    Program Files).
  - `get_default_install_paths()`:
    - Linux: `/usr/bin/`, `/usr/local/bin/`, `~/.local/bin/`,
      `/opt/<vendor>/`.
    - Windows: `%ProgramFiles%\<vendor>\<app>\bin\`, `%LOCALAPPDATA%`.
    - macOS: `/Applications/<App>.app/Contents/MacOS/`,
      `/opt/homebrew/bin/`.
  - Binary names per OS (например, `kicad-cli` Linux / macOS,
    `kicad-cli.exe` Windows).

- **`SubprocessAppManager`** (`adapters/outbound/subprocess_apps/`):
  - In-memory PID registry per process (один процесс CLI = одна
    карта). При новом CLI invocation — карта пустая (T009
    Out-of-Scope: persistence PID между CLI calls).
  - `start`: `subprocess.Popen` для GUI apps (detach как
    background); для headless (kicad-cli, ngspice) — start
    blocking subprocess.run возвращающий output (но это уже
    bridge logic, не app_manager).
  - `stop`: `process.terminate()`, через 5 sec `process.kill()`.
  - `status`: `kind in registry and process.poll() is None`.

#### CLI

- ДОЛЖНЫ: новые Typer subcommand'ы:
  ```
  efactory app status               # таблица всех известных apps
  efactory app status --kind kicad  # одно приложение
  efactory app start KIND [-- args...]
  efactory app stop KIND
  efactory app restart KIND
  ```
- Session-log integration (`app.status`, `app.start`, `app.stop`,
  `app.restart`).

#### Composition

- `Settings` не меняется (PlatformLayer не требует конфига; AppManager
  пока без persistent state).
- Composition wire: `NativePlatformLayer()` + `SubprocessAppManager()`
  → `build_app`.

### 4. Success Criteria

- TDD outside-in.
- 5-step гейт зелёный, coverage ≥ 80%.
- `efactory app status` показывает таблицу: каждый ApplicationKind
  + резолвинг статуса (`not_installed` если нет на машине,
  `installed_stopped` если найден).
- На моей dev-машине (Linux): ngspice / kicad-cli могут быть
  установлены (если есть) — `status` корректно сообщает.
- Integration test с **реальным `python`** как «приложение» —
  start/stop/status/restart полный round-trip (Python — гарантированно
  установлен, не нужен skip).
- Unit тесты с mocked `shutil.which` / `subprocess.Popen` — покрывают
  не-Linux paths без реальных Windows/macOS.
- KiCad/FreeCAD smoke — `pytest.skip` если соответствующий
  executable отсутствует.

### 5. Key Entities

- `ApplicationKind` (StrEnum), `ApplicationStatus` (StrEnum),
  `OsKind` (StrEnum).
- `ApplicationInfo` (frozen VO).
- `PlatformLayer` (Protocol) + `NativePlatformLayer` (adapter).
- `AppManager` (Protocol) + `SubprocessAppManager` (adapter).
- Контрактные исключения portов: `ApplicationNotInstalledError`,
  `ApplicationStartError`, `ApplicationStopError`.
- CLI subapp `app`.

### 6. Assumptions & Constraints

- Single-user, single-CLI-process. PID registry в памяти CLI;
  между CLI-вызовами не сохраняется (Out of Scope).
- Linux primary dev environment; Windows / macOS — only mocked в
  unit-тестах (CI-проверка позже).
- `python` доступен на любой dev-машине → safe для acceptance test.
- GUI apps (kicad, freecad) — `subprocess.Popen` detach; не пытаемся
  attach к existing instance.
- Headless apps (ngspice, kicad-cli) — start через bridge напрямую
  (`platform_layer.resolve_executable` + `subprocess.run`); AppManager
  фокус на GUI-lifecycle.

### 7. Out of Scope

- **Persistent PID registry** между CLI вызовами. Сейчас каждый
  `efactory app status` начинает с пустого реестра. Реально нужен
  если CLI start KiCad → CLI stop KiCad из другого вызова — пока
  нет. Расширим если станет проблемой (state-file в
  `<storage>/apps_state.json`).
- **Container apps (Docker)** — Out of Scope, потом.
- **macOS** — code-paths добавлены, но не тестируются (нет CI).
- **Process attach** (KiCad уже запущен пользователем — attach к нему).
  Сейчас CLI считает что start всегда создаёт новый instance.
- **Version detection** — `version: str | None` поле есть, но
  populate'ить не обязательно (optional). Заполним в отдельной
  задаче когда понадобится для compatibility.toml checks.
- **Headless mode bridge** — это T004 (KiCad pipeline). T009 даёт
  resolve_executable + AppManager для GUI-lifecycle.
- **FEMM на Linux** — FEMM Windows-only; на Linux статус
  `not_installed`. Документировано.
- **ngspice как «app»** — он скорее library/shared object, не
  GUI приложение. AppManager поддерживает start/stop, но реально
  использовать ngspice будем через PySpice/SPICEBridge (T008), не
  через subprocess.Popen.

---

### Clarify

#### Open questions

##### 1. Scope: GUI vs headless apps в AppManager?

GUI (KiCad, FreeCAD): нужен start/stop lifecycle (запуск как
background, kill).
Headless (kicad-cli, ngspice): subprocess.run на запрос bridge,
не «manage as service».

- **(A)** AppManager только для GUI; headless вызывает напрямую.
- **(B)** AppManager unified для всех — но семантика start
  отличается для headless.

**Предлагаемый дефолт:** **(A) GUI-focused**. PlatformLayer
(resolve_executable) — для всех. Headless apps bridge call'ит
`subprocess.run(platform.resolve_executable('kicad-cli'), args)`
напрямую, без AppManager.

##### 2. PID registry persistence между CLI вызовами?

- **(A)** In-memory (текущий процесс CLI). Простой; minus —
  каждый CLI invocation теряет состояние.
- **(B)** JSON file в `<storage>/apps.json` — между CLI вызовами
  state помнится.

**Предлагаемый дефолт:** **(A) in-memory** в T009. (B) если станет
проблемой — отдельная задача.

##### 3. Какие apps зашить в ApplicationKind enum изначально?

CONCEPT упоминает: KiCad, ngspice, FreeCAD, FEMM + kicad-cli
(headless tool).

- KICAD — GUI.
- KICAD_CLI — headless.
- FREECAD — GUI.
- FEMM — GUI (Windows-only).
- NGSPICE — headless (через PySpice; редко напрямую).

**Предлагаемый дефолт:** все 5. NGSPICE и KICAD_CLI могут редко
использоваться через AppManager (Out of Scope #ngspice), но в
enum полезно для status display.

##### 4. CLI: `efactory app start --kind kicad` vs `efactory app start kicad`?

- **(A)** `--kind <name>` (опция).
- **(B)** Positional argument: `efactory app start kicad`.

**Предлагаемый дефолт:** **(B) positional** — короче, типично для
CLI tools (`docker start <name>`, `systemctl start <name>`).

##### 5. `python` как safe acceptance app?

Чтобы тестировать `start/stop/status/restart` cycle не зависим от
KiCad, добавляем `PYTHON` в enum?

- **(A)** Да — `ApplicationKind.PYTHON = 'python'`. Acceptance test
  через python.
- **(B)** Нет — тестируем через mock subprocess.

**Предлагаемый дефолт:** **(B) mock subprocess**. PYTHON в enum
— странно (не «инструмент электроники»). Acceptance тесты с
monkeypatched subprocess дают тот же coverage.

##### 6. Phasing

- **(A)** Один phase — обозримо.
- **(B)** Два phase: domain/ports/adapter; CLI.

**Предлагаемый дефолт:** **(A)**.

---

### Analyze (после Clarify)
