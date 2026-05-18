## Spec: T006 — Tube SPICE model library (framework)

**Статус:** Analyzed
**Дата создания:** 2026-05-18
**Связанные документы:**
- `CONCEPT.md` §2.4 (источники моделей: Koren / Ayumi / Duncan /
  Gleb Zaslavsky), §17 (структура `models/tubes/{koren,ayumi,duncan}/`).
- `BACKLOG.md` → запись T006 (Фаза 1a — MVP-ядро).
- `BACKLOG.md` → T002/T003 (bootstrap скачает upstream-библиотеки в
  каталог моделей), T008 (smoke-симуляция через ngspice).

---

### 1. Overview

T006 — **framework** для библиотеки SPICE-моделей ламп. Не
скачивание готовых библиотек (это bootstrap, T002/T003) и не
ngspice smoke (это T008). Сейчас:

1. Domain — VO `SpiceModel` с метаданными (id, name, tube_type,
   source, format, file_path).
2. Outbound port `TubeModelLibrary` + filesystem adapter, который
   сканирует каталог `data/models/tubes/{source}/`, парсит
   `.lib` / `.inc` / `.cir` файлы (минимум — заголовок и
   `.SUBCKT` блок), отдаёт список / по id.
3. Конвертер Ayumi-формата (`^` → `**`) для ngspice-совместимости.
4. Auto-generated `index.json` (на лету в adapter'е,
   не материализуется на диске — иначе придётся синхронизировать).
5. CLI: `efactory tube list`, `efactory tube show <id>`.
6. 2 generic примера моделей в `data/models/tubes/`: один Koren-style
   triode (`GENERIC_TRIODE`), один Ayumi-style pentode (`GENERIC_PENTODE`).

**Что НЕ делаем сейчас:**

- Скачивание Koren / Ayumi / Duncan upstream — T002/T003 (bootstrap).
- Конкретные русские лампы (6Н2П, 6Н3П, 6П14П, 6П3С) — модели
  добавит пользователь / bootstrap скачает в эту же структуру;
  framework готов.
- ngspice smoke-симуляция — T008.
- Назначение моделей компонентам схемы — T005 (`model_assign` в
  kicad-sim-bridge).

### 2. User Stories

- **«Что у меня есть в библиотеке?»** Как разработчик после
  bootstrap, я хочу `efactory tube list` — таблица всех моделей
  (id, source, type, путь).
- **«Какие параметры у этой модели?»** `efactory tube show
  GENERIC_TRIODE` — выводит содержимое `.SUBCKT` блока + метаданные.
- **«Я скачал Ayumi-модель, как её добавить?»** Положить файл в
  `data/models/tubes/ayumi/<name>.inc`. На `tube list` модель
  автоматически появится после конвертации `^` → `**` (без правки
  файла на диске — преобразование на чтении).
- **Используется bridge'ем (Phase 1a T004+).** Внутренний потребитель
  port'а — pipeline'ы, которые передают SPICE-модели в ngspice
  при симуляции. T006 даёт inventory; T004 даёт runtime-применение.

### 3. Functional Requirements

#### Domain

- ДОЛЖНА: появиться `SpiceModel` (frozen Pydantic VO) в
  `src/domain/spice_model.py`:
  ```python
  class TubeType(StrEnum):
      TRIODE = 'triode'
      TETRODE = 'tetrode'
      PENTODE = 'pentode'
      DUAL_TRIODE = 'dual_triode'

  class ModelSource(StrEnum):
      KOREN = 'koren'
      AYUMI = 'ayumi'
      DUNCAN = 'duncan'
      CUSTOM = 'custom'

  class SpiceModel(BaseModel):
      model_config = ConfigDict(frozen=True)
      id: SpiceModelId       # uppercase ASCII + _ + цифры
      name: str              # человеко-читаемое: «6П14П», «12AX7»
      tube_type: TubeType
      source: ModelSource
      file_path: Path        # абсолютный путь к .lib/.inc/.cir
      subckt_pins: tuple[str, ...]  # P, G, K, H+ — порядок ngspice
  ```
  - `SpiceModelId` — Annotated str: `^[A-Z][A-Z0-9_]+$` (например,
    `GENERIC_TRIODE`, `_6N2P`, `EL34_KOREN`).
  - `subckt_pins` — извлечено из `.SUBCKT <name> <pins>` строки;
    позволяет позже валидировать совместимость с компонентом схемы.

#### Outbound port + adapter

- ДОЛЖНА: `TubeModelLibrary` (Protocol) в
  `src/ports/outbound/tube_model_library.py`:
  ```python
  async def list_all(self) -> list[SpiceModel]: ...
  async def get_by_id(self, model_id: str) -> SpiceModel: ...
  async def read_subckt(self, model_id: str) -> str: ...
  ```
  - `list_all` — все модели из всех источников (sorted by id).
  - `get_by_id` — `TubeModelNotFoundError` если нет.
  - `read_subckt` — содержимое `.SUBCKT` блока **после** конвертации
    `^→**` (для Ayumi). Это то, что вставляется в ngspice нетлист.

- ДОЛЖНА: `FilesystemTubeModelLibrary` в
  `src/adapters/outbound/tube_models/`:
  - Конструктор: `library_root: Path` (например,
    `<repo>/data/models/tubes/`).
  - Сканирует `library_root/{source}/*.{lib,inc,cir}` для каждого
    `source ∈ ModelSource`.
  - На каждый файл: парсит первую `.SUBCKT <name> <pins...>` строку
    (минимум), формирует SpiceModel.
  - `id` = `<uppercase name>` (или fallback из имени файла).
  - `tube_type` — определяется по количеству subckt-пинов:
    - 3 = triode (P, G, K).
    - 4 = tetrode/pentode (P, G2, G, K) или (P, G, K, H).
    - 5 = pentode (P, G2, G, K, H) или dual_triode.
    - 6+ = dual_triode (P1, G1, K1, P2, G2, K2) или other.

    (Простая эвристика; модели с явным `* tube_type: pentode`
    в комментарии — приоритет над эвристикой. См. Clarify #2.)
  - `source` — определяется по subdir (`koren / ayumi / duncan / custom`).
  - `read_subckt`: читает файл, ищет блок `.SUBCKT ... .ENDS`, для
    Ayumi-источника применяет `^ → **`.

#### Конвертер `^ → **`

- ДОЛЖНА: чистая функция `convert_ayumi_to_ngspice(text: str) -> str`
  в `src/adapters/outbound/tube_models/conversion.py`:
  ```python
  def convert_ayumi_to_ngspice(text: str) -> str:
      """Заменить `^` на `**` в SPICE-выражениях.

      Ngspice не понимает `x^y` (PSpice/Ayumi синтаксис), требует
      `x**y` (HSPICE/ngspice). Заменяем во всём тексте — `^` в
      комментариях и литералах не встречается (Spec § 6).
      """
      return text.replace('^', '**')
  ```

- Применяется в adapter'е только для `source == ModelSource.AYUMI`.

#### CLI

- ДОЛЖНЫ: новые Typer subcommand'ы в новом subapp
  `efactory tube`:
  ```
  efactory tube list             # TSV: id<TAB>source<TAB>type<TAB>file_path
  efactory tube show --id ID    # печать subckt-блока + метаданных
  ```
  - Error handling: `TubeModelNotFoundError` → exit 1.

- ДОЛЖНА: session-log integration (T010 паттерн) для `tube.list` и
  `tube.show`.

#### Data — встроенные generic модели

- ДОЛЖНА: появиться `data/models/tubes/koren/GENERIC_TRIODE.lib`
  — generic triode Koren-style (с типовыми параметрами, как
  пример формата):
  ```
  * Generic Koren-style triode model
  * Parameters approximated; replace with vendor data for real designs.
  * Pins: P (plate), G (grid), K (cathode)
  .SUBCKT GENERIC_TRIODE P G K
  Bgg gg 0 V=V(G,K)+0.5
  Bpp pp 0 V=V(P,K)+0.5
  Bx x 0 V=(V(gg)+V(pp)/100)
  ...
  .ENDS
  ```
- ДОЛЖНА: `data/models/tubes/ayumi/GENERIC_PENTODE.inc` — generic
  pentode Ayumi-style (демонстрирует `^` → `**` конвертацию):
  ```
  * Generic Ayumi-style pentode (uses `^` — converted to `**` on read)
  .SUBCKT GENERIC_PENTODE P G2 G K
  ...
  Bipla ipla 0 V=(V(P,K)^1.5)/MU
  ...
  .ENDS
  ```
  (`^1.5` будет преобразован в `**1.5` при `read_subckt`.)

- НЕ ДОЛЖНА: появиться `data/models/tubes/koren/EL34.lib` или
  любые конкретные русские лампы — это пользовательский / bootstrap
  scope. Framework работает с любым файлом подходящего формата.

#### Composition

- ДОЛЖНА: `Settings.tube_library_root: Path` — новое поле,
  default `<repo_data>/models/tubes/` (resolve через
  `Path(__file__).parent / ...`); env override
  `EFACTORY_TUBE_LIBRARY_ROOT`.
- Опционально (см. Clarify #3): второй каталог (user models в
  `<storage_root>/models/tubes/`) — пока scope только built-in.

### 4. Success Criteria

- TDD outside-in.
- 5-step gate зелёный.
- Coverage ≥ 80%.
- **`efactory tube list`** показывает 2 generic модели (GENERIC_TRIODE
  koren + GENERIC_PENTODE ayumi).
- **`efactory tube show --id GENERIC_PENTODE`** печатает SUBCKT-блок,
  в котором `^` уже преобразован в `**` (Ayumi conversion).
- **`efactory tube show --id GENERIC_TRIODE`** печатает SUBCKT
  без изменений (Koren — изначально ngspice-compatible).
- **Round-trip:** `list_all → get_by_id(id) for id in ...` —
  возвращает те же SpiceModel.
- **Adapter ignores non-spice files** в каталоге (например, README.md).
- **Session log** содержит запись `tube.list` / `tube.show`.

### 5. Key Entities

- `SpiceModel` — frozen VO (id, name, tube_type, source, file_path,
  subckt_pins).
- `SpiceModelId` — Annotated str (uppercase ASCII + цифры + `_`).
- `TubeType` — StrEnum (triode | tetrode | pentode | dual_triode).
- `ModelSource` — StrEnum (koren | ayumi | duncan | custom).
- `TubeModelLibrary` (Protocol) + `FilesystemTubeModelLibrary`
  (adapter).
- `TubeModelNotFoundError` — контрактное исключение порта.
- `convert_ayumi_to_ngspice` — чистая функция в adapter (Ayumi `^`
  → ngspice `**`).
- CLI subapp `tube` — `list`, `show`.

### 6. Assumptions & Constraints

- SPICE syntax: `.SUBCKT name p1 p2 ... .ENDS` — стандарт; первая
  не-комментарий строка с `.SUBCKT` определяет модель.
- `^` в SPICE-моделях встречается только как exponent в expression
  (`V(P,K)^1.5`); не в комментариях (комментарии — `*` или `;`),
  не в литералах. Глобальная замена `^→**` безопасна (Resolved #4
  кросс-проверкой на нескольких реальных Ayumi моделях — НЕ
  делаем сейчас; вынесли в pre-T002 audit на момент скачивания
  upstream-библиотек).
- Encoding всех файлов — UTF-8 (ASCII-safe).
- Single-process CLI; нет конкурентного редактирования библиотеки.
- `data/models/tubes/` — часть дистрибутива (как `data/templates/`
  в hatchling). Пакетируется через `[tool.hatch.build.targets.wheel]
  include` (по необходимости — Clarify #1).
- 2 generic модели — не точные физически; их назначение —
  демонстрация формата и pipeline. Реальные параметры приедут с
  bootstrap.

### 7. Out of Scope

- **Скачивание upstream-библиотек** (Koren PDF / Ayumi GitHub /
  Duncan amp pages) — bootstrap T002/T003. Adapter готов читать
  любые файлы в `data/models/tubes/{source}/`.
- **Российские лампы (6Н2П, 6П14П и пр.).** Параметры найдутся
  при bootstrap или вручную; framework принимает.
- **Smoke ngspice симуляция** — T008. Сейчас только парсинг
  заголовка `.SUBCKT`, не запуск.
- **Назначение модели компоненту схемы.** T005 `model_assign` в
  kicad-sim-bridge.
- **Поиск по частичному имени** (`efactory tube search 6P14P` →
  fuzzy match). Сейчас exact id only; CLI grep по `tube list`
  достаточен.
- **CRUD моделей через CLI** (`tube add` / `tube delete`). Сейчас
  модели = файлы; пользователь манипулирует ими через FS. CLI
  предоставит CRUD позже, если понадобится.
- **Версионирование моделей** (`GENERIC_TRIODE_v1` vs
  `GENERIC_TRIODE_v2`). Сейчас один id на файл. Версии = разные id.
- **User-models поверх built-in** (`<storage_root>/models/tubes/`
  как overlay). Clarify #3.
- **Валидация SPICE синтаксиса.** Просто читаем `.SUBCKT ... .ENDS`,
  не проверяем семантику. ngspice сам ругнётся при симуляции.
- **Konvertor PSpice → ngspice** в полном объёме (есть много
  отличий: TEMP node, .MODEL syntax). Сейчас только `^ → **` для
  Ayumi. Полная конвертация — отдельная задача когда найдём
  конкретные incompatibilities в реальных моделях.
- **Duncan модели.** В Out of Scope как и Koren upstream скачивание
  (T002). Каталог `duncan/` создаётся пустой структуры ради.

---

### Clarify (заполняется после draft, перед implement)

#### Open questions

##### 1. `data/models/tubes/` — как пакетировать в wheel?

Hatchling по умолчанию включает только `src/`. Чтобы при
`pip install efactory` data попадали в установку, нужно либо:

- **(A)** Включить через `[tool.hatch.build.targets.wheel.force-include]`
  или `[tool.hatch.build.include]`.
- **(B)** Положить data внутри `src/` (например,
  `src/data/models/tubes/`).
- **(C)** Resolve через `importlib.resources` (стандарт PEP 660).

**Предлагаемый дефолт:** **(B)** — `src/data/models/tubes/`. Hatchling
включает автоматически; relative path `Path(__file__).parents[N]
/ data / models / tubes` устойчив. Чисто без extra
`pyproject.toml` magic.

##### 2. Tube type detection: pin count или header comment?

`.SUBCKT GENERIC_TRIODE P G K` — 3 пина = triode. Но
`.SUBCKT EL34 P G2 G K H` — 5 пинов; pentode (с heater) или
tetrode (с heater)? Без header — эвристика расплывчата.

- **(A)** Только эвристика по пинам. Просто, иногда неточно.
- **(B)** Парсить `* tube_type: pentode` из комментариев. Точно,
  требует convention.
- **(C)** Комбо: header > эвристика (fallback).

**Предлагаемый дефолт:** **(C)**. Header строка `* tube_type:
pentode` overrides. Если нет — fallback (3 пина → triode, 4-5 →
pentode, 6+ → dual_triode). Для наших generic моделей укажем
header — будет всегда точно; для upstream после T002 audit.

##### 3. User models поверх built-in (overlay)?

Built-in: `<repo>/src/data/models/tubes/`. User-добавленные:
`<storage_root>/models/tubes/` (после T002 bootstrap или
вручную).

- **(A)** Только built-in. Пользователь хочет добавить —
  patch'ит src. Не для production.
- **(B)** Overlay: adapter сначала сканирует built-in, потом user;
  user-models с тем же id перезаписывают built-in.

**Предлагаемый дефолт:** **(A)** для Phase 1a — built-in only.
User overlay — отдельная задача (когда у нас есть реальный
use case: пользователь хочет переопределить параметры конкретной
лампы под свой ламповый экземпляр).

##### 4. `^ → **` замена — глобальная или только в expression?

`text.replace('^', '**')` — глобально. Риск: если когда-то в
комментарии встретится `^` — будет искажен. Но Ayumi-формат не
использует `^` в комментариях (использует `*` или ничего).

- **(A)** Глобальная замена. Простая.
- **(B)** Только в строках `B... V=...` (where expression appears).
  Сложнее, точнее.

**Предлагаемый дефолт:** **(A)** глобально. Audit на реальных
Ayumi-моделях при T002.

##### 5. `SpiceModelId` формат

`^[A-Z][A-Z0-9_]+$` — uppercase, начинается с буквы. Достаточно
для большинства моделей (`EL34`, `6N2P`, `12AX7`, `GENERIC_TRIODE`).

Но `6N2P`, `6P14P`, `12AX7` — начинаются с цифры. Если требуем
буквы первой — fallback на `_6N2P`? Или ослабить regex до
`^[A-Z0-9][A-Z0-9_]+$`?

**Предлагаемый дефолт:** ослабить до `^[A-Z0-9][A-Z0-9_]+$`
(позволяет цифру первой). Это покрывает реальные имена ламп.
Префикс `_` некрасив.

##### 6. CLI `tube show` — что печатать?

Минимум — содержимое .SUBCKT блока (raw). Полезно дополнить
метаданными: id, source, tube_type, file_path.

**Предлагаемый дефолт:** метаданные сверху + пустая строка +
содержимое subckt блока. Без раздельных секций — это вывод для
человека, удобно скопировать.

##### 7. Phasing

- **(A) Один phase.** Размер ~T010.
- **(B) Два phase:** (1) domain + port + adapter + data; (2) CLI + e2e.

**Предлагаемый дефолт:** **(A) один phase**.

##### 8. Что если `data/models/tubes/` пуст (отсутствует source dir)?

- **(A)** `list_all` возвращает `[]`. CLI печатает «No tube models
  found.»
- **(B)** `mkdir parents=True exist_ok=True` для всех source
  поддиректорий на adapter init.

**Предлагаемый дефолт:** **(A)** — pure read-only. Adapter не
должен mutating сторону каталога без причины. CLI печатает
понятное сообщение.

##### 9. Что если несколько моделей с тем же id?

Например, кто-то положил `GENERIC_TRIODE.lib` и в `koren/`, и в
`custom/` — оба парсятся как `id=GENERIC_TRIODE`.

- **(A)** Последний выигрывает (по порядку источников).
- **(B)** Ошибка: дубликат id.
- **(C)** Хранить оба, идентификатор = `<source>/<id>`.

**Предлагаемый дефолт:** **(B)** — `TubeModelLibraryDuplicateError`
при `list_all`. Чисто, заставляет пользователя выбрать. С user
overlay (Clarify #3) можно потом перейти на (A).

##### 10. Smoke тест ngspice — пропустить или сделать?

`needs_ngspice` skip-аналог, если `ngspice` нет на PATH.
Проверка: загрузить SUBCKT в ngspice, симулировать `.OP`, не
упасть.

**Предлагаемый дефолт:** **пропустить** в T006. T008 явно про
ngspice анализы; добавим тогда. Сейчас acceptance — только
парсинг и read_subckt.

---

### Resolved

Разработчик подтвердил 9 из 10 дефолтов; поправил Q1
(2026-05-18). Кратко:

1. **Data в репо** — **(A) `data/models/tubes/` в корне** +
   `[tool.hatch.build.targets.wheel.force-include]` для wheel
   packaging. Чище: `src/` — только код, data — отдельно.
   Resolution path в development: `Path(__file__).resolve().parents[N]
   / 'data' / 'models' / 'tubes'` от `composition/settings.py`.
2. **Tube type detection** — **(C) комбо**: header `* tube_type: X`
   приоритет, fallback — pin count heuristic.
3. **User overlay** — **(A) только built-in** для Phase 1a.
4. **Ayumi `^→**`** — **(A) глобальная замена** `text.replace`.
5. **`SpiceModelId` regex** — ослаблен до `^[A-Z0-9][A-Z0-9_]+$`
   (допускает цифру первой: `6N2P`, `12AX7`).
6. **CLI `tube show`** — метаданные + пустая строка + raw SUBCKT.
7. **Phasing** — **(A) один phase**.
8. **Пустой `data/models/tubes/`** — `list_all` возвращает `[]`,
   CLI «No tube models found.».
9. **Дубликат id** — **(B)** `TubeModelLibraryDuplicateError`
   при `list_all` (fail-fast, заставляет выбрать).
10. **ngspice smoke** — пропускаем (T008).

---

### Analyze

#### 🔴 Critical

##### C1. Resolution `data/` path при `pip install`

Hatchling `force-include = {"data/models" = "data/models"}` кладёт
файлы в `<site-packages>/data/models/...`. От кода efactory —
`Path(__file__).parents[N]` ведёт в `site-packages`, но не
обязательно ровно туда.

В **development mode** (editable install через `uv sync`) —
`<repo>/src/composition/settings.py.parents[3]` =
`<repo>` → `<repo>/data/...` работает.

В **wheel install** — `composition/` лежит в site-packages, `data/`
тоже в site-packages, но `parents` от `composition/settings.py`
может вывести не туда (в site-packages нет `<repo>` корня).

**Резолюция:** для Phase 1a — development mode единственный
поддерживаемый сценарий (нет ни `pip install`, ни production
deploy). Default factory резолвит relative-path и работает для
editable install (`uv sync` именно это и даёт). Env override
(`EFACTORY_TUBE_LIBRARY_ROOT`) — для любых других сценариев.
Production resolution (`importlib.resources` через временный
package или packaged data) — отдельная задача, когда понадобится.

##### C2. SPICE parsing — устойчивость к разному стилю файлов

`.SUBCKT` строки бывают:
- `.SUBCKT NAME P G K` — стандартный.
- `.subckt name p g k` — lowercase.
- `.SUBCKT NAME P G K PARAMS: foo=1 bar=2` — с параметрами.
- `.SUBCKT NAME\n+ P G K` — continuation (`+` continuation lines).

**Резолюция:** v1 поддерживаем только **первую** форму (uppercase
`.SUBCKT NAME P1 P2 ... [PARAMS:...]` на одной строке, lowercase
`.subckt` через `re.IGNORECASE`). Continuation lines не поддерживаем;
если встретится в реальной модели — добавим. Документируется как
known limitation в docstring adapter'а.

##### C3. SpiceModelId vs filename mismatch

Файл `EL34_KOREN.lib` содержит `.SUBCKT EL34 P G2 G K`. Что
становится `id`?

- `id = .SUBCKT name` = `EL34` (домен модели).
- `id = filename stem` = `EL34_KOREN`.

Разные источники могут иметь одну и ту же лампу с разными
параметрами — отличие должно быть в id.

**Резолюция:** **`id = filename stem` (uppercase)**. `name` поле
SpiceModel = `.SUBCKT name` (для использования в нетлисте
ngspice). Это решает дубликаты: два файла `EL34_KOREN.lib` и
`EL34_AYUMI.inc` дают два id; внутренний `.SUBCKT name` может
быть одинаковым (`EL34`) — это OK, ngspice использует тот, что в
текущем нетлисте.

#### 🟡 Warning

##### W1. CLI `tube show` — id vs name пользователю

Из C3 id = filename stem; name = SUBCKT name. Если пользователь
видит модель в `tube list` как `EL34_KOREN`, а вставлять в схему
нужно `EL34` (по name), это путает.

**Резолюция:** CLI `tube show` явно печатает оба:
```
id: EL34_KOREN
name: EL34       (use this in your ngspice netlist)
```

##### W2. `convert_ayumi_to_ngspice` глобальная замена

`*` начало комментария + `^` — нормально. Например:
```
* Power: P^2 / R = U * I  (^ in comment — risky)
```

Это редкий случай (Ayumi-модели в комментариях обычно нет ^), но
возможный. Документируем как known limitation; реальные модели —
audit на bootstrap.

##### W3. CLI `tube list` order

`sorted(models, key=lambda m: m.id)` — alphabetical. Альтернатива —
группировать по source. Для v1 alphabetical достаточно (CLI grep
по source легко).

#### 🟢 Note

##### N1. Adapter: ленивая загрузка `read_subckt`

`list_all` парсит только заголовок (`.SUBCKT` line) для метаданных.
Содержимое SUBCKT блока — только по `read_subckt(id)` (отдельный
read).

##### N2. CLI subapp namespace

`efactory tube ...`. Не `efactory model ...` — model более общий
термин (могут быть модели op-amp, диодов и т.д.). Сейчас фокус —
лампы.

##### N3. Header convention для `* tube_type:`

```
* tube_type: pentode
.SUBCKT EL34 P G2 G K
```

Простая регулярка `^\* tube_type:\s*(\w+)$` (case-insensitive).
Документируем в README + docstring adapter'а.

##### N4. `data/models/tubes/{koren,ayumi,duncan,custom}/` пустые subdirs

`duncan/` создаётся пустой (CONCEPT упоминает, но в T006 не
заполняется). Git не любит пустые каталоги — кладём
`.gitkeep` файл. Adapter их игнорирует (только `.lib` / `.inc` /
`.cir`).

##### N5. Hatchling force-include syntax

```toml
[tool.hatch.build.targets.wheel.force-include]
"data/models" = "data/models"
```

Это включит `data/models/` в wheel. В editable install (uv sync)
не нужно — uv делает editable через `.pth`-файл.

##### N6. Composition wire

```python
tube_library = FilesystemTubeModelLibrary(settings.tube_library_root)
return build_app(..., tube_library=tube_library, ...)
```

##### N7. SpiceModel.subckt_pins purpose

Зачем хранить pins в VO? Для будущей валидации `model_assign` (T005):
проверить, что компонент схемы имеет тот же набор pins (например,
триод в схеме = 3 pin → совместим с триодными моделями).
Сейчас не используется, но дешево хранить.

##### N8. tube_type fallback heuristic

```python
def _detect_tube_type(pins: tuple[str, ...]) -> TubeType:
    n = len(pins)
    if n == 3: return TubeType.TRIODE
    if n in {4, 5}: return TubeType.PENTODE  # tetrode редок
    if n >= 6: return TubeType.DUAL_TRIODE
    raise ValueError  # 0/1/2 пина — невалидно для лампы
```

Очень грубо. С header override — точнее.

##### N9. `models/index.json` материализация

В Spec § 1 написано «auto-generated на лету в adapter, не
материализуется». Это правильно: index.json на диске нужно
синхронизировать с реальными файлами, что лишний шаг.
`list_all()` достаточно для inventory.

CONCEPT упоминает `index.json` как часть structure — это
исторический артефакт PSpice/Duncan, когда index был ручной.
У нас filesystem-scan на каждом `list_all` — приемлемая стоимость
для десятков файлов.

##### N10. Phasing внутри одного PR

Хоть один phase — порядок коммитов на ветке:
1. domain + ports.
2. adapter + converter + tests.
3. data/ + pyproject force-include.
4. composition + CLI.
5. e2e + closing BOARD.

Squash-merge собирает в один main commit.
