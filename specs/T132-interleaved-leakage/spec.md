# Spec: Interleaved OPT leakage inductance — PyOM analytical path

**Статус:** Analyzed
**Дата создания:** 2026-05-21
**Связанные документы:**
- `specs/T131-saturable-thd/spec.md` — saturation distortion (другой
  главный нелинейный механизм OPT; T132 покрывает HF-rolloff
  через leakage Lσ).
- BACKLOG `T132` — оригинальная постановка.

---

## 1. Overview

Top-tier audio OPT'ы (Plitron, Sowter, Hashimoto, Tango, Lundahl)
используют **sandwich-секционную намотку обмоток** (P-S-P, S-P-S-P-S,
5-section, и т.д.) для минимизации leakage inductance Lσ — главного
источника HF-rolloff в усилителе. Чем меньше Lσ, тем выше bandwidth
(типичный low-end OPT: HF-3dB ≈ 20-30 kHz; интерливный hi-end: 50-100
kHz и выше).

efactory сейчас не enrich'ает `MagneticComponent` информацией о порядке
секций обмоток на bobbin'е (`Bobbin` VO содержит только имя bobbin'а
из PyOM каталога без layer order). T132 добавляет domain-уровневое
representation секционности + use case `analyze_interleaved_leakage`,
который через PyOM `calculate_leakage_inductance` возвращает Lσ для
произвольного `MagneticComponent`. Pilot — sandwich-OPT с известным
datasheet reference (например, Plitron classical 5-section, Sowter
3-section, или published DIY-измерение).

## 2. Сценарии использования

- **Designer choosing OPT topology.** Сравнивает interleaved vs
  non-interleaved Lσ для одного и того же core+turns ratio:
  P-S vs P-S-P vs P-S-P-S-P. Видит, как Lσ падает с увеличением
  секций; принимает решение о complexity vs HF-bandwidth tradeoff.
- **Specifying audiophile-grade OPT.** Запускает `analyze_
  interleaved_leakage` на дизайне с явной sandwich-структурой;
  получает Lσ_primary; рассчитывает HF-3dB = R_load_reflected /
  (2π·Lσ_primary). Если HF-3dB < target (например, 60 kHz) —
  итерирует layer count.
- **Cross-validation с datasheet'ом.** Pilot test для acceptance:
  PyOM-derived Lσ для известного OPT (Hammond / Plitron / Sowter с
  опубликованными измерениями) сходится в пределах ±25% к datasheet
  value.

## 3. Functional Requirements

- **ДОЛЖНА:** расширить domain `Bobbin` (или `MagneticComponent`)
  на представление **section layout** обмоток — sandwich порядок,
  parameters per section (layer count, insulation thickness).
- **ДОЛЖНА:** предоставить use case `analyze_interleaved_leakage(
  component: MagneticComponent) -> LeakageInductanceResult` —
  возвращает Lσ_primary [H], Lσ_secondary [H], coupling factor k.
- **ДОЛЖНА:** mapping domain section layout → PyOM MAS schema
  `windingWindow.sections` correctly: order = physical sandwich
  order; section type = primary/secondary; layer count = PyOM
  `layers` поле.
- **ДОЛЖНА:** Pilot acceptance test на известном reference OPT с
  documented Lσ — measured Lσ_primary в пределах ±25% от reference.
- **МОЖЕТ:** возвращать дополнительные diagnostics — например,
  per-section flux distribution или per-section copper-loss
  estimate (PyOM поддерживает).
- **НЕ ДОЛЖНА:** требовать FEM-solver или GUI — pure PyOM analytical
  path (T133 Elmer FEM cross-validation — отдельный follow-up).
- **НЕ ДОЛЖНА:** менять существующее представление `Bobbin.bobbin_name`
  — sandwich layout это новое опциональное поле (default None →
  PyOM использует автоматическую секционность через `interleaving_
  level` или равномерное распределение).

## 4. Success Criteria

- **Domain VO расширен**: `Bobbin.section_layout` (или sibling field)
  представляет sandwich-структуру с минимум 2 PyOM-compatible
  параметрами per section (winding_name + layer_count).
- **PyOM payload correct**: integration test проверяет, что
  `_build_winding_dict` / coil construction в PyOpenMagneticsAnalytics
  emit'ит правильный `windingWindow.sections` JSON.
- **Pilot acceptance**: Lσ_primary на reference OPT ∈ [reference ·
  0.75, reference · 1.25] (±25%).
- **Regression-safe**: existing `mag_verify_field` use case с
  `Bobbin.section_layout=None` работает unchanged (default PyOM
  behavior сохраняется).
- **Pre-push gate**: ruff / format / mypy / lint-imports / pytest
  все зелёные.

## 5. Key Entities

- **`MagneticComponent`** (existing, T113 Phase 2) — input
  компонент. Может быть расширен через `Core` или `Bobbin` extension,
  либо новым sibling-полем.
- **`Bobbin`** или новая VO для bobbin description с section layout.
- **`WindingSection`** (new) — параметры одной секции в sandwich'е:
  winding name (matches `Winding.name`), section index, layer count,
  опционально insulation thickness.
- **`LeakageInductanceResult`** (new) — output use case'а:
  Lσ_primary [H], Lσ_secondary [H], coupling factor k, опционально
  diagnostics.
- **`PyOpenMagneticsAnalytics`** (existing adapter) — расширяется
  методом `calculate_leakage_inductance(component) -> ...` через
  PyOM C++ binding.

## 6. Assumptions & Constraints

- **Hard reuse** T113 Phase 2 `MagneticComponent` / `Winding` /
  `Core` VOs — никаких новых core entities.
- **Hard reuse** существующий `PyOpenMagneticsAnalytics` adapter +
  `MagneticAnalytics` outbound port; добавление метода (вторая
  responsibility на этом adapter'е — обсуждается в Clarify).
- **PyOM 1.3.10** — `calculate_leakage_inductance` доступен (probed);
  поддерживает multi-section через `windingWindow.sections` JSON
  field (нужно verify в clarify).
- **Pilot reference data** — outside of paywalls (Stereophile,
  Audio Note Kondo skipped); preferable open sources: Patrick Turner,
  Hammond datasheet for 1627A-class, Sowter open spec sheets.
- **Acceptance band ±25%** — PyOM analytical использует упрощённые
  layer-geometric formulae; published datasheet измерения с
  precision ±10-15%; их сумма ≈ ±25% comfortable bound. Hi-precision
  до ±10% — отдельная задача FEM cross-validation (T133 +
  cross-validation T127).

## 7. Out of Scope

- **FEM cross-validation** для interleaved Lσ — T127 follow-up
  (зависит от T133 Elmer pivot готовности).
- **3D-FEM моделирование** для exotic layouts (toroidal, twisted-
  pair, и т.п.) — T13X / Phase 5 follow-up.
- **Wire-level resistance / parasitic capacitance** в interleaved —
  T132 покрывает только Lσ (главный HF-rolloff driver); copper
  resistance / inter-winding cap — отдельные задачи.
- **Saturation в interleaved** — T131 уже покрывает saturation
  через `FrohlichBHCurve`; saturation поведение от layout не
  зависит first-order (зависит только от total flux excursion и
  core area).
- **Push-pull OPT** (PP topology, primary с center-tap, чаще
  всего interleaved 5-section в hi-end) — generator должен принять,
  но pilot validation на SE-OPT (одиночная primary, без center-tap)
  для уменьшения уровня complexity. PP pilot — follow-up.
- **Optimization** (auto-select interleaving level для minimum Lσ
  given core constraints) — отдельная задача / Phase 5.

---

## Clarify (заполняется Гвидо)

### Open questions

**Domain representation:**

- **Q1.** `section_layout` лежит в `Bobbin` (вместе с `bobbin_name`)
  или в `MagneticComponent` как отдельное top-level поле? Bobbin
  семантически representation физического каркаса (включая winding
  windows и section dividers); layout того, **какая обмотка в какой
  секции**, естественно туда. Но это меняет `Bobbin.bobbin_name`-only
  pattern. Альтернатива — новая `Coil` VO между `Bobbin` и
  `Winding`-tuple. Какой путь?

- **Q2.** PyOM `windingWindow.sections` имеет fields: `name`,
  `layers`, `type` (primary/secondary), `insulation_after` (мм
  до следующей секции). Должны ли все эти поля присутствовать в
  domain `WindingSection`, или часть (insulation) идёт с default'ом?
  Insulation thickness может быть важен для leakage расчёта (больше
  insulation = больше Lσ); если у DIY-конструктора нет точных
  данных, какой sensible default? PyOM имеет default?

**PyOM API:**

- **Q3.** `calculate_leakage_inductance` в PyOM 1.3.10 — exact
  signature и payload requirements? Те же что `calculate_inductance_
  from_number_turns_and_gapping` (core_full + coil + operating_point
  + advisors)? Или другой API? Нужно verify probe.

- **Q4.** PyOM reluctance models (ZHANG/MUEHLETHALER/BALAKRISHNAN/
  STENGLEIN/EFFECTIVE_AREA) — применимы ли они к leakage расчёту,
  или leakage использует отдельный leakage model (e.g., Petros /
  Margueron)? Если несколько моделей — какую default'ом и почему?

**Adapter extension:**

- **Q5.** Добавить `calculate_leakage_inductance` метод в
  существующий `PyOpenMagneticsAnalytics` adapter (вторая
  responsibility), или создать отдельный adapter (например,
  `PyOpenMagneticsLeakage`)? Существующий аналог: `mag_verify_field`
  use case использует **два** port'а (`MagneticAnalytics` для
  inductance, `MagneticFieldSolver` для FEM). T132 Lσ — third
  responsibility analytics-стороны; добавлять как метод на тот же
  adapter / port, либо new port?

- **Q6.** Новый port `LeakageInductanceAnalyzer` (отдельный
  Protocol), или расширить `MagneticAnalytics` Protocol новым
  методом `calculate_leakage_inductance`? Расширение второго —
  breaking change для всех implementations (currently только PyOM);
  новый port — Single Responsibility сохраняется.

**Reference data:**

- **Q7.** Какой именно reference OPT для pilot acceptance? Опции:
  - **Hammond 1627A** — published Lσ_primary около 5 mH (5kΩ:8Ω
    SE, 5-section sandwich, общедоступная datasheet).
  - **Plitron PAT-XXXX** — open spec sheets, toroidal (но
    out of scope for now).
  - **Sowter 9525** — open spec, sandwich 3-section.
  - **Patrick Turner DIY measurement** — own measurements,
    detailed write-up, free access.
  Какой fixture builder делать как primary? Я склоняюсь к Hammond
  1627A class (5-section sandwich, OPT_SE_5K_8 уже есть в репо,
  можно reuse).

- **Q8.** Acceptance band ±25% — comfortable, но если pilot выйдет
  на ±5-10%, можем ли увеличить strict требования в follow-up?
  Это **range** при первом запуске, не upper bound на always.

**Backward compat:**

- **Q9.** Existing `Bobbin(bobbin_name='Bobbin E42/15')` без layout
  должно остаться valid. Когда `section_layout=None`, PyOM
  выполняет **какое default-поведение**: равномерное распределение,
  single-section P-then-S, или error? Если error — нужно явно
  пропускать leakage расчёт для default'ных bobbin'ов. Какое
  поведение мы хотим документировать?

### Proposed defaults (Гвидо, ожидают подтверждения Vladimir)

**Q1 → `MagneticComponent.section_layout: tuple[WindingSection, ...] | None`
(top-level optional field, не в Bobbin).**

Обоснование: layout — это property пары (bobbin × windings), не bobbin'а
самого по себе (тот же bobbin может содержать разные layout'ы для разных
трансформаторов). PyOM семантически тоже так: layout живёт в
`coil.functionalDescription.sections`, не в `bobbin.sections`. Альтернатива
(новая Coil VO между Bobbin и Winding[]) — корректнее DDD, но breaking
refactor для existing `MagneticComponent.windings` API; не оправдано в
T132 scope. Compromise: minimal additive — добавляем optional поле на
top-level VO. Если в будущем понадобится reorganize → Coil refactor в
отдельной задаче.

**Q2 → `WindingSection` поля:**
- `winding_name: str` — match `Winding.name`, required, min_length=1.
- `layer_count: int` — required, ≥1.
- `insulation_after_m: float | None = None` — None означает PyOM
  default (probe в Phase 0; typical kapton 25 µm).

Обоснование: minimal required для Lσ расчёта. Insulation thickness
materially влияет на Lσ (больший gap между секциями = больше Lσ), но в
DIY context конкретные measurements часто недоступны → None default к
PyOM-провайдеру. Caller с datasheet'ом задаёт явно.

**Q3 → Probe PyOM `calculate_leakage_inductance` в Phase 0 implementation
step.**

Обоснование: точная signature и payload schema не зафиксированы в open
PyOM docs (1.3.10 wheel — C++ binding без Python sources). Probe-script
(~30 LOC) на старте Phase 0 определит: argument list, return type,
required JSON fields. Аналогично pattern T113 / T131 (probe → adapter
design).

**Q4 → PyOM default leakage model, не задаём explicitly.**

Обоснование: reluctance models (ZHANG / MUEHLETHALER / ...) применяются
к **magnetizing inductance** через `calculate_inductance_from_number_
turns_and_gapping`, не к leakage. Leakage в PyOM — отдельный algorithm
(вероятно Petros/Margueron). Probe verify; если PyOM API требует
explicit model — берём default (skip parameter), при необходимости
делаем sweep в follow-up.

**Q5 → Extend existing `PyOpenMagneticsAnalytics` adapter новым методом
`calculate_leakage_inductance`.**

Обоснование: один adapter может implement'ить несколько ports.
Дублирование PyOM-module reference в отдельном adapter'е (`PyOpen
MagneticsLeakage`) — anti-pattern (один и тот же loaded `.so` хранится
twice). Existing adapter естественное место — оба метода манипулируют
тем же PyOM-binding. Single Responsibility выполняется на уровне port'а
(см. Q6), не adapter'а.

**Q6 → Новый port `LeakageInductanceAnalyzer` (Protocol), не extend
`MagneticAnalytics`.**

Обоснование: SRP per Protocol. `MagneticAnalytics` остаётся с одним
методом `calculate_inductance` (используется `mag_verify_field` use
case'ом). `LeakageInductanceAnalyzer` — новый Protocol с одним методом
`calculate_leakage_inductance` (используется новым `analyze_interleaved_
leakage` use case'ом). Existing `PyOpenMagneticsAnalytics` adapter
implement'ит оба. Composition root инжектит тот же instance в оба port'а.
No breaking change для existing `MagneticAnalytics` consumer'ов.

**Q7 → Physics-based acceptance + soft absolute bound, не точечное
matching к single reference.**

Обоснование: published Lσ для OPT часто approximate (datasheet специ-
фицирует HF-3dB, не Lσ напрямую; reverse-engineer через `Lσ = Z_load /
(2π · HF_3dB)` даёт ±20% uncertainty). Точечная привязка к single
source хрупка (Hammond 1627A не имеет authoritative published Lσ;
Patrick Turner использует M6 — material gap к нашему Nanoperm proxy
сделает direct comparison meaningless).

Robust acceptance:
- **(a) Physics-based monotonicity:** строим 3 варианта одного
  компонента — `P-S` (2 sections), `P-S-P` (3), `P-S-P-S-P` (5). Assert
  `Lσ(2) > Lσ(3) > Lσ(5)` — fundamental physics interleaving theorem.
  Если order incorrect → modeling bug.
- **(b) Absolute bound:** `Lσ(5-section) ∈ [0.1 mH, 10 mH]` для нашего
  OPT_SE_5K_8 параметров (Patrick Turner empirical range для 5kΩ:8Ω
  audio OPT, 3500 turns, E 42/15 cores: typically 0.5-5 mH; bound в
  10× wider для conservative gate).

Это лучше single-point match: проверяет **физику** + **plausibility
range** без подгонки к конкретному (потенциально неточному) datasheet.

**Q8 → Acceptance band — physics gate всегда binding, absolute range
[0.1 mH, 10 mH] на pilot.** Не ужесточаем ahead-of-time. Если в
practice окажется Lσ всегда в narrower band — corresponding tighten
в follow-up задаче.

**Q9 → `section_layout=None` → PyOM default behavior сохраняется для
`mag_verify_field` (inductance);
`analyze_interleaved_leakage(component)` где `component.section_
layout is None` → raises `ValueError("no section_layout — interleaved
analysis requires explicit layout")`.**

Обоснование: backward compat для existing inductance use case (T113 /
T129 не использует layout). Для leakage use case — explicit fail-loud
лучше silent default (DIY designer не должен случайно получить
single-section Lσ для конструктива, который реально interleaved).
PyOM behavior при отсутствии sections — probe в Phase 0.

### Resolved (Vladimir 2026-05-21: «подтверждаю»)

Все 9 предложенных defaults приняты без изменений. Кратко:

- **Q1.** `MagneticComponent.section_layout: tuple[WindingSection, ...] |
  None` — top-level optional поле (minimal additive, не Coil refactor).
- **Q2.** `WindingSection`: `winding_name: str` + `layer_count: int` +
  `insulation_after_m: float | None = None` (PyOM default).
- **Q3.** Probe PyOM `calculate_leakage_inductance` в Phase 0
  implementation step (signature factual unknown).
- **Q4.** PyOM default leakage model (no explicit choice).
- **Q5.** Extend existing `PyOpenMagneticsAnalytics` adapter методом
  `calculate_leakage_inductance` (один PyOM module → один adapter).
- **Q6.** Новый port `LeakageInductanceAnalyzer` (Protocol), не extend
  `MagneticAnalytics` (SRP per Protocol).
- **Q7.** **Physics-based monotonicity** test (P-S → P-S-P → P-S-P-S-P,
  Lσ monotonically decreases) + absolute bound [0.1 mH, 10 mH] для
  5-section pilot. Не точечная привязка к single datasheet (Hammond
  Lσ не authoritative published; Patrick Turner на M6 — material gap).
- **Q8.** Не ужесточаем ahead-of-time. Physics gate всегда binding,
  absolute range [0.1, 10] mH.
- **Q9.** `section_layout=None` → PyOM default для inductance
  (backward compat `mag_verify_field`); `analyze_interleaved_leakage`
  на None layout → `ValueError` (fail-loud).

**Spec status:** Draft → **Clarified** (готов к Analyze).

---

## Analyze (Гвидо, 2026-05-21)

После перечитки spec + grounding в codebase (`domain/magnetic.py`,
`adapters/outbound/magnetic_analytics_pyopenmagnetics/adapter.py`,
`ports/outbound/magnetic_analytics.py`, `composition/main.py`) + PyOM
1.3.10 API probe (`calculate_leakage_inductance`, `wind`,
`wind_by_sections`, `Bobbin E42/15` schema).

### 🔴 Critical (фиксим до начала реализации)

**A1. PyOM `wind`/`wind_by_sections` pattern — integer indices, не
имена обмоток.**

Probe показал: `pyom.wind(coil, reps, proportion, pattern, margins)`
ожидает `pattern` как `list[int]` где элементы — индексы winding'ов в
`coil.functionalDescription` (0-based). Не `list[str]` имён.
Spec Q1/Q2 предполагал domain-уровень с именами; нужен translation
layer.

**Решение для plan:** domain VO `InterleavingPattern.pattern: tuple[str,
...]` хранит имена обмоток (читабельно, domain-friendly); adapter
mapping переводит каждый name → index через `component.windings`
position lookup. Validation: каждое имя в pattern должно совпадать с
именем одной из обмоток компонента (model_validator на
`MagneticComponent`).

**A2. Каталожный `Bobbin E42/15` имеет `columnWidth=null` —
`calculate_leakage_inductance` падает на `[INVALID_BOBBIN_DATA]`.**

Probe показал: PyOM bobbin из `get_bobbins()` имеет
`processedDescription.columnWidth = null` и `columnDepth ≈ 2.43e-315`
(uninitialized memory garbage). Без явного fill leakage расчёт fails.

**Решение для plan:** в adapter (метод `_build_bobbin_for_leakage`)
заполняем bobbin dims вручную перед передачей в PyOM:
- `columnWidth = bobbin['windingWindows'][0]['width']` (proven
  working: 0.0074 m для E 42/15).
- `columnDepth ≈ stack_length` (для E 42/15 = 0.015 m; pull из
  core.processedDescription или hardcoded constant per shape;
  follow-up — extract via PyOM API).

Сделать helper `_normalize_bobbin_columns(bobbin, core_full)` который
fills null'ы из core data. Unit-test этот helper отдельно.

**A3. `pyom.wind` требует физическую fitment'ность turns в window —
3500 turns 0.5 mm wire в E 42/15 не помещается.**

Probe: `pyom.wind(..., pattern=[0,1], ...)` для 3500 primary + 140
secondary turns с `Round 0.5 - Grade 1` wire вернул `Exception:
Turns not created` (window 7.4 × 27.3 mm = 202 mm², required
~1750 mm linear для primary).

**Реальность:** real-world Hammond 1627A-class OPT использует тонкий
эмалированный provод (~AWG 30, ≈ 0.25 mm). С `Round 0.224 - Grade 1`
(или тоньше) turns должны помещаться.

**Решение для plan:** test fixture использует physical-realistic wire
diameter, не наш T131-default `Round 0.5`. Pilot acceptance — verify
PyOM wind succeed'ит до leakage call'а; если fail — error message
помогает выбрать правильную проволоку.

### 🟡 Warning (обсудим, возможно фиксим)

**W1. Return shape `calculate_leakage_inductance` — exception-as-data.**

Probe показал: PyOM C++ binding эмитит ошибки **в виде dict с key
`data` content'ом `"Exception: [TYPE] message"`**, не через Python
exception. То же поведение что в T113 — нужна detection в adapter.

**Решение для plan:** adapter после call'а проверяет:
```python
if isinstance(result, dict) and isinstance(result.get('data'), str) \
        and result['data'].startswith('Exception:'):
    raise LeakageInductanceAnalyticsFailedError(result['data'])
```

Same pattern уже applied в existing `MagneticAnalyticsFailedError`
catch.

**W2. PyOM `wind` excludes operating point / excitation —
leakage requires it separately.**

Probe showed: `wind(coil, ...)` принимает только coil + pattern;
`calculate_leakage_inductance(magnetic, freq, source_idx)` требует
ПОЛНЫЙ `magnetic = {core, coil, operatingPoint}` JSON. То есть
excitations нужны для leakage расчёта (frequency-dependent skin/
proximity effects?).

**Решение для plan:** adapter переиспользует existing
`_sine_waveform` helper + `excitationsPerWinding` builder из
`PyOpenMagneticsAnalytics._calculate_blocking`. Refactor: extract
shared `_build_operating_point` метод; вызывать из обоих
inductance/leakage paths.

**W3. Spec §5 Q2 default `insulation_after_m=25e-6` — не достаточно
для PyOM `wind` (требует positive margin_pairs).**

Probe: `pyom.wind(..., margin_pairs=[[0.001, 0.001]])` requires
**non-zero left+right margin** (1 mm typical kapton tape для bobbin
edges). Это **separate** от inter-section insulation.

**Решение для plan:** domain VO `InterleavingPattern` имеет ДВА
insulation поля:
- `inter_section_thickness_m: float = 25e-6` (между секциями, входит
  в `pyom.wind`'s 5-й arg).
- `bobbin_margin_m: float = 0.001` (left/right margin tape; передаётся
  в `margin_pairs` arg).

Defaults подкрепляются probe-tested values.

**W4. `pyom.wind` print-debugging spam в stderr.**

Probe: PyOM в момент call'а печатает full JSON payload + arg names в
stderr — это **встроенная** debug-печать (видно в моём probe outputs
выше). Не отключается через стандартные mech'ы (`-W` / logging level).

**Решение для plan:** adapter wrap'ает PyOM calls в `contextlib.
redirect_stderr` (или fd-level redirect) для скрытия spam'а от
end-user'а. Pre-existing problem (probably same в existing
`calculate_inductance_from_number_turns_and_gapping` — verify в Phase
0; добавить общий wrapper).

### 🟢 Note (к сведению)

**N1. Существующий `MagneticAnalytics` port остаётся неизменным.**

T132 добавляет новый `LeakageInductanceAnalyzer` port (Q6); existing
`mag_verify_field` use case continue использовать `MagneticAnalytics`
без изменений. Phase E2 hexagonal cleanup (T131) подтвердил —
addition of port'а это правильный путь.

**N2. PyOM `calculate_leakage_inductance` принимает `source_index` —
leakage направленный.**

Source winding → all-other leakage. Для трансформатора с N обмотками
получаем (N-1) values. Pilot fixture (2 обмотки: primary + secondary)
— один Lσ_primary→secondary. Если user задаёт 3+ обмотки (например,
ultralinear OPT с tap'ом + secondary) — adapter возвращает dict
{winding_name: Lσ}.

**Решение для plan:** `LeakageInductanceResult` VO имеет:
```python
class LeakageInductanceResult(BaseModel):
    source_winding: str  # имя source winding'а
    leakage_to: dict[str, float]  # имя target → Lσ [H]
    coupling_factor: float  # k = √(1 - Lσ/L)
```

`coupling_factor` derived: для N=2 trivial; для N>2 — pairwise.

**N3. `MagneticComponent.section_layout=None` →
`mag_verify_field` use case unchanged.**

Probed: PyOM `calculate_inductance_from_number_turns_and_gapping`
(existing call в `mag_verify_field`) **не** требует layered coil —
работает с only `functionalDescription` (windings list) + bobbin.
Layered description (sections/layers/turns) — required только для
**leakage** calc.

То есть backward compat (Q9) гарантирована автоматически: existing
`mag_verify_field` не запускает `pyom.wind` → не страдает от
layered-coil требования.

**N4. Pilot wire diameter: `Round 0.224 - Grade 1` или `Round 0.25 -
Grade 1`.**

A3 mitigation: для 3500 primary turns в E 42/15 (window area 202 mm²)
typical thin enamel wire `Round 0.224` (AWG ~32) fits comfortably с
fill factor ~0.5. Реальные Hammond 1627A используют ~AWG 32 для
primary; secondary AWG 22-24 (`Round 0.5 - Grade 1`). Pilot fixture
обновить с этих values.

**N5. Spec §3 reference: «PyOM `calculate_leakage_inductance`
поддерживает multi-section» — verified.**

Каталог PyOM 1.3.10 содержит функцию (`hasattr(pyom,
'calculate_leakage_inductance')` returns True; docstring confirms
multi-winding support). Spec вопрос Q3 отвечен probe'ом — proceeded
to design.

### Решения для Plan-фазы

1. **A1 → domain pattern в именах** + adapter mapping name→index.
2. **A2 → adapter helper** `_normalize_bobbin_columns(bobbin,
   core_full)`.
3. **A3 → pilot fixture с realistic wire** (`Round 0.224 - Grade 1`
   primary, `Round 0.5 - Grade 1` secondary).
4. **W1 → exception-as-data detection** в adapter (pattern из T113).
5. **W2 → refactor shared `_build_operating_point` helper** в existing
   PyOM adapter.
6. **W3 → ДВА insulation поля** в `InterleavingPattern`
   (`inter_section_thickness_m` + `bobbin_margin_m`).
7. **W4 → stderr redirect wrapper** для PyOM calls (apply ко всем
   PyOM methods в adapter).
8. **N2 → `LeakageInductanceResult`** VO с `leakage_to: dict[str,
   float]` (поддержка N>2 windings) + `coupling_factor`.

### Phase-структура (готовит Plan)

| Phase | Что | Файлы | Est |
|-------|-----|-------|-----|
| **A** | Domain + port (no adapter wiring): `InterleavingPattern`, `WindingSection` (если оставляем), `LeakageInductanceResult`, `MagneticComponent.section_layout` field + validation, `ports/outbound/leakage_inductance_analyzer.py` | 1 new domain file, 1 extend, 1 new port | ~3h |
| **B** | Adapter implementation: extend `PyOpenMagneticsAnalytics` (или сосед `PyOpenMagneticsLeakage` — рассмотреть в plan'e) с `calculate_leakage_inductance` + `_normalize_bobbin_columns` + shared `_build_operating_point` refactor + stderr redirect | 1 extend, 1 helper | ~3h |
| **C** | Use case `analyze_interleaved_leakage` + acceptance test (physics-based monotonicity + absolute bound) + composition wiring | 1 new use case, 1 new acceptance | ~4h |
| **D** | Pre-push gate + commit + PR | n/a | ~1h |

**Total:** ~11h работы; реально 1.5-2 рабочих сессии (близко к BACKLOG
estimate 1-2 дня).

**Spec status:** Clarified → **Analyzed** (готов к Plan-фазе и/или
implementation).

---

## Phase B PyOM probe results (2026-05-21)

Probe-script `probe_phase_b.py` запущен внутри `efactory:linux`. Полные
факты для adapter implementation:

**Сигнатуры (из docstring'ов; `inspect.signature` на pybind11 не работает):**

- `wind(coil_json, repetitions, proportion_per_winding_json, pattern_json,
  margin_pairs_json) -> json`
- `wind_by_sections(coil_json, repetitions, proportion, pattern,
  insulation_thickness) -> json` (section-only, не нужен для Lσ).
- `calculate_leakage_inductance(magnetic_json, frequency, source_index) ->
  json` — 3-arg сигнатура подтверждена.

**Return shape `calculate_leakage_inductance`:**

```python
{
    'leakageInductancePerWinding': [
        {'nominal': 0.0, 'unit': None, ...},        # entry 0: source winding (self = 0)
        {'nominal': 0.0001672, 'unit': None, ...},  # entry 1: target winding
        # ... один entry per winding
    ],
    'methodUsed': 'Energy',
    'origin': 'simulation',
}
```

Source entry (по `source_index`) — self-leakage 0.0 (информационно).
Остальные entries — Lσ от source к каждому target обмотке.

**Bobbin null gotcha (Analyze §A2 confirmed):**

- `Bobbin E42/15` из `get_bobbins()` имеет `processedDescription.columnWidth
  = None` и `columnDepth ≈ 5.45e-315` (uninitialized memory).
- `pyom.wind` принимает bobbin **без** patches (не валидирует columns).
- `pyom.calculate_leakage_inductance` тоже не падает на raw bobbin
  на happy path (probe выполнил patches заранее — нужно verify
  без patches в Phase B implementation; pattern: всегда patch для
  defensive coding).
- Patched values: `columnWidth = windingWindow.width` (E 42/15: 0.0074 m),
  `columnDepth = 0.015` (E 42/15 stack length, hardcoded — TODO extract
  via `core_full.processedDescription`).

**Exception-as-data (Analyze §W1):**

На happy path не воспроизводится — PyOM возвращает proper dict.
Detector оставляем precautionary (для bad-geometry / unfit-wire
error case'ов, которые в Stage E T113 видели).

**`wind` margin_pairs:**

`[[0.001, 0.001]]` (1 mm left/right margin) — verified рабочее значение.

**Phase B implementation impact:**

- `_translate_pattern_to_indices(layout, windings) -> list[int]` —
  natural map name → component.windings position.
- `_normalize_bobbin_columns(bobbin, core_full)` — always-apply
  defensive patch для PyOM bobbin перед leakage call.
- `_build_operating_point(component)` — extract из existing
  `_calculate_blocking`, переиспользовать в leakage path.
- `calculate_leakage_inductance(component, source_winding)` —
  выбирает source_index (по имени → position), вызывает PyOM,
  парсит `leakageInductancePerWinding` → `LeakageInductanceResult`.

---

## Phase B closure — infrastructure-only (2026-05-21)

**Status:** все domain/port/adapter infrastructure готово (Phase B), но
**runtime backend leakage недоступен** — PyOM `calculate_leakage_
inductance` consistently возвращает `[CALCULATION_ERROR] Mesh generation
failed: induced field data is empty` для любого fixture в текущей
PyOM 1.3.10 setup. Pattern закрытия — copy T129 (Frohlich material +
DC-bias load line) "infrastructure для downstream tasks".

**Что entered investigation (4+ часа Phase B):**

1. Probe PyOM API через `.pyi` stub + METADATA: подтверждены сигнатуры,
   обнаружены `magnetic_autocomplete`, `mas_autocomplete`,
   `process_inputs`, `simulate` как candidate orchestration helpers.
2. Bobbin column null fix через `_normalize_bobbin_columns` — error
   меняется с `INVALID_BOBBIN_DATA` на `Mesh generation failed`.
3. `magnetic_autocomplete(magnetic, {})` перед leakage — autocomplete
   стирает column patches; re-patch после autocomplete не помогает.
4. `process_inputs(inputs)` добавляет `magneticFieldStrength` slot к
   excitation, **но значение остаётся `None`** (process_inputs не
   знает про magnetic geometry).
5. `calculate_magnetic_field_strength_field(operating_point, magnetic)`
   — separate FEM call, возвращает `{'data': 'Exception: bad optional
   access'}` (std::optional unwrap на пустом). Circular dependency:
   leakage нуждается в computed magneticFieldStrength, но public API
   для compute падает на тех же inputs.
6. Прогон всех accepted leakage models (`BinnsLawrenson` — единственный
   валидный; `Roshen/Margueron/Petros/Energy` reject'ает schema).
   Grid auto-scale on/off + precision up — без эффекта.
7. **Полный official `simulate(inputs, magnetic, models)` pipeline** —
   возвращает тот же `Mesh generation failed`. Подтверждает, что баг
   не в нашем payload, а в PyOM C++ MKF layer.
8. **Cross-material sweep (12 PyOM-catalog materials)**: 3C90, 3C94,
   3C95, N87, N97, Kool Mu 60, XFlux 60, Hi-Flux 60, MPP 60, 3F3,
   3F36, N49 — все 10 ferrite/powder материалов return тот же mesh
   error, 2 (Kool Mu 60 / Hi-Flux 60) дополнительно reject'аются
   `cannot use at() with string` JSON schema issue.

**Корневая причина:** PyOM MKF C++ engine (closed-source binary в wheel)
не может построить mesh для valid coil/core/operating point payload.
Возможные направления (требует upstream access):
- MKF source review (https://github.com/OpenMagnetics/MKF) — какое
  optional поле required для `induced field data`?
- Open GitHub issue
  (https://github.com/OpenMagnetics/PyOpenMagnetics/issues).
- Try PyOM 1.4.x / 1.2.x — может быть version-specific regression.
- Switch backend → Elmer FEM (T133 в BACKLOG, изначально planned для
  field validation, теперь становится primary path для leakage).

**Что Phase B доставила (готово к use cases без runtime backend):**

| Артефакт | Файл | Тесты |
|---|---|---|
| 3 domain VO + section_layout field | `src/domain/magnetic.py` | 14 unit (test_magnetic.py) |
| Port Protocol + 2 errors | `src/ports/outbound/leakage_inductance_analyzer.py` | — |
| 3 adapter helpers | adapter.py module-level | 10 unit (test_helpers.py) |
| Adapter method + _build_operating_point shared refactor | adapter.py instance | — |
| Exception-as-data detection (wind + leakage paths) | adapter.py | manual probe |
| Integration test (4 scenarios, skipif probe fails) | test_pyom_leakage.py | skips on host AND container |

**BACKLOG entry:** T13X — "PyOM leakage backend investigation (mesh
failure root cause OR upgrade OR Elmer pivot)". См. BACKLOG.md.

**Phase C/D не запускаются** до решения backend issue ИЛИ переключения
на Elmer (T133). Domain/port/adapter scaffolding T132 готов принять
любой backend — это и есть infrastructure value Phase B.

**Spec status:** Analyzed → **Implemented (infrastructure-only)**.
