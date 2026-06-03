# Spec: Tube-curve-fitting — Koren/Ayumi-параметры из даташитов через Claude vision

**Статус:** Draft
**Дата создания:** 2026-06-03
**Связанные документы:**
- `data/models/tubes/README.md` — формат built-in моделей (T006).
- ADR T134 — KB-namespace `tubes.<part>` для агент-стороны.
- ADR T156 — `efactory kb add --body` для записи KB topic.
- ADR T027 — расширение библиотеки до ~50 моделей через templates +
  patches к Ayumi-моделям (T167).
- ADR 2026-05-19 «Claude Code as multimodal frontend» — снимает
  необходимость в собственном vision-pipeline в коде.
- Reference: `github.com/Gleb-Zaslavsky/Tube-curve-fitting-by-Koren-
  triode-model` (MIT, 2023, single-commit, PyQt5 GUI, только триод,
  не headless). Используется как формульный референс (каноническая
  6-параметрическая Koren-формула с V_ct), не как dependency. ADR-T031a
  «почему не wrap'аем» будет в `DECISIONS.md` при merge.

---

## 1. Overview

Добавить путь «datasheet редкой / советской / экзотической лампы
(PDF или PNG в чате) → SPICE-модель в библиотеке efactory». Claude
как multimodal frontend визуально извлекает точки анодных
характеристик `(Vg, Va, Ia)`; собственный scipy-fitter (без
зависимости от Заславский) возвращает Koren-параметры для триода
или Ayumi-параметры для пентода / beam tetrode; результат пишется
`.lib`-файлом в user overlay (`~/.local/share/efactory/models/tubes/`),
заводится KB topic `tubes.<part>`, и опционально запускается
smoke-симуляция типового включения для acceptance-проверки.

Цель — расширить библиотеку моделей за пределы ~50 ламп после
T027/T167 (built-in коллекции Koren/Ayumi/Duncan + советские
custom), приоритетно для production-grade case-ов, где пользователю
важна сходимость с datasheet, а не "усреднённая Koren-модель".

## 2. Сценарии использования

> Frontend — Claude Code как multimodal интерфейс (ADR 2026-05-19);
> backend — CLI efactory + KB. Сценарии описывают связку.

**S1. Datasheet → модель (vision-driven, primary path).**
Инженер в чате efactory-агента: «вот datasheet 6Ж38П.pdf
[прикладывает], добавь модель в библиотеку». Агент: (a) видит PDF
multimodal, идентифицирует анодные характеристики (output curves
Ia vs Va для разных Vg), (b) извлекает точки в JSON-формате
fitter'а, (c) вызывает `efactory tube fit-from-points 6P38P
--type pentode --points /tmp/6p38p.json`, (d) fitter возвращает
параметры, CLI пишет `.lib` в user overlay, (e) агент создаёт KB
topic `tubes.6p38p` через `efactory kb add --body`, (f) запускает
smoke-сим типового включения, (g) докладывает результат с
сравнением модель↔datasheet.

**S2. Точки готовы заранее (deterministic path).**
Инженер померил образец на стенде, есть JSON с точками `(Vg, Va, Ia)`.
Вызывает `efactory tube fit-from-points 6P14P_MY --type pentode
--points my_measurements.json --out /tmp/`. Получает `.lib` для
дальнейшего использования. KB topic, smoke-сим — отдельным шагом
вручную или не нужны.

**S3. Уточнение существующей модели под конкретные образцы.**
Built-in 12AX7 — усреднённая Koren-модель; для аудиофильского
проекта инженер хочет fit под свою партию ECC83 Sovtek. Workflow
тот же что S2, но результат пишется как `12AX7_SOVTEK.lib` в user
overlay — built-in остаётся нетронутым.

**S4. Round-trip регрессия (наш test-case).**
Берём существующую built-in модель (например, 12AX7), генерируем
синтетические IV-точки прогоном через её Koren-equation в ngspice
.op-sim, скармливаем fitter'у, проверяем, что вернулись те же
параметры с относительной ошибкой ≤5%. Это unit-уровень
гарантии корректности fitter'а — без datasheets и vision.

## 3. Functional Requirements

### Fitter (domain слой)

- **ДОЛЖНА** принимать IV-датасет в виде `(Vg array, Va array,
  Ia array)` равной длины (один датасет = много (Vg, Va, Ia)
  точек, измеренных на разных curves Vg).
- **ДОЛЖНА** поддерживать два режима:
  - `triode` — Koren 5-параметрическая формула (MU, EX, KG1, KP,
    KVB), опционально 6-я V_ct (cathode contact potential) при
    `--include-vct`.
  - `pentode` — Ayumi-style формула (точная форма — в Phase 1,
    калибруется на существующих Ayumi-моделях типа 6V6/EL34).
- **ДОЛЖНА** использовать `scipy.optimize.curve_fit` или
  `least_squares` с физически осмысленными bounds (`mu>0`, `1<ex<3`,
  `kg1>0`, `kp>0`, `kvb>0`, `0<vct<5`) и initial guess (для известных
  типовых ламп — derived из «типичного триода / пентода»).
- **ДОЛЖНА** возвращать pure-Python dataclass `FitResult` с
  параметрами, residuals (RMS Ia error по всему датасету),
  per-parameter standard errors (из covariance).
- **НЕ ДОЛЖНА** depend on `Qt`, `matplotlib.show()`, или любого GUI —
  работает в headless контейнере без X.
- **МОЖЕТ** генерировать PNG-overlay фита поверх IV-точек через
  `matplotlib.savefig` (без `show()`) — opt-in флагом
  `--overlay <path>`, по аналогии с `efactory plot` (T024).

### CLI (адаптер слой)

- **ДОЛЖНА** появиться команда `efactory tube fit-from-points <name>
  --type {triode,pentode} --points <file.json> [--out <dir>]
  [--include-vct] [--overlay <png>]`.
- **ДОЛЖНА** принимать JSON-схему (см. §5, Key Entities, `IVDataset`).
- **ДОЛЖНА** писать `.lib` файл в `<out>/<NAME>.lib`, по умолчанию
  `<out> = $XDG_DATA_HOME/efactory/models/tubes/custom/` (user
  overlay).
- **ДОЛЖНА** проставлять header `* tube_type: triode | pentode` —
  обязательное условие для tube-type detection (см.
  `data/models/tubes/README.md`).
- **ДОЛЖНА** отказываться перезаписать существующий `.lib` без
  `--force`.
- **МОЖЕТ** выдавать summary в stdout: parameter values ± errors,
  RMS residual, пути файлов.

### Slash-команда (agent-facing)

- **ДОЛЖНА** появиться `/tube-add-from-datasheet <part>` —
  agent-driven workflow по сценарию S1.
- Slash — тонкий wrapper: даёт агенту последовательность шагов
  (vision-extract → CLI → KB → smoke), список форматных правил
  (как структурировать JSON для fitter'а, какие точки минимально
  нужны), и acceptance-template для финального доклада.
- **НЕ ДОЛЖНА** содержать сам fitter или vision-логику в коде slash
  (логика — у агента и CLI; slash — instructions).

### KB

- **ДОЛЖНА** после fit'а доступна команда (или подпункт CLI)
  создания KB topic `tubes.<part>` через `efactory kb add --body`,
  с шаблонным телом: tube_type, ключевые параметры, источник
  datasheet, дата fit'а, RMS residual.
- Точная форма (создаёт ли это `tube fit-from-points` автоматически,
  или slash-команда — отдельным шагом) — пункт Clarify.

### Smoke-симуляция (acceptance gate)

- **ДОЛЖНА** для acceptance проверяться сходимость модели с
  datasheet-точками. Конкретный механизм — пункт Clarify (variant A:
  отдельный `efactory tube validate <name> --against-points <json>`;
  variant B: интегрировано в `fit-from-points` как post-fit step).

## 4. Success Criteria

1. **Round-trip (S4).** Синтетические точки из 12AX7 Koren-модели
   (Va: 0..400 V, 7-10 точек на curve; Vg: -0.5..-4 V, 5 curves) →
   fitter → параметры с относительной ошибкой по MU ≤5%,
   KG1/KP/KVB ≤5%, EX ≤2% (это абсолютный показатель).
2. **Acceptance на 6Ж38П (S1).** Реальный datasheet → vision-extract
   → fit → `.lib` + smoke-сим → сравнение Ia(Va, Vg) с datasheet
   точками. Допуск: ±15% по Ia (typical for tube fits), ±10% по Va
   при заданном Ia. Smoke-сим — типовое включение (для пентода —
   SE-усилитель с резистивной нагрузкой 5-10 kΩ, Vb ≈ 250 V,
   bias через cathode resistor).
3. **CLI deterministic test.** Готовый JSON c точками → команда
   возвращает exit 0, `.lib` в указанном пути, stdout содержит
   summary параметров и RMS residual.
4. **KB integration.** После выполнения slash-команды S1 запрос
   `/kb-search 6Ж38П` находит topic `tubes.6p38p` (имя
   транслитерируется в slash-safe form — пункт Clarify).
5. **Pre-push gates.** ruff / ruff format / mypy / lint-imports /
   pytest с coverage ≥80% — все зелёные.
6. **L2 KB regression** (per наш T134 sync discipline): новые KB
   topics покрыты parametrized case в
   `tests/integration/agent_kb/test_control_examples.py`.

## 5. Key Entities

### `IVPoint`
```
vg: float  # grid-cathode voltage, V (negative for typical bias)
va: float  # anode-cathode voltage, V (positive)
ia: float  # anode current, mA (positive)
```

### `IVDataset` (JSON-схема)
Один датасет = много точек на нескольких curves (по Vg).
```json
{
  "tube_name": "6Ж38П",
  "tube_type": "pentode",
  "source": "datasheet: <ref>",
  "date_extracted": "2026-06-03",
  "screen_voltage_v": 150,   // pentode only
  "curves": [
    {"vg": -1.0, "points": [[50, 5.2], [100, 7.1], ...]},  // [(Va, Ia)]
    {"vg": -2.0, "points": [[50, 2.4], [100, 4.3], ...]},
    ...
  ]
}
```
Внутри fitter'а разворачивается в плоские массивы `(Vg, Va, Ia)`.

### `KorenTriodeParams` (dataclass)
```
mu: float       # amplification factor
ex: float       # exponent (~1.4 typical small-signal, ~2 power)
kg1: float      # plate current scaling
kp: float       # plate-to-grid coupling
kvb: float      # plate-to-bias coupling
vct: float | None  # cathode contact potential (optional)
```

### `AyumiPentodeParams` (dataclass)
Точная форма Phase 1 (калибруется на 6V6/EL34/EF86 Ayumi).
Минимально: `mu`, `ex`, `kg1`, `kg2` (screen), `kp`, `kvb`,
`screen_v` (нормировочный — берётся из datasheet).

### `FitResult` (dataclass)
```
params: KorenTriodeParams | AyumiPentodeParams
rms_residual_ma: float
per_param_stderr: dict[str, float]  # из covariance diag
n_points: int
converged: bool
```

### KB topic `tubes.<part>`
Slash-safe `<part>` — транслитерация кириллицы (точные правила —
Clarify). Body — короткий summary tube_type + ключевых параметров
+ source + дата fit'а.

## 6. Assumptions & Constraints

- **Claude vision действительно справляется** с прямым чтением анодных
  характеристик на datasheet — гипотеза, валидируемая acceptance на
  6Ж38П. Если нет — fallback не «GUI picker», а «попроси пользователя
  отдать JSON, vision не сработал». Manual GUI picker — out of scope
  этого спринта (см. §7).
- Целевой формат датасета — 5 curves по Vg, 7-10 точек на curve.
  Меньше — fit может не сойтись для пентода (6 параметров).
- Headless контейнер `efactory:linux` — никаких Qt/X11.
- Стандартный стек: `uv` + `scipy >=1.12` (уже в `pyproject.toml`
  через T113/T129) + `matplotlib` (есть, T024/T142).
- Fitter — pure deterministic; vision-extract — non-deterministic
  (LLM), но это часть **agent workflow**, не CLI. CLI всегда работает
  с готовым JSON.

## 7. Out of Scope

- **Manual point-picker GUI** (Zaslavsky-style PyQt5). Если vision
  не справится — заводим отдельной задачей, возможно desktop tool
  вне efactory:linux. Не блокер.
- **Rectifier curve-fitting.** Rectifier модели — diode-based
  (`IS`, `RS`, `N`, `BV`), fitting проще, отдельная мини-задача.
- **AC small-signal validation** (gm, rp, динамический mu через
  `.ac`-sweep на bias-точке). Только DC IV в этой фиче. Add-on —
  отдельная задача.
- **Auto-download datasheets** из интернета. Пользователь приносит
  файл сам.
- **Auto-generation KiCad symbol** для новой лампы. Symbol = copy
  base shape (как T107 Phase 0) — отдельная фича. T031 даёт только
  `.lib`.
- **Wrap of Zaslavsky's repo as dependency.** Решение «свой fitter»
  закреплено до начала спеки (см. ADR-T031a).
- **Symbolic auto-rename рукописных** буквенных имён (например, "6Ж38П"
  vs "6P38P"). Точные правила транслитерации — внутри Clarify;
  user-facing transliteration UI — out of scope.
- **Beam tetrode с complex screen modeling** свыше Ayumi-формы
  (например, KT88 multi-section saturation). Калибруем на типовых
  Ayumi-моделях и не лезем глубже.

---

## Clarify (заполняется Claude)

### Open questions

(Раунд 1 — Claude задаст, Vladimir ответит, ответы вшиваются обратно.)

### Resolved (с ответами)

---

## Analyze (заполняется Claude)

(Заполняется после Clarify.)
