## Spec: T009 — platform_layer + app_manager (infrastructure для bridges)

**Статус:** Analyzed
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

### Resolved

Разработчик ответил 2026-05-18, поправил Q1 и Q5, плюс важная
поправка: KiCad и FreeCAD на dev-машине реально установлены как
**AppImage** (Гвидо угадал что их нет — было предположение, не
проверка; feedback сохранён в auto-memory).

1. **AppManager scope** — **Headless unified** вместо GUI-only
   (Q1 (A) → (B)). Два метода:
   - `run(kind, args, timeout) -> CompletedProcess` — blocking
     headless вызов (для `kicad-cli`, `ngspice batch`).
   - `launch(kind, args) -> ApplicationInfo` — detach background
     (для GUI: KiCad, FreeCAD).
   - `status` / `stop` / `restart` — работают для `launched` apps.
2. **PID registry** — **(A) in-memory**.
3. **ApplicationKind** — все 5: KICAD, KICAD_CLI, FREECAD, FEMM, NGSPICE.
4. **CLI** — **(B) positional** `efactory app launch <kind>` /
   `app run <kind> [-- args...]` etc.
5. **Acceptance** — **(B) mock subprocess** (без PYTHON в enum).
   Integration через `/bin/sleep` или подобное Unix-builtin.
6. **Phasing** — **(A) один phase**.

#### Реальное окружение dev-машины (проверено command -v + find)

- KiCad: `/home/vlakir/kicad/kicad.AppImage` (→
  `kicad-10.0.2-x86_64.AppImage`). `.desktop` Exec:
  `/home/vlakir/kicad/kicad.AppImage %f`.
- FreeCAD: `/home/vlakir/Загрузки/freecad.AppImage` (→
  `FreeCAD_1.1.1-Linux-x86_64-py311.AppImage`). `.desktop` Exec:
  `'/home/vlakir/Загрузки/freecad.AppImage' - --single-instance %F`.
- FEMM: не установлен (Windows-only).
- ngspice: не установлен (`apt install` либо через PySpice).
- kicad-cli: внутри KiCad AppImage; синтаксис вызова проверим
  integration тестом.

#### Resolution стратегия для PlatformLayer

`resolve_executable(kind)` пробует в порядке:

1. **Env override** — `EFACTORY_<KIND>_PATH` (например,
   `EFACTORY_KICAD_PATH=/path/to/kicad.AppImage`).
2. **`shutil.which(binary_name)`** — для apt/snap installs в PATH.
3. **`.desktop` файл** — парсим `~/.local/share/applications/
   <kind>.desktop`, извлекаем первый non-flag path из `Exec=`.
4. **Known install paths** — список по платформе (см. ниже).

#### Known install paths

- **Linux:**
  - PATH-style: `/usr/bin/`, `/usr/local/bin/`, `~/.local/bin/`,
    `/opt/<vendor>/`.
  - AppImage locations (only one-level deep scan):
    `~/Applications/`, `~/Downloads/`, `~/Загрузки/`,
    `~/AppImages/`, `~/<app>/` (например, `~/kicad/`).
  - Pattern: `<app>*.AppImage` либо `<app>.AppImage`.
- **Windows:**
  - `C:\Program Files\KiCad\<ver>\bin\kicad.exe`,
    `C:\Program Files\FreeCAD <ver>\bin\freecad.exe`,
    `C:\femm42\bin\femm.exe`, `C:\Program Files\ngspice\bin\ngspice.exe`.
- **macOS:** Out of Scope (можно добавить позже).

---

### Analyze

#### 🔴 Critical

##### C1. AppImage resolution через `.desktop`

`Exec=` содержит флаги (`%f`, `%F`, `--single-instance`, etc.).
PlatformLayer должен `shlex.split(exec_line)`, отфильтровать
`%[fFuU]` placeholder'ы и `--*` flags, взять первый существующий
absolute path.

**Резолюция:** реализуется в helper `_parse_desktop_exec(line)
-> Path | None`. Tested на реальных KiCad/FreeCAD `.desktop`
файлах.

##### C2. KiCad-CLI inside AppImage

`kicad-cli` — отдельный binary, но внутри KiCad AppImage. Прямого
PATH'а нет. Проверка integration:
- `~/kicad/kicad.AppImage` — multi-call binary? Если да, может
  быть синтаксис `kicad.AppImage cli args...` или
  `kicad.AppImage --appimage-extract-and-run kicad-cli args...`.
- Если нет — нужно extract AppImage и запускать
  `<extracted>/usr/bin/kicad-cli`.

**Резолюция:** PlatformLayer для KICAD_CLI возвращает
`tuple[Path, list[str]]` (executable + command prefix). Узнаём
синтаксис integration-тестом и фиксируем mapping. Если AppImage
не поддерживает multi-command — Out of Scope, kicad-cli получит
статус `not_installed` через AppImage; реальное использование —
после установки KiCad через apt либо отдельной задачи extract.

##### C3. Detach semantics — POSIX vs Windows

- **POSIX:** `subprocess.Popen(..., start_new_session=True)` —
  процесс отвязан от tty CLI, не убивается при выходе CLI.
- **Windows:** `subprocess.CREATE_NEW_PROCESS_GROUP` +
  `DETACHED_PROCESS` flags.

**Резолюция:** Adapter helper `_detach_kwargs() -> dict` который
возвращает platform-specific kwargs. Тесты — mocked Popen, проверка
переданных kwargs.

#### 🟡 Warning

##### W1. Stale PID detection

Между `launch()` и `status()` процесс мог завершиться (crash, user
kill). `status()` зовёт `process.poll()`; если `None` — running,
если int — exit code, помечаем `installed_stopped`, убираем из
registry.

##### W2. Concurrent launch — два инстанса

CLI не защищает от двух `launch kicad` подряд из одного процесса.
Второй создаст второй KiCad instance (KiCad сам решит multi-window
vs reject). In-memory registry перезапишет PID на второй — первый
KiCad станет «orphan» (запущен, но AppManager не знает PID).

**Резолюция:** для Phase 1a не защищаем. Документируется. CLI
команда `launch` может проверять `status(kind) == RUNNING` и
warning'ить.

##### W3. `.desktop` файл устаревший

Пользователь удалил AppImage, `.desktop` остался. После extract —
проверка `Path.is_file()`; если нет — fallback на следующий шаг
resolution.

#### 🟢 Note

##### N1. CLI `app status` — TSV таблица всех known apps

```
kicad        installed_stopped  /home/vlakir/kicad/kicad.AppImage
kicad-cli    not_installed      —
freecad      installed_stopped  /home/vlakir/Загрузки/freecad.AppImage
femm         not_installed      —
ngspice      not_installed      —
```

##### N2. Integration test через `/bin/sleep`

Acceptance: `SubprocessAppManager` с stubbed `PlatformLayer`
возвращающим `Path('/bin/sleep')` для тестового KIND. Launch с
args `['5']`, status RUNNING, stop, status INSTALLED_STOPPED.

##### N3. CLI: 5 команд

- `efactory app status [--kind KIND]`.
- `efactory app launch KIND [-- args...]` — GUI launch.
- `efactory app run KIND [-- args...]` — headless blocking
  (печатает stdout, exit code).
- `efactory app stop KIND`.
- `efactory app restart KIND`.

Session-log: `app.status`, `app.launch`, `app.run`, `app.stop`,
`app.restart`.

##### N4. Independence contract

`adapters.outbound.platform_native` + `adapters.outbound.subprocess_apps`
— два новых sub-package. Добавляются в independence contract.

##### N5. Composition

```python
platform = NativePlatformLayer()
app_manager = SubprocessAppManager(platform)
build_app(..., platform_layer=platform, app_manager=app_manager)
```

##### N6. Stop timing: TERM → 5s → KILL

```python
proc.terminate()
try:
    proc.wait(timeout=5)
except TimeoutExpired:
    proc.kill()
    proc.wait()
```

##### N7. AppImage glob depth

Не делаем `~/**` сканирование. Только level-1 children в known
locations (`~/Applications/<file>.AppImage`, не `~/Documents/foo/
bar/baz.AppImage`).

##### N8. Env override format

`EFACTORY_<KIND>_PATH`. Для kebab-case kind'ов (`kicad-cli`)
преобразуем в `EFACTORY_KICAD_CLI_PATH`.