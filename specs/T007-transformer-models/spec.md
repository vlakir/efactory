## Spec: T007 — Transformer / load SPICE model library

**Статус:** Analyzed
**Дата создания:** 2026-05-18
**Связанные документы:**
- `CONCEPT.md` §13 (BACKLOG задача T007).
- `BACKLOG.md` → запись T007 (Фаза 1a — MVP-ядро).
- `specs/T006-tube-library/spec.md` — symmetric структура для tubes;
  T007 повторяет паттерн адаптера + CLI + Settings.
- T008 (предстоящий) — ngspice анализы; OPT + speaker нужны для
  AC sweep SE-усилителя.

---

### 1. Overview

T007 — **framework** для библиотеки выходных трансформаторов и
нагрузок (loads). Симметричен T006 (tubes), но в отдельном sub-package
и port'е. Не объединяем в общий `ComponentModelLibrary` —
дублирование 200 строк не оправдывает scope-разрастание; если позже
понадобится generalization, сделаем отдельным рефакторингом.

Включает:
1. Domain.TransformerModel — frozen VO (id, name, kind, file_path,
   subckt_pins).
2. TransformerKind enum (`opt` | `load`; расширим в будущем —
   `pt` power transformer, `it` interstage, `choke`).
3. Outbound port TransformerLibrary + filesystem adapter.
4. CLI `efactory transformer list / show --id`.
5. Settings.transformer_library_root + user overlay (паттерн T006).
6. 4-5 example моделей в `data/models/transformers/`:
   - `opt/OPT_SE_5K_8.lib` — SE output transformer 5kΩ:8Ω (для 300B/EL84).
   - `opt/OPT_PP_6K6_8.lib` — Push-Pull 6.6kΩ:8Ω (для EL34 PP).
   - `load/SPEAKER_8OHM.lib` — 8Ω speaker с mechanical резонансом.
   - `load/SPEAKER_8OHM_RES.lib` — чисто резистивная нагрузка
     (для simple AC sweep).
   - `load/SPEAKER_4OHM.lib` — 4Ω вариант.

### 2. User Stories

- **Симуляция SE-усилителя.** Как разработчик, я выбрал 300B + OPT +
  speaker; хочу `efactory transformer list` чтобы увидеть какие OPT
  доступны, потом `tube show --id 300B` + `transformer show --id
  OPT_SE_5K_8` → дальше bridge (T004) собирает netlist для ngspice.
- **Замена нагрузки.** Сменить 8Ω на 4Ω для тестирования усилителя:
  `transformer show --id SPEAKER_4OHM`.
- **Свои трансформаторы.** Положить файл в
  `~/.local/share/efactory/models/transformers/opt/MY_TANGO.lib`
  → виден в `tube list` (через user overlay).

### 3. Functional Requirements

#### Domain

- ДОЛЖНА: `TransformerModel` (frozen Pydantic VO) в
  `src/domain/transformer_model.py`:
  ```python
  class TransformerKind(StrEnum):
      OPT = 'opt'    # output transformer
      LOAD = 'load'  # speaker / dummy load

  class TransformerModel(BaseModel):
      model_config = ConfigDict(frozen=True)
      id: str  # ^[A-Z0-9][A-Z0-9_]+$ (тот же regex что SpiceModelId)
      name: str
      kind: TransformerKind
      file_path: Path
      subckt_pins: tuple[str, ...]
      is_user: bool = False
  ```
  - Не переиспользуем `SpiceModelId` напрямую, копируем regex
    (мини-дублирование ради независимости domain от tube-specifics).

#### Outbound port

- ДОЛЖНА: `TransformerLibrary` (Protocol) в
  `src/ports/outbound/transformer_library.py`:
  ```python
  async def list_all(self) -> list[TransformerModel]: ...
  async def get_by_id(self, model_id: str) -> TransformerModel: ...
  async def read_subckt(self, model_id: str) -> str: ...
  ```
- ДОЛЖНЫ: контрактные исключения `TransformerNotFoundError`,
  `TransformerLibraryDuplicateError`.

#### Adapter

- ДОЛЖНА: `FilesystemTransformerLibrary` в
  `src/adapters/outbound/transformer_models/`:
  - Конструктор: `library_root: Path, user_library_root: Path | None`.
  - Сканирует `library_root/{kind}/*.{lib,inc,cir}` для каждого
    `kind ∈ TransformerKind`.
  - Парсит первую `.SUBCKT` строку (паттерн T006).
  - Kind определяется по subdir (`opt` / `load`).
  - User overlay по тому же принципу (T006 fix-up Q3).

#### Data

`data/models/transformers/{opt,load}/`:

- **`opt/OPT_SE_5K_8.lib`** — SE output 5kΩ:8Ω.
  ```
  .SUBCKT OPT_SE_5K_8 P1 P2 S1 S2
  Lp P1 P2 50
  Ls S1 S2 0.08
  K1 Lp Ls 0.9995
  Rp_dcr P1 P3 200
  Rs_dcr S1 S3 0.3
  Cps P1 S1 200p
  .ENDS
  ```
- **`opt/OPT_PP_6K6_8.lib`** — Push-Pull 6.6kΩ:8Ω, center-tapped
  primary.
- **`load/SPEAKER_8OHM.lib`** — voice coil DCR + L + parallel
  RLC resonator (~70 Hz mechanical resonance).
- **`load/SPEAKER_8OHM_RES.lib`** — чисто `R 8` для AC sweep.
- **`load/SPEAKER_4OHM.lib`** — 4Ω аналог.

Параметры — typical для бюджетного OPT (Hammond 1627A class) и
типичного hi-fi speaker (Sd ~250 cm², Qts ~0.4).

#### CLI

- ДОЛЖНЫ: новые Typer subcommand'ы:
  ```
  efactory transformer list           # TSV: id<TAB>library<TAB>kind<TAB>file_path
  efactory transformer show --id ID   # метаданные + raw SUBCKT
  ```
- Session-log integration (`transformer.list`, `transformer.show`).

#### Composition / Settings

- ДОЛЖНА: `Settings.transformer_library_root: Path` (default
  `<repo>/data/models/transformers/`, env
  `EFACTORY_TRANSFORMER_LIBRARY_ROOT`).
- ДОЛЖНА: `Settings.user_transformer_library_root: Path` (default
  `<storage_root>/models/transformers/`, env
  `EFACTORY_USER_TRANSFORMER_LIBRARY_ROOT`).
- ДОЛЖНА: composition wire FilesystemTransformerLibrary в build_app.

### 4. Success Criteria

- TDD outside-in.
- 5-step гейт зелёный, coverage ≥ 80%.
- `efactory transformer list` показывает 5 built-in моделей.
- `efactory transformer show --id OPT_SE_5K_8` печатает SUBCKT.
- Adapter валидно парсит kind из subdir, header `* kind: opt` priority.
- User overlay работает (test).
- Integration со звуковым: ngspice симуляция SE-усилителя на 300B +
  OPT_SE_5K_8 + SPEAKER_8OHM_RES → отложено в **T008** (требует
  SPICEBridge).

### 5. Key Entities

- `TransformerModel` — frozen VO.
- `TransformerKind` — StrEnum (opt | load).
- `TransformerLibrary` (Protocol) + `FilesystemTransformerLibrary`
  (adapter).
- `TransformerNotFoundError` / `TransformerLibraryDuplicateError`.
- `Settings.transformer_library_root` + `user_*`.

### 6. Assumptions & Constraints

- SPICE syntax — стандартный, тот же что для tubes.
- Параметры моделей — typical-sample (Hammond 1627A class OPT,
  generic hi-fi speaker); не для production — там по результатам
  измерений реального трансформатора.
- Single-user CLI; concurrent чтение библиотеки не защищаем.

### 7. Out of Scope

- **Power transformers (`pt/`)** — отдельный задача (после T049
  PSU wizard).
- **Interstage transformers (`it/`)** — когда будет конкретный
  use case.
- **Choke** — отдельная задача с T053 (mag_design_choke).
- **OPT design wizard** (расчёт под конкретную лампу/выход) — T052
  (`mag_design_transformer`) в Фазе 5.
- **Mag-параметры из FEMM** — T055 в Фазе 5.
- **Generalization SpiceModel + TransformerModel в общий
  ComponentModel** — отдельный рефакторинг (если потребуется).
  Сейчас параллельная структура.
- **ngspice smoke** — T008.

---

### Clarify (заполняется после draft)

#### Open questions

##### 1. Generalization domain `SpiceModel` vs duplicate `TransformerModel`?

T006 ввёл `SpiceModel` (tube-specific: tube_type / source enum).
T007 нужен трансформатор/нагрузка. Варианты:

- **(A) Дублирование** — отдельный TransformerModel + Library +
  adapter + CLI. Параллельная структура. Чисто, но 80% копипасты.
- **(B) Generalization** — обобщить SpiceModel: `category: ComponentCategory`
  (tube / transformer / load), убрать tube_type → subcategory: str. Один
  port + adapter + CLI с `--category` filter.

**Предлагаемый дефолт:** **(A) дублирование** — generalization
важна, но это отдельный рефакторинг T006 + T007; здесь scope
T007. Если в Фазе 1a добавятся ещё категории (cables, connectors) —
generalize отдельной задачей.

##### 2. Subdir структура `data/models/transformers/`

- `opt/` — output transformers.
- `load/` — speakers + dummy loads.

В будущем (Фаза 5): `pt/`, `it/`, `choke/`.

**Предлагаемый дефолт:** только `opt/` и `load/` в T007.
Пустые `pt/`, `it/`, `choke/` не создаём — заведутся со своими
задачами.

##### 3. Speaker как «transformer»?

Категориально speaker — не трансформатор, а нагрузка. Но в SPICE
это `.SUBCKT SPEAKER ... .ENDS` — синтаксически identical. Положить
в `transformers/load/` практично (одна библиотека = одна абстракция
"passive output component"), но названия путают.

- **(A)** `data/models/transformers/{opt,load}/` — одна библиотека.
- **(B)** `data/models/loads/SPEAKER_*.lib` отдельно, разделить
  на 2 port'а.

**Предлагаемый дефолт:** **(A) одна библиотека**. Speaker — load
для OPT secondary; они работают вместе в pipeline (OPT primary
→ tube anode, secondary → speaker). Один CLI `efactory transformer
list/show` покрывает оба.

##### 4. CLI namespace `transformer` vs `passive` vs `output`?

`efactory transformer list` — но speaker не трансформатор.
`efactory passive list` — generic, но широко.
`efactory output list` — output stage, но узко.

**Предлагаемый дефолт:** **`transformer`** — простое, понятное, по
BACKLOG-описанию ("модели трансформаторов"). Speaker как load —
часть "output stage", документируется.

##### 5. Параметры OPT — типовые или конкретный datasheet?

- **(A) Generic typical** — параметры реального Hammond 1627A или
  Tango XE-20S как ориентир. Без претензии на конкретный fit.
- **(B) Vendor-specific** — `OPT_HAMMOND_1627A.lib`, `OPT_TANGO_XE20S.lib`.
  Лицензионные / IP риски (vendors могут не разрешать SPICE-публикацию).

**Предлагаемый дефолт:** **(A) generic typical**. Имена generic
(`OPT_SE_5K_8`, `OPT_PP_6K6_8`) — не привязаны к vendor. Параметры
в pattern «typical для класса». Vendor-specific — пользователь добавит
сам через user overlay.

##### 6. Phasing

- **(A) Один phase** — задача компактная.
- **(B) Два phase** — domain/port/adapter; data + CLI.

**Предлагаемый дефолт:** **(A) один phase**.

---

### Resolved

Разработчик подтвердил 4 дефолта; **поправил Q1 и Q3** (2026-05-18).

1. **Generalize SpiceModel** — **(B) generalization** вместо (A)
   дублирования. Рефакторинг T006: `SpiceModel` получает поля
   `category: ComponentCategory` (tube/transformer/load) и
   `subcategory: str`. Один port `SpiceModelLibrary`, один adapter
   `FilesystemSpiceModelLibrary`. CLI остаётся раздельным
   (`tube`/`transformer`/`load` subapps), внутри фильтрует по
   category.
2. **Subdir структура** — дефолт **(A)** `transformers/{opt}/`,
   `loads/{speaker,resistive}/` (Q3 отделяет loads).
3. **Speaker отдельно** — **(B)** `data/models/loads/`,
   не `transformers/load/`. Семантически чище: load это load,
   transformer это transformer.
4. **CLI namespace** — три отдельных subapp: `efactory tube`,
   `efactory transformer`, `efactory load`.
5. **Параметры моделей** — **(A) generic typical** (Hammond 1627A
   class OPT, typical hi-fi speaker).
6. **Phasing** — **(A) один phase** в рамках одного PR (рефакторинг
   T006 + добавление T007 категорий вместе; squash-merge даст один
   коммит в main).

#### Структура `data/models/` после рефакторинга

```
data/models/
├── tubes/
│   ├── koren/...      # source-based subdir
│   ├── ayumi/...
│   ├── duncan/...
│   └── custom/...
├── transformers/
│   └── generic/...    # vendor-based subdir (generic, hammond, tango, ...)
└── loads/
    └── generic/...
```

#### Sub-directory семантика

Subdir1 = `category`, Subdir2 = `source`. Унифицировано: всегда
2-уровневая структура. Для tubes source значит fit (Koren/Ayumi/Duncan/
Custom). Для transformers/loads source значит vendor/origin
(generic/hammond/tango/custom).

Subcategory (tube_type / transformer_kind / load_kind) определяется
header `* subcategory: <value>` либо pin-эвристикой (для tubes уже
работает).

#### Backward compat header

Adapter ищет в header `* subcategory:` И `* tube_type:` (legacy
T006). Старые ~50 tube файлов не трогаем. Header для transformers /
loads — обязателен или fallback pin-эвристика per-category (пока
тривиально: opt всегда 4 pin, speaker 2 pin — но header всё равно
обязателен для discrimination от 2-pin half-wave rectifier).

---

### Analyze

#### 🔴 Critical

##### C1. Backward compat для T006 tube models

После рефакторинга adapter ищет `subcategory` поле в SpiceModel.
Старые tube файлы (~50) содержат header `* tube_type: triode|pentode|
rectifier|...`. Adapter должен поддержать оба header'а: новый
`* subcategory:` (для transformers/loads) и legacy `* tube_type:`
(для tubes, без изменения файлов).

**Резолюция:** в `_parse_header` ищем оба регекспа. Если найден
`tube_type` — это subcategory. Старые файлы продолжают работать.
Новые файлы используют `subcategory`. Документируется в README.

##### C2. Pin-эвристика для transformer/load

Сейчас 2-pin → RECTIFIER (T006 expansion). Speaker 2-pin тоже —
будет ошибочно определён как RECTIFIER без header.

**Резолюция:** **header обязателен** для не-tube моделей. Pin-
эвристика остаётся tube-only (применяется только для category=TUBE
файлов). Adapter: для файлов в `transformers/`/`loads/` subdir
header `* subcategory:` обязателен; иначе `SpiceModelInvalidError`.

Для tubes pin-эвристика — fallback (как раньше).

##### C3. Settings backward incompatible change

`EFACTORY_TUBE_LIBRARY_ROOT` и `EFACTORY_USER_TUBE_LIBRARY_ROOT`
заменяются на `EFACTORY_LIBRARY_ROOT` и `EFACTORY_USER_LIBRARY_ROOT`.
Существующие тесты используют `EFACTORY_TUBE_LIBRARY_ROOT` — все
обновятся в этом PR. Production пока нет, поэтому breaking change
безопасен.

**Резолюция:** обновить все references в одном PR. Документировать
в commit message.

#### 🟡 Warning

##### W1. SpiceModel.tube_type как @property

После рефакторинга `tube_type` становится property с category guard:

```python
@property
def tube_type(self) -> TubeType:
    if self.category is not ComponentCategory.TUBE:
        msg = f'Not a tube: category={self.category}'
        raise ValueError(msg)
    return TubeType(self.subcategory)
```

Старый код, который использовал `model.tube_type` для tube,
продолжает работать. Для transformer вызов `tube_type` сейчас даст
ValueError — корректное поведение.

##### W2. CLI помощь и `tube_type` колонка

Старый `tube list` показывал колонку `tube_type` (`triode`/`pentode`).
В новой версии для CLI tube subapp выводим `subcategory` под именем
`type` (общее для всех category). Изменение колонки display
backward-incompatible для скриптов, парсящих TSV.

**Резолюция:** оставить колонку как было (header содержит type как
строку). Скриптам не должно быть разницы — значения те же.

##### W3. ModelSource.GENERIC семантика

Для tubes GENERIC не используется (есть koren/ayumi/duncan/custom).
Для transformers/loads GENERIC — основной source. Добавление в один
enum для всех category — компромисс. Альтернатива — иметь по enum
на category, но это усложняет.

**Резолюция:** добавляем GENERIC в общий ModelSource. Документируется
как «source для transformer/load когда vendor не специфичен».

#### 🟢 Note

##### N1. CLI helper structure

```python
async def _list_models(
    library: SpiceModelLibrary,
    category: ComponentCategory,
) -> list[SpiceModel]:
    all_models = await library.list_all()
    return [m for m in all_models if m.category is category]
```

CLI subapp tube/transformer/load — каждый вызывает _list_models
с своей категорией. Минимум дублирования.

##### N2. Filename `OPT_SE_5K_8` vs `OPT_GENERIC`

BACKLOG спецификация — `OPT_GENERIC`. Но `OPT_SE_5K_8` информативнее
(5kΩ:8Ω SE topology). При расширении (`OPT_PP_6K6_8`) разница
читабельна. Решаю в пользу descriptive names.

##### N3. Adapter sub-package renaming

`tube_models/` → `spice_models/`. Update independence contract в
pyproject. Все импорты обновить.

##### N4. Tests рефакторинг

Существующие T006 тесты используют tube-specific импорты. После
рефакторинга:
- `TubeModelLibrary` → `SpiceModelLibrary`.
- Сигнатуры методов сохранены.
- Имена fixture'ов в адаптерных тестах обновить.

##### N5. README обновление

`data/models/README.md` (новый) — глобальная структура. Существующий
`data/models/tubes/README.md` остаётся для tube-specific.

##### N6. ngspice smoke — T008

Подтверждение что OPT + speaker действительно работают в SE-усилителе
— T008 (требует SPICEBridge/ngspice). T007 acceptance: только
парсинг моделей + CLI display.
