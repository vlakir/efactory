# Spec: Tube-curve-fitting — Koren/Ayumi-параметры из даташитов через Claude vision

**Статус:** Analyzed
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
  - `pentode` — Ayumi-style формула (см. Clarify C1). Покрывает и
    beam tetrode (KT88, 6L6, 6П3С); отдельного режима `tetrode` нет
    (см. Clarify C2). В `.lib` header проставляется реальный
    `tube_type` (`pentode` или `tetrode`), пользователь указывает
    через CLI флаг `--header-type {pentode,tetrode}` (default
    `pentode`).
- **ДОЛЖНА** использовать `scipy.optimize.curve_fit` или
  `least_squares` с физически осмысленными bounds (`mu>0`, `1<ex<3`,
  `kg1>0`, `kp>0`, `kvb>0`, `0<vct<5`).
- **ДОЛЖНА** запускать **multi-start** оптимизацию (см. Clarify C5):
  ≥3 initial guess'а (типовые класса + один-два randomized в пределах
  bounds + опциональный `--seed-from <existing-tube>` для экзотики),
  выбирается решение с минимальным RMS residual. Это страховка от
  локальных минимумов scipy.curve_fit на «нестандартных» лампах.
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
  [--include-vct] [--header-type {pentode,tetrode}]
  [--seed-from <existing-tube>] [--overlay <png>] [--force]`.
- **ДОЛЖНА** принимать JSON-схему (см. §5, Key Entities, `IVDataset`).
- **ДОЛЖНА** писать `.lib` файл в `<out>/<NAME>.lib`, по умолчанию
  `<out> = $XDG_DATA_HOME/efactory/models/tubes/custom/` (user
  overlay).
- **ДОЛЖНА** проставлять header `* tube_type: triode | pentode |
  tetrode` — обязательное условие для tube-type detection (см.
  `data/models/tubes/README.md`). Для `--type pentode` значение
  header выбирается флагом `--header-type` (default `pentode`).
- **ДОЛЖНА** отказываться перезаписать существующий `.lib` без
  `--force`.
- **ДОЛЖНА** быть **pure compute** — НЕ трогает KB (см. Clarify C7).
  KB-topic добавляется отдельным шагом (slash-команда или
  `efactory kb add` вручную).
- **МОЖЕТ** выдавать summary в stdout: parameter values ± errors,
  RMS residual, пути файлов.

### Slash-команда (agent-facing)

- **ДОЛЖНА** появиться `/tube-add-from-datasheet <part>` —
  agent-driven workflow по сценарию S1.
- **Входной контракт** (см. Clarify C6): slash берёт только `<part>`;
  агент инструкцией ищет последний PDF/PNG в текущем чате. Если
  изображений несколько (или ни одного) — агент **спрашивает у
  пользователя** конкретный путь, не угадывает. Опциональный
  fallback — `<part> <path-to-file>` при явном указании.
- Slash — тонкий wrapper: даёт агенту последовательность шагов
  (vision-extract → CLI → KB → smoke), список форматных правил
  (как структурировать JSON для fitter'а, какие точки минимально
  нужны), правила транслитерации (см. §5 / Clarify C4), и
  acceptance-template для финального доклада.
- **НЕ ДОЛЖНА** содержать сам fitter или vision-логику в коде slash
  (логика — у агента и CLI; slash — instructions).

### KB

- **ДОЛЖНА** после fit'а создаваться KB topic `tubes.<part>` через
  `efactory kb add --body ...`, с шаблонным телом: tube_type,
  ключевые параметры, источник datasheet, дата fit'а, RMS residual.
- **Ответственность — slash, не CLI** (Clarify C7). CLI остаётся
  pure compute; slash после успешного fit вызывает `efactory kb add`
  отдельным шагом. Это держит границу: deterministic боковой эффект
  (write `.lib`) — в CLI; KB как agent-driven artifact — снаружи.

### Smoke-симуляция (acceptance gate)

- Acceptance в Phase 4 покрывает **две лампы** (Clarify C3, вариант
  c): 6Ж38П (RF pentode) и 6П13С (audio output pentode).
- **Для 6Ж38П** — облегчённый smoke: `.op`-симуляция типичной
  bias-точки, сравнение Ia с одной-двумя datasheet-точками без
  полного RF-каскада (RF-схема для одной задачи overkill).
- **Для 6П13С** — полный SE-amp по образцу существующих T027 templates
  (например, `audio-pent-se-amp`): Vb ≈ 250 V, cathode resistor bias,
  резистивная нагрузка 5-10 kΩ. Smoke = `.op` + проверка анодного
  тока и операционной точки.
- Допуски — §4 Success Criteria.
- Механизм запуска — переиспользуем существующие `efactory bridge
  sim-run op` (T145) + `efactory sim-results` (T142), нового CLI на
  validation не вводим.

## 4. Success Criteria

1. **Round-trip (S4).** Синтетические точки из 12AX7 Koren-модели
   (Va: 0..400 V, 7-10 точек на curve; Vg: -0.5..-4 V, 5 curves) →
   fitter → параметры с относительной ошибкой по MU ≤5%,
   KG1/KP/KVB ≤5%, EX ≤2% (это абсолютный показатель).
2. **Acceptance на двух лампах (S1, Clarify C3 вариант c).**
   - **6Ж38П (RF pentode):** vision-extract → fit → `.lib` + `.op`
     smoke в типичной bias-точке → сравнение Ia с datasheet'ом на
     одной-двух control-точках. Допуск ±15% по Ia.
   - **6П13С (audio output pentode):** vision-extract → fit →
     `.lib` + SE-amp smoke (Vb ≈ 250 V, Rk bias, Rload 5-10 kΩ) →
     сравнение Ia (op-point) и Va с datasheet'ом. Допуск ±15% по Ia,
     ±10% по Va при заданном Ia.
   - Контроль на **3-5 control-точках** на лампу — равномерно
     распределённых по всему curve range (low-Vg + mid + high-Vg
     корнеры). Не на всех извлечённых точках, чтобы избежать
     overfitting-bias оценки.
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
Body — короткий summary tube_type + ключевых параметров + source +
дата fit'а. Имя `<part>` — slash-safe lowercase, после транслитерации
(см. ниже).

### Транслитерация имён (Clarify C4)

Существующая конвенция `data/models/tubes/custom/` — латиница
(`GU50`, `6N1P`, `6P14P`, `6P45S`). Прописываем её формально:

| Кириллица | Латиница | Пример |
|-----------|----------|--------|
| А | A | — |
| Г | G | GU50 |
| Е | E | — |
| Ж | Zh | 6Zh38P (но см. ниже!) |
| Л | L | — |
| М | M | — |
| Н | N | 6N1P |
| П | P | 6P14P |
| Р | R | — |
| С | S | 5S3S |
| Т | T | — |
| У | U | GU50 |
| Х | Kh | — |
| Ц | Ts | — |

**Особый случай "Ж":** существующие custom не имеют ламп с "Ж"
прецедента. Дефолт — `Zh` (например, `6Zh38P.lib`); пользователь
видит финальное имя в подтверждении slash-команды и может
override'нуть. KB topic — lowercase: `tubes.6zh38p`.

Slash в инструкции агенту: **сначала транслитерировать → показать
пользователю предлагаемое имя → подтвердить перед записью**.
Reject (без транслитерации) — нет: всегда даём предложение, чтобы
не падать на edge-case буквах.

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

## 8. Phases / Implementation plan

Закреплено в Clarify C8. Каждая Phase — одна сессия + один коммит
на ветке (squash перед PR).

- **Phase 0 — Probe (без записи кода в src/).** Открыть в чате
  datasheet известной лампы (12AX7 или EL34, чтобы было с чем
  сравнить ground truth) и проверить, что Claude vision извлекает
  IV-точки с разумной точностью. Если точки врут систематически —
  переоцениваем спеку и формат вwo CLI до начала implement. Артефакт
  фазы — короткая запись «vision feasibility check» в `specs/T031-
  tube-curve-fitting/phase-0-probe.md` (~200 строк отчёта). Без
  изменений в репозитории, кроме этого файла.
- **Phase 1 — Domain fitter (TDD).** `src/domain/tube_fitting/`
  (hexagonal layout без `efactory/` обёртки в репо): Koren triode,
  Ayumi pentode, multi-start,
  dataclasses (`IVDataset`, `KorenTriodeParams`, `AyumiPentodeParams`,
  `FitResult`). Round-trip-тесты на синтетических данных из
  существующих библиотечных моделей. Без I/O, без CLI.
  Acceptance — Success Criterion #1 (синтетика 12AX7 ≤5% error).
- **Phase 2 — CLI + JSON loader + .lib writer + overlay.** Adapter
  слой: JSON-схема (см. §5), `.lib`-renderer (с header'ом), CLI
  `efactory tube fit-from-points`, opt-in overlay PNG. Round-trip
  CLI-тест (готовый JSON → `.lib` идентичен ожидаемому). Acceptance
  — Success Criterion #3.
- **Phase 3 — Slash + KB integration + ADR-T031a.** Slash-команда
  `/tube-add-from-datasheet`, инструкции агенту (vision-pipeline,
  транслитерация, KB-template). ADR-T031a в `DECISIONS.md` («свой
  fitter, не wrap Заславский»). KB-sync per T134 — Уровень 1
  (`agent.command-routing` mapping) и Уровень 2 (parametrized case
  в `test_control_examples.py`). Acceptance — Success Criterion #4 и
  #6.
- **Phase 4 — Acceptance на 6Ж38П + 6П13С.** Vision-extract обоих
  datasheet'ов в чате, fit, smoke-сим (`.op` для 6Ж38П, SE-amp для
  6П13С), сравнение с control-точками, отчёт в `phase-4-acceptance.md`
  внутри spec-папки. Phase закрывается, когда оба варианта проходят
  допуски Success Criterion #2.

Phase 0 — выполняется до commit'ов в код (probe-only). Phase 1-4 —
последовательные сессии, в каждой делаем `git commit -m "T031 Phase
N: ..."` на этой же ветке. Перед PR — squash + перенос BOARD
Doing → Done.

---

## Clarify (заполняется Claude)

### Open questions

(Раунд 1 закрыт 2026-06-03. Дополнительные вопросы появятся на
Analyze-проходе, см. ниже.)

### Resolved (с ответами)

- **C1 (pentode формула).** Ayumi. Существующие 11 рабочих pentode
  моделей в `data/models/tubes/ayumi/` дают калибровочный baseline
  для round-trip тестов. Хspice `^` оператор остаётся в .lib
  source; T168 конвертер сделает `pwr()` на чтении.
- **C2 (beam tetrode).** Под единым режимом `pentode` в fitter'е.
  В `.lib` header реальный `tube_type` (`pentode` или `tetrode`)
  выбирается флагом `--header-type` (default `pentode`).
- **C3 (целевая лампа acceptance).** Вариант **(c) — обе:** 6Ж38П
  (RF pentode, минимальный smoke `.op`) + 6П13С (audio output pentode,
  полный SE-amp smoke). Дороже по подготовке, но maximally validate
  и реально валидирует production use case.
- **C4 (транслитерация).** Закреплена в §5 секции «Транслитерация
  имён». Slash подтверждает финальное имя у пользователя перед
  записью.
- **C5 (initial guess).** Вариант **(c) — multi-start:** ≥3 starts
  (типовой класса + 1-2 randomized в bounds + opt `--seed-from
  <existing-tube>`), выбирается решение с минимальным RMS residual.
  Не вариант (a), потому что для экзотичных ламп hard-coded typical
  значения могут увести в локальный минимум.
- **C6 (slash input contract).** Slash `<part>` + агент ищет
  последний PDF/PNG в чате; если несколько — спрашивает пользователя,
  не угадывает. Fallback `<part> <path>` явным указанием — опция.
- **C7 (KB ownership).** CLI остаётся pure compute (только `.lib`).
  KB topic создаётся slash-командой отдельным шагом через
  `efactory kb add --body`.
- **C8 (план фаз).** Phase 0 probe + Phase 1-4 implement. Закреплено
  в §8.

---

## Analyze (заполняется Claude)

Проход после Clarify 2026-06-03. Категории по нашей конвенции:
🔴 Critical (фиксим до implement), 🟡 Warning (обсуждаем), 🟢 Note
(к сведению).

### 🔴 Critical

- **A-C1. `scipy.optimize.curve_fit` + bounds требует `method='trf'`
  или `'dogbox'`.** Default Levenberg-Marquardt (`method='lm'`)
  bounds НЕ поддерживает; передача bounds с default'ом
  молча даст silent error / неверное поведение в разных версиях
  scipy. В реализации Phase 1 — **явно** `curve_fit(..., bounds=...,
  method='trf')`. Без этого fitter может молча игнорировать bounds
  и сходиться в нефизичное решение.
- **A-C2. Multi-start с randomized seeds — фиксируем `numpy.random.
  default_rng(seed)`.** Без detereminism unit-тесты будут flaky
  (round-trip-error может прыгать выше threshold). Default seed
  закладываем в код (например, `42`), tests могут override через
  fixture.

### 🟡 Warning

- **A-W1. `--include-vct` действует только для `--type triode`.**
  V_ct (cathode contact potential) — параметр Koren-triode
  formulation; для Ayumi-pentode у него нет прямого аналога. CLI
  должен отвергать `--include-vct --type pentode` с понятной
  ошибкой, не молча игнорировать.
- **A-W2. Success Criterion #2 формулировка «±10% по Va при
  заданном Ia» — inverse problem.** Чтобы дать Va по Ia, нужно
  численно инвертировать Koren / Ayumi уравнение (root find).
  Это дополнительная сложность. **Предложение упростить:**
  «±15% по Ia при заданных (Vg, Va) на control-точках» — это
  одна оценка, прямая, без inverse solver. Для пентода на одном
  screen voltage этого достаточно для acceptance. Va-проверка
  тогда уходит из формулировки. Согласовать на старте Phase 1.
- **A-W3. Smoke-сим SE-amp для 6П13С — нужен ли реальный OPT
  (выходной трансформатор)?** Если да — мы тащим T007 transformer
  модель в smoke. Если нет — резистивный nullload (R = 5-10 kΩ)
  даёт ту же op-point оценку, без OPT-сложности. **Предложение:**
  резистивная нагрузка достаточно (op-point smoke). Полный SE с
  OPT — отдельный валидационный шаг, выходит за рамки T031.
- **A-W4. PNG-overlay требует `matplotlib.use("Agg")` в headless
  контексте.** Если код подключает matplotlib без явного backend,
  на тестовом docker'е `pyplot.figure()` упадёт с
  `no display name`. Существующий T024/T142 кода это уже решают —
  переиспользуем pattern.
- **A-W5. Vision-feasibility 6Ж38П может провалить Phase 0.**
  Если Claude vision не извлекает frame-grid datasheet'ы с
  достаточной точностью — нужна стратегия: (a) переключиться на
  более простой datasheet 6П13С только; (b) добавить manual
  point-entry CLI path. Решение принимается на выходе Phase 0;
  спека может потребовать корректировки.
- **A-W6. Headless контейнер видит PDF/PNG из чата фронтенда —
  гипотеза.** Slash говорит «найди файл в чате»; technically frontend
  Claude Code должен передать image в context агента. Если нет —
  agent видит только filesystem контейнера, и slash должен явно
  требовать `<path>` (S1 input contract пересматривается). Pилотaем
  в Phase 0 probe.

### 🟢 Note

- **A-N1. Транслитерация edge-letters** (Ё/Й/Щ/Я и др.) — полная
  таблица не нужна в спеке, добавим в slash-instructions Phase 3.
- **A-N2. Multi-start vs global optimizers.** Если на Phase 1
  multi-start с N=3-5 startов не закрывает acceptance — есть
  `scipy.optimize.differential_evolution` / `basinhopping`. Не
  закладываемся сейчас; backup plan.
- **A-N3. 6П13С шаблон SE-amp.** Существующий `data/templates/
  se-amp/` использует 6П14П — для Phase 4 smoke удобно скопировать
  и подменить `.SUBCKT 6P14P` на `6P13S`, без нового template'а.
  Это inline-change, не отдельная задача.
- **A-N4. KB L3 smoke (full agent через docker run)** — для T031
  не обязателен по T134 (T031 — feature, не infrastructure). L1
  (`agent.command-routing` mapping) + L2 (parametrized regression
  test) достаточно.
- **A-N5. Round-trip генерация синтетики (S4).** В Phase 1 для
  test-фикстур можно либо (a) запускать ngspice `.op` на
  существующих .lib моделях (медленно, integration-tests style),
  либо (b) вычислить Ia напрямую из Koren/Ayumi-formulas
  питон-кодом, в тех же модулях, что fitter (быстро, unit-style).
  Вариант (b) предпочтителен — никаких подпроцессов, тесты
  миллисекундные.

### Phase 1 entry gate (после Analyze)

Перед началом implement-ов фиксируем эти решения:

- A-C1, A-C2 — обязательны в коде.
- A-W1 — CLI argparse валидирует.
- A-W2 — переформулировать §4 Success Criterion #2 (только Ia при
  заданных Vg, Va). Согласовать с Vladimir.
- A-W3 — резистивная нагрузка, без OPT.
- A-W5, A-W6 — экспериментально валидируются в Phase 0; результат
  определяет, нужны ли поправки спеки.
