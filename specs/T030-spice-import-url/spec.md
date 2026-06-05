# Spec: T030 — Импорт SPICE-моделей по URL

**Статус:** Done (PR pending merge)
**Дата создания:** 2026-06-05
**Связанные документы:**
- BACKLOG.md → T030 (reformulated 2026-06-03).
- T006 — tube library (источник pattern `<library_root>/<category>/<source>/`).
- T007 — generic `* subcategory:` header convention.
- T168 — `convert_pwrs_to_ngspice` (используется как этап pipeline).
- T029 — `KicadCliErcRunner` pattern (subprocess wrapper, exit codes 0/1/2).
- T134 — KB sync дисциплина, 3 уровня.
- T153 — Opamp category и `OpampKind.FULL_VENDOR` (placeholder под T030,
  см. `domain/spice_model.py:77`).
- T187 — slash + CLI bridge pattern (`/grid-check` ↔ `efactory design
  check-grid`).

---

## 1. Overview

T030 добавляет автономный pipeline импорта SPICE-моделей semiconductor-
компонентов (BJT, JFET, MOSFET, op-amp, diode) из публичных URL'ов
vendor'ов в пользовательскую библиотеку efactory одной командой.

Без T030 каждая новая модель — это: скачать руками, разобраться к какой
категории относится, придумать имя и место в `<user_library_root>/`,
залезть внутрь, починить HSPICE-only `PWRS()` если есть, написать KB
topic. Это разнотипная ручная работа из 5-8 шагов, отпугивающая от
расширения библиотеки.

С T030 это становится `/spice-import-url <url>`: pipeline скачивает,
классифицирует, конвертирует PWRS, кладёт под `<user_library_root>/
<category>/<vendor>/<part>.lib` с inline-headers traceability, прогоняет
per-class ngspice smoke и заводит KB topic `spice.<vendor>.<part>` —
после чего модель доступна symbol→model resolver'у и agent'у через
`/kb-search`.

## 2. User Stories / Сценарии использования

- **US1.** Как разработчик, я знаю URL опубликованной модели на сайте
  Vishay/ON Semi/Microchip → запускаю `/spice-import-url <url>` →
  модель скачана, классифицирована, установлена, smoke прошёл, KB topic
  заведён — следующий `/sim-run` на схеме с этим part'ом находит модель.
- **US2.** Как разработчик, я скачал модель руками (auth-walled vendor:
  TI PSpice .zip за SSO; раскопал .lib внутри) → `efactory spice import-
  file <path> --vendor=ti` → тот же pipeline, без шага download.
- **US3.** Как разработчик, я хочу посмотреть план импорта перед
  записью → `--dry-run` печатает классификацию, install path, smoke
  fixture, KB topic name — без модификаций файловой системы.
- **US4.** Как разработчик/agent, я повторно импортирую тот же URL по
  ошибке → exit-code != 0 с сообщением «already installed at <path>»,
  ничего не перезаписывается. С `--force` перезапись разрешена.
- **US5.** Как разработчик, я импортирую модель с подозрением что
  smoke упадёт (старая HSPICE-форма, нестандартные .PARAM) → `--skip-
  smoke` пропускает финальный шаг; модель установлена, KB topic помечен
  `smoke: skipped` — позже могу запустить smoke вручную.
- **US6.** Как CI/automation, я зову `efactory spice import-url <url>
  --json` → stdout — машинно-парсимый `ImportReport`, exit-code
  по семантике R6.

## 3. Functional Requirements

### ДОЛЖНА

#### Download (Phase 2)

- **F1.** Поддерживать **только direct-URL HTTP/HTTPS GET** без cookies,
  без SSO, без JS-рендеринга. URL должен возвращать text/plain или
  application/octet-stream с SPICE-deck в теле.
- **F2.** Timeout по умолчанию 30 секунд (override `--timeout SECONDS`).
- **F3.** Limit на размер body 1 MiB (override `--max-bytes N`) — defense
  против случайно вписанного binary URL.
- **F4.** Follow HTTP redirects ≤ 5 hops; кросс-host redirect — fail
  (defense против open redirect).
- **F5.** TLS verification on (default `ssl.create_default_context()`).
  Override `--insecure` — выводит warning, продолжает.
- **F6.** Сохранять raw downloaded bytes в `<user_library_root>/
  _imports/<sha256>/raw.lib` для аудита (provenance).
- **F7.** `efactory spice import-file <path>` — bypass download, читает
  файл с диска; всё остальное (classify → convert → install → smoke →
  KB) идентично URL-флоу.

#### Classification (Phase 2)

- **F8.** Парсить SPICE-deck на наличие двух типов карт:
  - `.SUBCKT NAME pins...` — model wrapper (исторически tubes / opamps /
    transformers / loads).
  - `.MODEL NAME TYPE (params...)` — primitive device card (исторически
    BJT / JFET / MOSFET / DIODE).
- **F9.** Mapping `.MODEL` TYPE → (ComponentCategory, subcategory):
  - `NPN` → `BJT / NPN`
  - `PNP` → `BJT / PNP`
  - `NJF` → `JFET / NJF`
  - `PJF` → `JFET / PJF`
  - `NMOS` → `MOSFET / NMOS`
  - `PMOS` → `MOSFET / PMOS`
  - `D` → `DIODE / SIGNAL` (default, refinable header'ом)
- **F10.** Mapping `.SUBCKT` → category через эвристики:
  - 5 пинов, имена в `{V+, V-, INP, INM, OUT, VCC, VEE, VS+, VS-}`-style
    → `OPAMP / FULL_VENDOR`.
  - 3 пина (`C/B/E` / `D/G/S` / `A/G/K`) — `BJT` / `MOSFET` / `TUBE` —
    дискриминация по содержимому SUBCKT (наличие `Q`-карт / `M`-карт /
    `B`-карт + tube lookups). Если ambiguous → `ClassificationAmbiguous
    Error` + сообщение «specify --category=<...> --subcategory=<...>».
  - 2 пина + только `D`-карта внутри → `DIODE` (subcategory из header'а
    или fallback `SIGNAL`).
- **F11.** Header override приоритет (как T007 для built-in): если в
  deck есть `* category: <cat>` и/или `* subcategory: <subcat>` строки
  до первой `.SUBCKT`/`.MODEL` — они **переопределяют** эвристику.
- **F12.** Multi-`.SUBCKT` / multi-`.MODEL` файлы разрешены — каждый
  splits в отдельный target file `<part>.lib` (контракт сканера
  `FilesystemSpiceModelLibrary`).
- **F13.** Vendor извлекается:
  - При `import-url`: из URL host (`www.ti.com` → `ti`,
    `www.vishay.com` → `vishay`, `www.onsemi.com` → `onsemi`,
    `ww1.microchip.com` → `microchip`); словарь `_KNOWN_VENDOR_HOSTS`.
    Unknown host → `unknown` (warning в stderr).
  - При `import-file`: дефолт `unknown`.
  - Override: `--vendor=<name>` (CLI flag), валидируется как
    `^[a-z][a-z0-9_-]*$`.

#### Conversion (Phase 3, reuse T168)

- **F14.** `convert_pwrs_to_ngspice` применяется к downloaded deck
  (idempotent). Дополнительно: автоматическая нормализация `^ → **`
  если deck маркирован header'ом `* source: hspice` или `* source:
  pspice` (как `ModelSource.AYUMI` для тубов).

#### Install (Phase 3)

- **F15.** Target path: `<user_library_root>/<category-plural>/<vendor>/
  <PART>.lib` где:
  - `<category-plural>` — `bjt` / `jfet` / `mosfet` / `diodes` / `opamps`
    / `tubes` / `transformers` / `loads` (множественные имена под
    существующий sweep T006).
  - `<PART>` — uppercase normalized model id (`2N3904`, `OPA1612`).
- **F16.** Header injection перед записью:
  ```
  * vendor: <vendor>
  * source_url: <url>   (или 'local-file:<absolute path>')
  * sha256: <hex of raw download>
  * imported_at: <UTC ISO 8601>
  * subcategory: <value>
  ```
  Любые existing `* vendor:` / `* subcategory:` строки замещаются
  (нормализация). Остальные строки сохраняются как есть.
- **F17.** Atomicity: install происходит через staging directory
  (`<user_library_root>/_imports/<sha256>/staged/`), `os.replace` на
  success. На любой fail (classification, conversion, smoke) — staged
  директория не promote'ится, ничего на user-видимом месте не
  изменяется.
- **F18.** Duplicate detection: если `<target_path>` уже существует —
  `ImportDuplicateError`. `--force` перезаписывает, выводит warning.

#### Smoke (Phase 3)

- **F19.** Per-class smoke fixture — ngspice OP analysis на минимальном
  тестовом netlist'е (~5-10 строк), который подключает свежую модель и
  проверяет 1 элементарную инвариантную точку:
  - `BJT/NPN`: CE @ Vcc=10V, Rc=1k, Vb=2V через Rb=100k → `Vc < Vcc`.
  - `BJT/PNP`: mirror.
  - `JFET/N`: CS @ Vdd=10V, Rd=1k, Vgs=-1V → `Vd < Vdd`.
  - `MOSFET/N`: CS @ Vdd=10V, Rd=1k, Vgs=2V → `Vd < Vdd`.
  - `MOSFET/P`: mirror.
  - `DIODE`: forward @ Vsrc=5V через R=1k → `0.2V < Vf < 1.2V`.
  - `OPAMP`: unity-gain buffer Vin=1V → `0.95V < Vout < 1.05V`.
  - `TUBE / TRANSFORMER / LOAD`: import support, но smoke skipped
    (стандартный flow tube models — через T031 fitter, не URL import).
- **F20.** Smoke timeout 15 секунд. Превышение → `SmokeTimeoutError`,
  install rollback.
- **F21.** Smoke fail → `SmokeFailedError(stdout, stderr)`, install
  rollback. `--skip-smoke` пропускает шаг полностью, в KB topic пишется
  `smoke: skipped`.

#### KB sync (Phase 5, T134 Уровень 1)

- **F22.** На каждый successful import создаётся KB topic
  `<knowledge_base_root>/spice.<vendor>.<part>.md` (lowercase) с frontmatter
  и stub-телом. Vendor `unknown` → топик `spice.unknown.<part>.md`.
- **F23.** Duplicate KB topic (existing): silently overwritten (KB topic
  is derived из install state; перезапись отражает свежие headers).
- **F24.** **Не** обновляет `agent.command-routing` per-import — это
  делается один раз в Phase 5 как часть routing-mapping для самого
  slash `/spice-import-url`, не для каждой импортированной модели.

#### CLI / slash (Phase 4)

- **F25.** Новая CLI-группа `efactory spice` с командами:
  - `efactory spice import-url <url> [opts]`
  - `efactory spice import-file <path> [opts]`
  Общие opts: `--vendor=<name>`, `--force`, `--skip-smoke`, `--dry-run`,
  `--json`, `--timeout=SECONDS`, `--max-bytes=N`, `--insecure`,
  `--category=<cat>` (override), `--subcategory=<sub>` (override).
- **F26.** Slash `/spice-import-url <url>` — bridge на `efactory spice
  import-url <url>` (pattern T029/T187). Аргумент — single positional
  URL.
- **F27.** Exit codes (R6 pattern):
  - `0` — ok (import успешен ИЛИ `--dry-run` отработал).
  - `1` — domain-level fail: download 4xx, classification ambiguous,
    duplicate без `--force`, conversion fail, smoke fail.
  - `2` — infrastructure fail: network timeout, DNS, TLS reject, disk
    out-of-space, ngspice unavailable, malformed URL.

### МОЖЕТ

- **M1.** `--category=<cat>` / `--subcategory=<sub>` overrides для
  edge-cases где эвристика классифицирует неверно (debug флаги; agent
  по умолчанию не использует).
- **M2.** `--name=<part>` override для случаев когда `.SUBCKT`/`.MODEL`
  имя модели не совпадает с marketing-name (vendor использовал
  internal-codename).
- **M3.** Future-extension: `efactory spice import-batch <file>` —
  список URL'ов из файла. **Не в-scope T030**, упомянуто как
  пространство для следующей задачи.

### НЕ ДОЛЖНА

- **N1.** Не download'ить **ничего** требующего auth/cookies/SSO/JS-
  render. Если URL вернул HTML (text/html) с признаками login-form —
  hard fail с сообщением «авторизационная страница, не SPICE deck».
- **N2.** Не разворачивать ZIP/TAR/GZ. Если content-type не SPICE — fail.
- **N3.** Не модифицировать **built-in** библиотеку под `src/data/spice-
  models/` (или где она лежит сейчас) — записи **только** в `<user_
  library_root>`.
- **N4.** Не генерировать KiCad-symbols (`.kicad_sym`) — это отдельный
  flow, упоминается в Out of Scope.
- **N5.** Не парсить LTspice-specific расширения (`.lib`-references на
  internal LTspice subcircuits, `.asy`-symbol, encrypted models). При
  встрече encrypted block (`*encrypted ... *endencrypted`) — fail с
  понятным сообщением.
- **N6.** Не делать **batch** (один URL за вызов). M3 — будущее.

## 4. Success Criteria

- **SC1.** Synthetic fixture `tests/data/spice_import/vendor_samples/
  2n3904.lib` (BJT NPN `.MODEL` + минимальный header) → `efactory spice
  import-file <fixture>` → файл `<user_library_root>/bjt/synthetic/
  2N3904.lib` создан, headers инжектированы, smoke OP прошёл, KB topic
  `spice.synthetic.2n3904.md` создан.
- **SC2.** Synthetic fixture с multi-`.SUBCKT` (op-amp pair, e.g.
  imitating TI dual op-amp .lib) → split на два файла, оба установлены,
  оба прошли smoke.
- **SC3.** `--dry-run` на любом fixture'е → stdout содержит план
  (target paths, smoke fixture names, KB topic), exit-code 0, **ноль**
  модификаций на диске (verifiable через snapshot).
- **SC4.** Duplicate без `--force` → exit-code 1, сообщение «already
  installed at <path>»; с `--force` → перезапись, warning в stderr,
  exit-code 0.
- **SC5.** Synthetic encrypted-block fixture → exit-code 1, сообщение
  «encrypted SPICE model, unsupported».
- **SC6.** HTTP fixture через `file://` URL (загрузка через стандартный
  urllib без сети) → end-to-end pipeline проходит идентично `--from-
  file`.
- **SC7.** HTTP 404 (фиктивный server в тесте, либо смоделировано через
  monkey-patch) → exit-code 2, понятное сообщение.
- **SC8.** Classification ambiguity (synthetic deck с 3-пиновой SUBCKT
  без disambiguating cards) → exit-code 1, сообщение с подсказкой
  override-флагов.
- **SC9.** Atomicity: smoke fail (synthetic broken `.MODEL` parameter)
  → exit-code 1, `<target_path>` не существует, `_imports/<sha256>/
  staged/` не promoted.
- **SC10.** Coverage новых модулей ≥ 80%.
- **SC11.** Pre-push 5/5 (ruff / format / mypy / lint-imports / pytest).
- **SC12.** KB sync (T134 Уровень 1+2): KB topic `spice.import-pipeline`
  + routing row + 2 deterministic regression cases в `test_control_
  examples.py`.
- **SC13.** ADR-T030a в `DECISIONS.md` фиксирует: расширение
  `ComponentCategory` (BJT/JFET/MOSFET), `.MODEL`-scanner contract,
  user_library_root-only write policy.
- **SC14.** **Manual acceptance (Vladimir, ad-hoc):** прогон real URL
  TI/Vishay/ON Semi на dev-машине заканчивается успешно. Не блокирует
  PR merge (network-dependent), но фиксируется в `## Doing → Done`
  при closing.

## 5. Key Entities

### Domain layer (`domain/spice_import.py`)

- `ImportSource` (frozen pydantic) — `kind: Literal['url', 'file']`,
  `location: str` (URL или path), `vendor_hint: str | None`.
- `RawImport` — `source: ImportSource`, `bytes_text: str`, `sha256:
  str`, `downloaded_at: datetime`.
- `ModelKind` (StrEnum) — `SUBCKT` | `MODEL`.
- `ParsedModelCard` — `kind: ModelKind`, `name: str`, `body: str` (full
  card incl. continuations), `model_type: str | None` (для `.MODEL` —
  NPN/PNP/D/...), `pins: tuple[str, ...] | None` (для `.SUBCKT`),
  `header_meta: dict[str, str]` (parsed `* foo: bar` headers above this
  card).
- `ClassificationResult` — `category: ComponentCategory`, `subcategory:
  str`, `reason: str` (human-readable, в KB topic), `ambiguous: bool`.
- `ImportPlan` — `raw: RawImport`, `cards: tuple[(ParsedModelCard,
  ClassificationResult), ...]`, `vendor: str`, `target_paths: tuple
  [Path, ...]`.
- `SmokeOutcome` — `card_name: str`, `status: Literal['passed',
  'failed', 'skipped']`, `details: str`.
- `ImportReport` — `plan: ImportPlan`, `installed_paths: tuple[Path,
  ...]`, `smoke_outcomes: tuple[SmokeOutcome, ...]`, `kb_topics: tuple
  [Path, ...]`, `started_at: datetime`, `finished_at: datetime`.

### Domain extensions (`domain/spice_model.py`)

- `ComponentCategory` += `BJT`, `JFET`, `MOSFET`.
- `BjtKind` (StrEnum) — `NPN`, `PNP`.
- `JfetKind` (StrEnum) — `NJF`, `PJF`.
- `MosfetKind` (StrEnum) — `NMOS`, `PMOS`.
- `SpiceModel.bjt_kind` / `jfet_kind` / `mosfet_kind` — typed
  accessors по pattern existing.
- `OpampKind` += `FULL_VENDOR` (was placeholder, теперь реализуется).

### Domain exceptions (`domain/spice_import.py`)

- `SpiceImportError(Exception)` — base.
- `DownloadError(SpiceImportError)` — network/timeout/redirect/TLS/4xx/5xx.
- `ContentRejectedError(SpiceImportError)` — non-SPICE content
  (HTML/binary/encrypted).
- `ClassificationAmbiguousError(SpiceImportError)` — F10 fall-through.
- `ConversionError(SpiceImportError)` — PWRS converter exploded
  (defensive, не ожидается т.к. converter idempotent).
- `ImportDuplicateError(SpiceImportError)` — F18.
- `SmokeFailedError(SpiceImportError)` — F21.
- `SmokeTimeoutError(SpiceImportError)` — F20.
- `KbWriteError(SpiceImportError)` — F22-F23 IO fail.

### Outbound ports (`ports/outbound/spice_import.py`)

- `SpiceModelDownloader` (Protocol): `async def download(source:
  ImportSource, *, timeout_seconds: float, max_bytes: int,
  verify_tls: bool) → RawImport`.
- `SpiceModelClassifier` (Protocol): `def classify_all(raw: RawImport)
  → tuple[(ParsedModelCard, ClassificationResult), ...]`.
- `SpiceSmokeRunner` (Protocol): `async def smoke(*, card:
  ParsedModelCard, classification: ClassificationResult, model_path:
  Path, timeout_seconds: float) → SmokeOutcome`.
- `SpiceKbWriter` (Protocol): `def write_topic(*, report: ImportReport,
  card: ParsedModelCard, classification: ClassificationResult,
  installed_path: Path, kb_root: Path) → Path`.

### Use case (`application/run_spice_import.py`)

- `async def run_spice_import(*, source: ImportSource, user_library_
  root: Path, kb_root: Path, downloader: SpiceModelDownloader,
  classifier: SpiceModelClassifier, smoke: SpiceSmokeRunner, kb_writer:
  SpiceKbWriter, force: bool = False, skip_smoke: bool = False, dry_
  run: bool = False, timeout_seconds: float = 30.0, max_bytes: int =
  1_048_576, verify_tls: bool = True, vendor_override: str | None =
  None, category_override: ComponentCategory | None = None,
  subcategory_override: str | None = None) → ImportReport`.

Поток:
1. `download` → `RawImport`.
2. `classifier.classify_all` → cards + classifications.
3. Apply overrides (vendor/category/subcategory).
4. Compute `target_paths`, build `ImportPlan`.
5. **If `dry_run`** — вернуть report (planned), без модификаций.
6. Detect duplicates → `ImportDuplicateError` если не `force`.
7. Staging dir → headers injection → PWRS conversion → write files.
8. **If not `skip_smoke`** — для каждой card вызвать smoke; на любой
   fail → rollback (delete staging), raise.
9. `os.replace` staging → user_library_root tree (atomic).
10. KB topics write.
11. Build + return `ImportReport`.

### Adapters

- `adapters/outbound/spice_import_http/downloader.py` —
  `UrllibSpiceModelDownloader` (stdlib `urllib.request` +
  `ssl.create_default_context`, redirect handler, body-size enforcer,
  content-type sniff).
- `adapters/outbound/spice_import_classify/classifier.py` —
  `RegexSpiceModelClassifier` (regex-based, без LLM): scanner для
  `.SUBCKT` (reuse существующего pattern из `spice_library.py`) +
  scanner для `.MODEL` cards с continuation `+` lines support.
- `adapters/outbound/spice_import_smoke/runner.py` —
  `NgspiceSmokeRunner` (subprocess wrapper, per-class fixture templates
  inline в коде, ngspice batch mode `-b -o <log>`).
- `adapters/outbound/spice_import_kb/writer.py` —
  `MarkdownSpiceKbWriter` (рендерит markdown topic по шаблону).

### CLI / slash

- `adapters/inbound/cli/app.py` — новая Typer-группа `spice` с
  командами `import-url` и `import-file`.
- `docker/runtime-agent-commands/spice-import-url.md` — slash.
- `composition/build_app.py` — wiring новых ports.

## 6. Assumptions & Constraints

- **A1.** `<user_library_root>` уже сконфигурирован (T006 fix-up,
  Q3) — efactory знает куда писать.
- **A2.** Существующий `FilesystemSpiceModelLibrary` (`spice_library.
  py`) расширяется для поддержки `.MODEL`-cards в дополнение к `.
  SUBCKT`. Это **архитектурное** изменение библиотеки → требует ADR-
  T030a (часть SC13).
- **A3.** ngspice доступен в PATH (в `efactory:linux` всегда; на dev-
  машине Vladimir — apt). На CI без ngspice — smoke pytest cases
  маркируются `pytest.mark.integration`, skip if not available
  (pattern T029 R16).
- **A4.** Default `<user_library_root>/_imports/` — staging + raw
  cache. Размер: ~ KB-per-import, не растёт неограниченно за year (≤
  100 imports).
- **A5.** `unknown` vendor — допустимое значение для случаев когда host
  не маппится и `--vendor` не задан. Не считаем это ошибкой; warning в
  stderr.
- **A6.** Multi-architecture (linux amd64 + arm64 для container,
  linux amd64 для dev) — pipeline pure-Python (stdlib) + ngspice
  subprocess; portability gar.
- **A7.** Все vendor URL'ы в acceptance SC14 — стабильно публичны
  (Vishay/ON Semi/Microchip исторически), но это **manual** acceptance,
  не CI-блокатор.

## 7. Out of Scope

- **OS1. Auth-walled vendors.** TI PSpice .zip за SSO, ADI Models за
  login — не делаем. Workaround: `efactory spice import-file <path>` для
  manually-extracted .lib.
- **OS2. ZIP/TAR/GZ unpacking.** Не разворачиваем archive — `import-
  file` ожидает уже распакованный `.lib`.
- **OS3. KiCad symbol generation (`.kicad_sym`).** Только SPICE-model
  half; symbol attachment — отдельная задача (вне T030, не в
  BACKLOG'е пока).
- **OS4. LTspice encryption / proprietary extensions.**
  `*encrypted...*endencrypted` blocks, `.asy` symbols — hard-fail.
- **OS5. Batch import** (M3 — для будущей задачи).
- **OS6. Auto-update / re-check vendor URL** для newer model — не
  делаем (нет webhook'ов на vendor side, нет cron-флоу).
- **OS7. Symbol disambiguation per netlist.** Если пользователь
  импортирует две модели с одинаковым `.SUBCKT` именем от разных
  vendor'ов (e.g. `OPA1612` у TI и custom fork) — overlay-rule из T006
  (user перекрывает built-in) применяется; cross-vendor collision внутри
  user_library_root → install падает на duplicate-check (F18), пользователь
  делает выбор через `--force` или manually rename file.
- **OS8. LLM-based classification.** F10/F11 — regex-only. LLM-assist
  возможен в будущем, не сейчас (детерминизм важнее ergonomics для CI).
- **OS9. T031 tube curve fitter integration.** Tube models через URL —
  редкий use case (тубы у нас собираются fitter'ом по datasheet точкам);
  тем не менее import-pipeline tube-models технически поддерживает
  (smoke skipped), но не оптимизирован.
- **OS10. Per-class smoke с DC/AC/transient analysis.** Только OP —
  быстро, детерминированно, достаточно чтобы поймать syntax-fail и
  «модель отказывается биасироваться». Полная validation — отдельный
  use case (`/spice-validate <part>` — не в-scope T030).

---

## Clarify (заполняется Claude — self-clarify, Vladimir дал carte
blanche на остальное)

### Open questions

(Vladimir 2026-06-05: «Новых задач не создаем, все делаем в рамках
текущей. Остальное на твое усмотрение» — все ниже разрешены сам Гвидо
с обоснованием. Если Vladimir не согласен — flag перед Phase 1.)

### Resolved (с ответами)

- **R1. Категории BJT/JFET/MOSFET — три отдельных enum'а, не FET-bucket.**
  Vladimir отменил вариант «вынести в отдельную задачу», значит
  расширяем `ComponentCategory` в T030. Выбор «три раздельных»: BJT
  bipolar — фундаментально другой принцип чем field-effect (JFET и
  MOSFET). Унификация в `FET` спрятала бы важное различие (JFET = pn-
  junction gate, MOSFET = insulated-gate); subcategory всё равно
  пришлось бы дискриминировать `NMOS|PMOS|NJF|PJF`. Три enum'а
  читабельнее в коде и в KB-топиках (`category: jfet` vs `category:
  fet/jfet`).

- **R2. Auth-walled vendors — только `import-file`.** Direct-URL
  HTTP/HTTPS GET без cookies. Auth-walled vendors (TI PSpice .zip за
  SSO) — workaround `efactory spice import-file <path>` (US2). В spec
  явно (OS1 + F7). Manual download не считается scope creep — это
  ergonomic fallback.

- **R3. Multi-`.SUBCKT` — split на отдельные файлы.** Соответствует
  существующему контракту `FilesystemSpiceModelLibrary` (один `.SUBCKT`
  на файл, см. spice_library.py:23). Поддержка bundle потребовала бы
  refactor сканера на множественные модели per file, что lifts scope
  значительно. Split simpler, преемственно, идемпотентно.

- **R4. Smoke per-class с реальным ngspice — да.** Vladimir сказал
  «остальное на усмотрение», но acceptance из BACKLOG'а явно требует
  «проходит smoke-симуляцию». Мinimal OP-analysis fixture per class —
  достаточно чтобы поймать syntax-fail и basic-bias-fail; занимает
  <1s per smoke. CI-friendly через `pytest.mark.integration` skip.

- **R5. Vendor extraction — host-mapping table.** Из URL host получаем
  vendor через словарь `_KNOWN_VENDOR_HOSTS = {'www.ti.com': 'ti', ...}`.
  Unknown host → `unknown` с warning. Override `--vendor`. Это
  предсказуемо, не зависит от content-парсинга html-title или
  intelligent guessing. Если в будущем нужно — расширяется тривиально.

- **R6. Header injection — переписываем install-копию, raw download
  остаётся нетронутым.** Headers (`* vendor: ti` etc) injected **в
  install file** (`<user_library_root>/.../OPA1612.lib`), а raw bytes
  лежат в `_imports/<sha256>/raw.lib` без модификаций (audit trail).
  Это разводит «что мы получили» и «как мы интегрировали».

- **R7. Duplicate-detection key — full target path.** Если файл по
  пути `<user_library_root>/bjt/ti/Q2N3904.lib` уже существует — это
  duplicate. Не sha256-сравнение (vendor может обновить модель и тот
  же sha256 не воспроизводится); не имя без vendor (vendor-specific
  модели могут conflict-ить). Полный путь = «есть ли уже файл там, куда
  собирался писать». `--force` всё перезаписывает.

- **R8. KB topic — простой markdown stub.** Структура:
  ```markdown
  ---
  topic: spice.<vendor>.<part>
  source: import
  imported_at: <UTC ISO>
  ---

  # SPICE model: <PART> (<vendor>)

  - **Category:** <category>/<subcategory>
  - **Source URL:** <url> (or `local-file:<path>`)
  - **Install path:** `<rel path from project root>`
  - **SHA256:** <hex>
  - **Smoke:** <passed|failed|skipped>: <details>

  ## Usage

  Symbol→model resolver finds this by part name `<PART>`. To use in a
  schematic, set component `Sim_Model` field to `<PART>`.
  ```
  Stub намеренно lean — у нас и так детектится из install file
  (subcategory, pins, sha256 хранятся в headers); KB topic — для
  agent-friendly discovery + manual notes (пользователь дополняет).

- **R9. Atomicity — staging directory + `os.replace`.** На fail
  staging выкидывается, user-видимая часть не меняется. Это упрощённо
  по сравнению с full-transactional (no need для multi-file
  cross-rollback) — staging директория = единица atomicity.

- **R10. Exit codes 0/1/2 — pattern T029.** Уже устоявшийся в efactory
  pattern. Без redesign. Domain fail = 1, infrastructure = 2.

- **R11. `--insecure` flag — стандарт.** Подобно curl. Warning,
  но не блок. Это для local-test и одноразовых случаев где у vendor
  expired-cert (бывает у academic sites).

- **R12. CLI имя `spice import-url` vs `import spice-url` vs
  `model import` etc.** Выбран `spice` как top-level группа: это уже
  domain-namespace (next to `design`, `bridge`, `project`). Inside —
  `import-url` / `import-file` чтобы parallel с user-mental-model «как
  получить модель: по URL или из файла». Compatible с future `efactory
  spice list`, `efactory spice show <part>` без коллизий.

- **R13. ADR-T030a — yes.** Архитектурное расширение `ComponentCategory`
  (3 новых enum'а) + scanner contract расширение (.MODEL cards) — это
  ADR-worthy (методология dreamteam требует ADR для архитектурных
  изменений). Не три отдельных ADR — один общий «T030 import pipeline
  architecture decisions».

- **R14. Granularity slash vs CLI feature parity.** Slash `/spice-
  import-url` — единственный slash (нет `/spice-import-file` —
  агенту нужен URL flow; manual file flow — для Vladimir CLI use).
  Это сознательная асимметрия: agent не должен предлагать manually-
  downloaded файл (это off-grid action).

---

## Analyze (заполняется Claude после resolved-clarify)

(Pass-1 будет после Vladimir review spec на консистентность. Pre-
emptive analyze ниже, как self-check перед request-for-review.)

### Pre-emptive (self-analyze, 2026-06-05)

#### 🔴 Critical (none anticipated)

(spec собран на устоявшихся patterns T006/T007/T029/T187; новых
архитектурных дыр не вижу.)

#### 🟡 Warning

- **W1. `.MODEL` continuation lines.** `.MODEL` cards могут быть multi-
  line через `+` prefix. Текущий `_SUBCKT_RE` в `spice_library.py:73`
  не учитывает continuation. Для `.MODEL` scanner — обязательно
  поддержать. План: сначала склеить continuation lines в один логический,
  потом распарсить. Тест-fixture с continuation обязательна (Phase 2).

- **W2. `--max-bytes 1 MiB` — достаточно?** Типичная single-model
  `.lib` — 1-20 KiB. TI dual op-amp `.lib` ≤ 30 KiB. 1 MiB — с запасом
  ×30. Encrypted LTspice subcircuit-library может быть больше; но это
  и так N5/N1 reject. Оставляем 1 MiB default.

- **W3. Multi-host redirect — fail by design (F4).** Vishay часто
  redirect'ит `vishay.com → www.vishay.com` (subdomain). Это **тот же
  registered domain**, не cross-host. Нужно correctly классифицировать:
  «cross-host» = разные effective TLD+1, не разные subdomains. План
  Phase 2: использовать `tldextract` library? Нет — extra dependency.
  Простая регулярка `(?:^|\.)([^.]+\.[^.]+)$` для extract effective
  domain. Реализуется ~5 LOC.

- **W4. ngspice smoke детерминистичность.** Один и тот же .MODEL +
  фикстура должны давать одинаковый OP-result. Это true для standard
  ngspice; но `--seed`-based stochasticity (если включена) ломает.
  План: fixture не использует `.noise`/`.tran` с rand-sources, только
  `.op` — deterministic.

- **W5. `OpampKind.FULL_VENDOR` — semantic shift.** Существующий
  `OpampKind.SINGLE_POLE` означает analytical macro-model (T153).
  `FULL_VENDOR` — реальная vendor SUBCKT (T030). Они **разные**
  archetype'а: SINGLE_POLE — для T153 analytical, FULL_VENDOR — для
  vendor import. SchemaCheck при load: SINGLE_POLE → analytical
  loader, FULL_VENDOR → pure SUBCKT. Существующий
  `_detect_tube_subcategory`-style heuristic нужно extend для opamp.

#### 🟢 Note

- **N1.** Phase ordering: TDD-first для domain (Phase 1), затем
  adapters (Phase 2). PWRS converter не трогаем (T168, idempotent).

- **N2.** `tests/data/spice_import/vendor_samples/` фикстуры — purely
  synthetic, written by hand (Phase 0). Не пытаемся копировать real
  vendor `.lib` (потенциальный copyright issue для distribution; это
  paranoid но дёшево избежать).

- **N3.** `efactory spice list` / `show` / `remove` — обвязка вокруг
  user library — out-of-scope T030 (полезные follow-up, но не сейчас).

- **N4.** `OpampKind` уже имеет TODO-комментарий на T030
  (spice_model.py:77). Implementation T030 закрывает этот placeholder
  и убирает комментарий.

- **N5.** KB topic name collision: `spice.unknown.<part>` от разных
  imports с unknown vendor могут collidить (e.g. два «unknown OPA1612»
  от двух разных academic URL'ов). Реальный риск низкий (unknown
  vendor — exceptional); behavior — overwrite, последний import выигрывает.

- **N6.** Logging policy: download + classify + smoke шаги логируются в
  stderr через стандартный logging (level INFO). `--json` — stdout
  reserved для machine output; stderr остаётся human-friendly.

### Acceptance gate перед Phase 1

- Vladimir review spec (этот файл) — accept / amend.
- W1-W5 closeable в Phase 2 без spec изменений (implementation
  details).
- Critical — нет.

Готов к implementation сразу после Vladimir approve (или silent
acceptance после 15 минут review-window — methodology dreamteam
позволяет «silent agree» если spec в clarified состоянии).
