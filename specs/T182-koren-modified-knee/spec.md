# Spec: Modified Koren-pentode formula + Koren-triode cutoff modifier

**Статус:** Analyzed
**Дата создания:** 2026-06-04
**Связанные документы:**
- `BACKLOG.md` → исходная карточка T182 (перенесена в BOARD Doing).
- `specs/T031-tube-curve-fitting/phase-0-probe.md` §3, §6 — knee
  error data на Mullard EL34 (mean 40.2%, max 79.1% в knee region
  vs 15.1% / 70.3% на plateau).
- `specs/T031-tube-curve-fitting/phase-4-acceptance.md` — 6П13С
  unusual params (`KG1=51000`, `EX=2.67`) как косвенный symptom.
- `src/domain/tube_fitting/_formulas.py` — Koren triode +
  Ayumi/Koren-pentode formulas, target рефактора.
- `src/domain/tube_fitting/_params.py`, `_bounds.py`,
  `_fitter.py` — pydantic VO + scipy.curve_fit обвязка.
- `DECISIONS.md` — добавятся ADR-T182a (выбор modified Koren vs
  Reefman vs Cohen-Hélie, ROI matrix) + ADR-T182b (формальное
  определение `koren-modified-knee` pentode + `koren-modified-cutoff`
  triode variants: math form, parameters, bounds, .lib emission).

---

## 1. Overview

Каноническая Koren-pentode формула
(`E1^EX / KG1 · atan(Va/KVB)`) и каноническая Koren-triode формула
(`E1^EX / KG1` с softplus-плейт-зависимостью) — это лучший
компромисс «5-7 параметров / сходимость scipy.curve_fit / SPICE-
portable .lib» для типичной mid-region операции (plateau pentode,
Va ≫ knee у триода). Но обе формы дают систематический gap к
реальной physics:

- **Pentode knee:** `atan(Va/KVB)` поднимается слишком пологo; T031
  Phase 0 §6 EL34 probe — max ошибка 79% Ia в knee region.
- **Triode strong cutoff:** softplus tail слишком гладкий; KP-knob
  одновременно управляет cutoff sharpness и mid-region distortion,
  что вынуждает либо завышать KP (overshoot в mid), либо мириться
  с слишком длинным tail (300B SE — реальный use case).

T182 добавляет два modifier-варианта:
1. **`koren-modified-knee` (pentode):** plate-term умножается на
   `(1 - exp(-Va/Vk))` — sharper knee, plateau unchanged.
2. **`koren-modified-cutoff` (triode):** Ia умножается на
   sigmoid-фактор от Vg — резкий cutoff floor без overshoot в mid.

Канонические Koren triode/Ayumi-pentode формулы НЕ меняются;
существующие built-in `.lib`, user overlay'и, T031 round-trip
тесты работают unchanged. Choice variant'а — opt-in CLI flag
`--formula-variant`.

## 2. Сценарии использования

- **S1.** Инженер вызывает `efactory tube fit-from-points <name>
  --type pentode --points data.json --formula-variant
  koren-modified-knee`. Получает .lib с better knee fidelity.
- **S2.** Инженер вызывает аналогично с `--type triode
  --formula-variant koren-modified-cutoff` для 300B и получает
  triode-модель, лучше воспроизводящую strong-cutoff tail.
- **S3.** Существующий пользователь без `--formula-variant` флага
  продолжает получать `koren-canonical` поведение — все built-in
  `.lib`, все user overlay'и, все T031 fixtures работают unchanged.
- **S4.** Round-trip регрессионные тесты T031 SC#1 (12AX7 canonical
  triode, Ayumi-pentode synthetic) остаются ✓ без изменений.
- **S5.** Phase 0-style cross-check Mullard EL34 на `koren-modified-
  knee`: knee error <30% (vs текущие 40-80%) при сохранении plateau
  <15%.
- **S6.** Mullard 300B cross-check на `koren-modified-cutoff`: strong
  cutoff (Vg ∈ [-100, -60] V) error <30% при сохранении mid-region
  (Vg ∈ [-30, -60] V) <15%.

## 3. Functional Requirements

### Pentode (knee modifier)

- **ДОЛЖНА** ввести `KorenModifiedKneePentodeParams` (pydantic VO):
  все поля canonical pentode (`mu`, `ex`, `kg1`, `kg2`, `kp`, `kvb`,
  `screen_v`) + `vk` (knee voltage scale, `Field(gt=0)`).
- **ДОЛЖНА** ввести `koren_modified_knee_pentode_ia(vg, va, params)`
  в `_formulas.py`:
  ```
  E1 = (Vg2/KP) · ln(1 + exp(KP · (1/MU + Vg/Vg2)))
  Ia = (2 · E1^EX / KG1) · atan(Va/KVB) · (1 - exp(-Va/Vk))
  ```
  при `E1 > 0`; иначе 0. Возвращает Ia в mA (как канонические
  формулы).
- **ДОЛЖНА** добавить `KOREN_MODIFIED_KNEE_PENTODE_BOUNDS` и
  `_TYPICAL` initial guess в `_bounds.py` (`vk` typical: 50 V,
  bounds: (5.0, 500.0)).

### Triode (cutoff modifier)

- **ДОЛЖНА** ввести `KorenModifiedCutoffTriodeParams` (pydantic VO):
  все поля canonical triode (`mu`, `ex`, `kg1`, `kp`, `kvb`,
  `vct`) + `vc_off` (cutoff center, **negative**) + `vs_off`
  (transition sharpness, `Field(gt=0)`).
- **ДОЛЖНА** ввести `koren_modified_cutoff_triode_ia(vg, va, params)`
  в `_formulas.py`:
  ```
  E1 = (Va/KP) · ln(1 + exp(KP · (1/MU + (Vg+Vct)/sqrt(KVB+Va²))))
  Ia_canonical = 2 · E1^EX / KG1
  Ia = Ia_canonical · sigmoid((Vg - Vc_off) / Vs_off)
       где sigmoid(x) = 1/(1 + exp(-x))
  ```
  При `E1 > 0`; иначе 0. Возвращает mA.
- **ДОЛЖНА** добавить `KOREN_MODIFIED_CUTOFF_TRIODE_BOUNDS` и
  `_TYPICAL` в `_bounds.py`:
  - `vc_off` ∈ (-200, -0.5), typical: -40.0 (для 300B-style).
  - `vs_off` ∈ (0.5, 30.0), typical: 5.0.

### Variant switch

- **ДОЛЖНА** ввести `FormulaVariant` Literal в `_params.py`:
  `'koren-canonical' | 'koren-modified-knee' | 'koren-modified-cutoff'`.
- **ДОЛЖНА** добавить CLI flag `--formula-variant` в `efactory tube
  fit-from-points` (default: `koren-canonical`). Валидация:
  - `koren-modified-knee` требует `--type pentode`;
  - `koren-modified-cutoff` требует `--type triode`.
  Mismatch → понятная ошибка от CLI, exit code != 0.
- **ДОЛЖНА** в выходном `.lib` записать выбранный variant как
  комментарий (`* fit variant: koren-modified-knee`) И через
  ngspice-syntax в `B`-source формулы (multiplier term из formula).
- **МОЖЕТ** добавить `_FORMULA_DEFAULTS` mapping для типичных
  init-guess (Vk=50 V для pentode, Vc_off=-40 V для triode).

### TDD coverage

- **ДОЛЖНА** содержать round-trip тесты для каждой modified-variant
  формулы: synthetic Ia(Vg, Va) из known params → fitter → recovery
  error ≤ заявленные tolerance (см. §4 SC#3, SC#3b).

### Backward compatibility

- **НЕ ДОЛЖНА** менять `koren_triode_ia`, `ayumi_pentode_ia`,
  `KorenTriodeParams`, `AyumiPentodeParams`, `KOREN_TRIODE_BOUNDS`,
  `AYUMI_PENTODE_BOUNDS`, T031 round-trip suite в `tests/unit/
  domain/tube_fitting/`.
- **НЕ ДОЛЖНА** менять existing built-in `data/models/tubes/*/*.lib`
  (re-fit — это T171).
- **НЕ ДОЛЖНА** перетягивать fitting pipeline на Cohen-Hélie / Reefman
  (rejected альтернатива в DECISIONS ADR).

## 4. Success Criteria

- **SC#1 (canonical backward-compat).** T031 round-trip suite — pass
  unchanged: ≤5% MU/KG1/KP/KVB, ≤2% EX (canonical 12AX7 + Ayumi
  6V6). Тесты `test_fitter.py` для canonical-варианта не
  модифицируются.
- **SC#2 (knee improvement EL34).** На Mullard EL34 vision-extracted
  fixture (36 points, скопировано из T031 Phase 0 §4):
  - knee region (Va < 150 V, Vg ∈ [-10, -20] V): **mean |err| < 30%**
    и **max |err| < 40%** (vs текущие ~40% / ~80%).
  - plateau region (Va ≥ 200 V): **mean |err| < 15%**.
- **SC#3 (pentode-modified round-trip).** Synthetic Ia/Ig2 из known
  `koren-modified-knee` params → fitter → recovery:
  - MU/KG1/KP/KVB/KG2: ≤7%
  - EX: ≤3%
  - Vk: ≤15%
- **SC#3b (triode-modified round-trip).** Synthetic Ia из known
  `koren-modified-cutoff` params → fitter → recovery:
  - MU/KG1/KP/KVB: ≤7%
  - EX: ≤3%
  - Vc_off: ≤20%
  - Vs_off: ≤25%
- **SC#4 (300B cutoff improvement).** На Mullard 300B vision-
  extracted fixture (vision-pass в Phase 4 этой задачи, 25-35
  points expected):
  - strong-cutoff region (Vg ∈ [-100, -60] V): **mean |err| < 30%**.
  - mid-region (Vg ∈ [-30, -60] V): **mean |err| < 15%**.
- **SC#5 (.lib emission portable).** Выходной `.lib` с
  modified-knee и modified-cutoff variants компилируется и
  работает в ngspice (smoke `bridge sim-run op` на EL34 SE-стенде +
  300B SE-стенде с резистивной нагрузкой).
- **SC#6 (6П13С re-fit как sanity-check для modified-knee).** Re-fit
  6П13С на T031 Phase 4 fixture (`6P13S_iv.json`, 19 points) с
  `--formula-variant koren-modified-knee`:
  - `KG1 ∈ [500, 10000]` (vs текущие 51000).
  - `EX ∈ [1.0, 2.0]` (vs текущие 2.67).
  - SC#2 control point error ≤ T031 Phase 4 baseline (mean 4.5%,
    max 6.2%).
  Если хотя бы один из bounds не выполняется — это **не** failure
  T182 (Phase 4 closed на canonical), но требует разбора в Phase
  4 этой задачи: что compensated formula limit, и где modified-
  variant решает / не решает.
- **SC#7 (DECISIONS hygiene).** В `DECISIONS.md`:
  - ADR-T182a — ROI matrix (Koren-canonical / Koren-modified-knee+
    cutoff / Reefman / Cohen-Hélie / neural), 3-5 строк на row,
    columns: params count, knee accuracy class, fit complexity,
    .lib portability, status (current/rejected/future).
  - ADR-T182b — формальное определение modified variants: math
    form (с уравнениями), параметры с physical interpretation,
    bounds rationale, .lib emission syntax.

## 5. Key Entities

- **`FormulaVariant`** — `Literal['koren-canonical', 'koren-
  modified-knee', 'koren-modified-cutoff']` в `_params.py`.
- **`KorenModifiedKneePentodeParams`** — новый pydantic VO в
  `_params.py`. Поля: `mu`, `ex`, `kg1`, `kg2`, `kp`, `kvb`,
  `screen_v`, **`vk`**.
- **`KorenModifiedCutoffTriodeParams`** — новый pydantic VO в
  `_params.py`. Поля: `mu`, `ex`, `kg1`, `kp`, `kvb`, `vct`,
  **`vc_off`**, **`vs_off`**.
- **`koren_modified_knee_pentode_ia(vg, va, params)`** — forward Ia в
  `_formulas.py`.
- **`koren_modified_cutoff_triode_ia(vg, va, params)`** — forward Ia
  в `_formulas.py`.
- **Bounds + typical** — `KOREN_MODIFIED_KNEE_PENTODE_BOUNDS`,
  `KOREN_MODIFIED_CUTOFF_TRIODE_BOUNDS`,
  `KOREN_MODIFIED_KNEE_PENTODE_TYPICAL`,
  `KOREN_MODIFIED_CUTOFF_TRIODE_TYPICAL` в `_bounds.py`.
- **Fitter dispatch** — `fit(dataset, variant=...)` в `_fitter.py`
  делает routing по `variant`; multi-start core unchanged.
- **CLI flag** — `--formula-variant` в `efactory tube fit-from-
  points` (adapter + use case input DTO + .lib writer).
- **EL34 fixture** — `specs/T182-koren-modified-knee/fixtures/
  el34_mullard.json`, 36 vision-extracted точек из T031 Phase 0 §4
  (без PDF — datasheet external artefact).
- **300B fixture** — `specs/T182-koren-modified-knee/fixtures/
  300b_mullard.json`. Vision-extracted в Phase 4 этой задачи из
  Western Electric / Mullard datasheet (locate через
  frank.pocnet.net или audiomatica).
- **6П13С fixture (для SC#6)** — переиспользуем
  `/tmp/t031-probe/6P13S_iv.json`; копируем в
  `specs/T182-koren-modified-knee/fixtures/6p13s_iv.json` для
  persistence.
- **FitResult** — `params` поле расширяется union'ом:
  `KorenTriodeParams | AyumiPentodeParams |
  KorenModifiedKneePentodeParams | KorenModifiedCutoffTriodeParams`.

## 6. Assumptions & Constraints

- **Стек:** Python 3.13, scipy.optimize.curve_fit, numpy. Без новых
  C-extension зависимостей. Multi-start backend = тот же, что в
  T031 (`method='trf'`, seeded RNG default = 42).
- **SPICE portability:** обе modifier-формулы emit-ятся в
  ngspice-syntax. `exp` + `atan` + sigmoid (= `exp` form) поддержаны
  `B`-source.
- **EL34 acceptance dataset:** 36 точек из T031 Phase 0 §4 (vision-
  extracted, Mullard EL34 1962). Переиспользуем — no re-extract.
- **300B acceptance dataset:** vision-pass в Phase 4 этой задачи.
  Datasheet: Mullard или Western Electric, найти через
  `frank.pocnet.net/sheets`. Ожидаемое количество — 25-35
  vision-extracted точек, покрывающих Vg ∈ [-100, -10] V,
  Va ∈ [50, 500] V. Если vision не вытянет (300B-1937 печать
  blurry) — fallback на manual JSON по handbook'ам.
- **Identifiability risk.** 7-param pentode-modified (был 6) и
  8-param triode-modified (был 5-6) — это много для 20-40-точечного
  fit. Multi-start с увеличенным числом random starts (5 → 8 для
  modified variants) и сужёнными `vk` / `vc_off` / `vs_off`
  bounds — необходимое условие. Это будет проверено в Phase 1
  TDD и записано в Analyze.
- **Coverage gate:** ≥80% по `src/domain/tube_fitting/` — стандартный
  проектный gate, не ослабляем.

## 7. Out of Scope

- **Re-fit built-in .lib через modified variants.** T171 уже
  зарегистрирован отдельно; T182 даёт алгоритмическую basis, не
  массовый re-fit.
- **Audit 2× множителя в `koren/*.lib`** (T172).
- **Cohen-Hélie / Reefman implementation.** Только rejected
  alternatives в ADR-T182a ROI matrix; никакого кода. Decision
  flip — отдельная T-задача.
- **Pentode-triode-mode (Vg2 ≪ Va) extension.**
- **CLI UX heuristics.** Только explicit `--formula-variant`; никаких
  `--auto-select-variant` heuristic'ов, никакого introspection из
  vision data.
- **Изменение Ayumi-pentode** (`ayumi_pentode_ia`). Канонический
  Koren-pentode form остаётся reference для round-trip Ayumi tests.
- **Изменение Koren triode mid-region.** Только cutoff modifier;
  если canonical mid-region (Va ∈ [50, Vk·5] для 300B) точен — не
  трогаем.
- **Knee modifier для триода.** Знаем, что не нужен — у Koren-triode
  plate-зависимость в `sqrt(KVB + Va²)` уже smooth-bridge, в knee
  region (Va ≪ Vp, mod 300B) accuracy достаточная по plate-direction.
  Подтверждено Phase 0 §6 (gap там был pentode-side).

---

## Clarify (заполняется Claude)

### Resolved

- **C1 (mathematical form).** ✓ Sigmoid-soft-rectified atan (вариант a)
  с +1 параметром `Vk` для pentode-knee. **Math form (final):**
  `plate_term = atan(Va/KVB) · (1 - exp(-Va/Vk))`. Свойства:
  zero-preserving (Va=0 → 0), plateau-preserving (Va→∞ → π/2),
  monotone, C∞-smooth, gradient бережёт scipy multi-start.
- **C2 (modified round-trip tolerance).** ✓ 7% / 3% / 15% (core /
  EX / Vk) для pentode-modified. Симметрично для triode-modified:
  7% / 3% / 20% / 25% (core / EX / Vc_off / Vs_off — Vs_off
  identifiability слабее, поэтому относительный bound шире).
- **C3 (scope).** ✓ (β) — symmetric pentode knee+cutoff (фактически
  knee-only modifier у pentode + cutoff-only modifier у триода).
  Vladimir работает с 300B SE — strong-cutoff на 300B критичен.
- **C4 (.lib emission portability).** ✓ Mandatory ngspice-syntax
  emission. Sigmoid и `(1 - exp(-Va/Vk))` оба раскладываются в
  elementary `B`-source выражения; никаких runtime lookup tables.
- **C5 (EL34 fixture persistence).** ✓ Скопируем 36 vision-точек
  в `specs/T182-koren-modified-knee/fixtures/el34_mullard.json`.
  PDF не коммитим (external artefact). Дополнительно копируем
  T031 Phase 4 `/tmp/t031-probe/6P13S_iv.json` в
  `fixtures/6p13s_iv.json` для SC#6.
- **C6 (DECISIONS ROI matrix scope).** ✓ Quick literature snapshot
  (3-5 строк per row, 1-2 citations per row), не academic review.
- **C7 (SC#6 — 6П13С re-fit как sanity-check).** ✓ Добавлено как
  SC#6. Если modified-knee на 6П13С даёт «здоровые»
  `KG1 ∈ [500, 10000]` / `EX ∈ [1.0, 2.0]` при сохранении
  ≤7% / ≤6% control point error — это direct подтверждение, что
  modified variant физичнее. Если не даёт — разбор в Phase 4
  (без блокера на merge).

### Open questions

- (пусто; clarify завершён)

---

## Analyze (заполняется Claude)

### 🔴 Critical

- **A-C1. `FitResult.params` Union расширение — cross-cutting.**
  `FitResult.params` в `_params.py:225` — `KorenTriodeParams |
  AyumiPentodeParams`. T182 расширяет на 4 типа. Затрагивает:
  `_render_lib` / `_validate_params_match_header` в
  `tube_lib_writer.py`; `_load_seed_from` / `_fit_triode` /
  `_fit_pentode` в `fit_tube_from_points.py`;
  `_emit_tube_fit_summary` в `app.py`. Без сквозной diff-strategy
  тесты пройдут, но runtime упадёт на первом modified-fit'е.
  **План:** одновременная инкрементация (param VO → writer dispatch
  → use case dispatch → CLI dispatch) в Phase 1+2+3; Pre-push gate
  mypy + e2e test покрывают.

- **A-C2. Identifiability 7-8 параметров маржинальна для 20-40 точек.**
  Канонический Ayumi: 6 params, screen_v known → 5 effective fit
  unknowns; 20+ points достаточно. Modified-knee добавляет `vk` →
  6 effective; Phase 4 EL34 fixture даёт 36 points, OK. Modified-
  cutoff триод: 5-6 → 7-8 effective; 300B vision-extract ожидаем
  25-35 points — **минимально достаточно** только при правильных
  bounds. **Митигация:** для modified variants `n_starts = 8` (vs
  canonical 5), сужённые bounds на `vk` / `vc_off` / `vs_off`,
  seeded multi-start determinism сохраняется.

### 🟡 Warning

- **A-W1. Modified-cutoff триод + `--include-vct` — semantic overlap.**
  И `vct` (cathode contact), и `vc_off` (cutoff threshold) сдвигают
  cutoff edge. Двойная identifiability → degenerate. **Решение:**
  `--include-vct` и `--formula-variant koren-modified-cutoff` —
  **mutually exclusive** на CLI. Документируется в help-strings и
  валидируется в use case.

- **A-W2. Vector callback `_*_vec` в `_fitter.py` дублирует scalar
  formulas из `_formulas.py` (DRY violation).** Это T031 design
  (vec — internal, scalar — public reference). T182 продолжает тот
  же паттерн: `koren_modified_knee_pentode_ia` в `_formulas.py` +
  `_koren_modified_knee_pentode_ia_vec` в `_fitter.py`. Альтернатива
  — рефакторинг scalar → vec — out of scope (отдельная T-задача,
  если когда-нибудь возникнет).

- **A-W3. `vc_off` bounds — negative range, log-uniform sampling не
  работает.** Linear-uniform для `vc_off` (как для MU/EX). Для
  `vs_off` (positive) — log-uniform. **Решение:** обновлённый
  `_modified_cutoff_triode_initial_guesses` использует
  `linear-uniform` ветку для всех negative-domain params.

- **A-W4. Acceptance probe 300B vision-extract в автономном
  ночном режиме.** WebFetch может не вытащить PDF с
  frank.pocnet.net (firewall / login). **Fallback:** manual
  fixture JSON по published handbook values (Western Electric
  300B 1933 + GE 1950 reissue tables). Если оба пути не сработают
  — SC#4 markером BLOCKED и закрывается в follow-up T-задаче
  (не блокирует merge остальных Phase'ов).

- **A-W5. CLI `--formula-variant` semantics: pentode vs triode.**
  `koren-modified-knee` валиден только для `--type pentode`;
  `koren-modified-cutoff` — только для `--type triode`. Mismatch
  должен дать понятную ошибку до запуска fitter'а. **Решение:**
  CLI argparse-level guard + use case secondary check (defence
  in depth).

### 🟢 Note

- **A-N1. KB sync (T134) минимально требуется.** T182 не вводит
  новую slash-команду — только CLI flag. `agent.command-routing`
  mapping `/tube-add-from-datasheet` остаётся unchanged (slash
  передаёт vision-extracted JSON в CLI; variant choice — это CLI
  concern, агент не выбирает сам). Уровень 1 (KB topic) — **не
  требуется**. Уровень 2 (deterministic test) — добавим один
  case-test для `agent.command-routing` regression. Уровень 3 —
  при следующем infrastructure change.

- **A-N2. `_TYPICAL` для 300B-style power triode.** Текущий
  `KOREN_TRIODE_TYPICAL` калиброван на small-signal preamp
  (MU=70, KP=300). Для modified-cutoff fit'а 300B нужен второй
  typical: MU=4, EX=1.4, KG1=1500, KP=800, KVB=200, vc_off=-50,
  vs_off=5. Multi-start добавит этот typical как 2-ой anchor.

- **A-N3. `.lib` emission модифицированных вариантов** —
  два новых rendering helpers в `tube_lib_writer.py`. G1 line
  получает modifier-term:
  - knee: `... / KG1 * ATAN(V(P,K)/KVB) * (1 - EXP(-V(P,K)/VK))`
  - cutoff: triode-`G1` умножается на
    `1/(1+EXP(-(V(G,K)-VC_OFF)/VS_OFF))`.

- **A-N4. Phase commit boundaries (методика dreamteam).**
  Каждая Phase = отдельный commit на ветке, всё схлопывается в
  squash-merge:
  - Phase 1: domain (`_params`, `_bounds`, `_formulas`) + tests.
  - Phase 2: fitter (`_fitter.py`) + tests.
  - Phase 3: use case + adapter (writer) + CLI flag + tests.
  - Phase 4: acceptance fixtures + probe scripts + results.
  - Phase 5: DECISIONS + CHANGELOG + KB regression test.

- **A-N5. Phase 4 SC#6 (6П13С re-fit) noisy, но direct.** Existing
  T031 Phase 4 fixture (19 points, 5 curves). Re-fit с modified-
  knee → если `KG1` упал из 51000 в 1000-5000, и `EX` упал с 2.67
  в 1.0-2.0 — это прямой физический win. Если нет — Phase 4
  raises вопрос: что 6П13С datasheet actually does в knee, и нужно
  ли Vk дополнительный фактор. Не блокер merge T182.

### Phase plan (после Analyze)

- **Phase 1 — Domain (TDD).** `KorenModifiedKneePentodeParams` +
  `KorenModifiedCutoffTriodeParams` в `_params.py`; bounds + typicals
  в `_bounds.py`; `koren_modified_knee_pentode_ia` +
  `koren_modified_cutoff_triode_ia` в `_formulas.py`;
  `FormulaVariant` Literal; reference-tests на синтетике (manual
  hand-calc) + monotonicity + plateau-/cutoff-bounds. Commit:
  «T182 Phase 1: domain modified-knee + modified-cutoff formulas».
- **Phase 2 — Fitter integration (TDD).** `_koren_modified_knee_
  pentode_ia_vec`, `_koren_modified_cutoff_triode_ia_vec` (internal
  duplication T031-style); `fit_koren_modified_knee_pentode`,
  `fit_koren_modified_cutoff_triode` (multi-start n_starts=8);
  round-trip SC#3 / SC#3b tests. Commit: «T182 Phase 2: fitter
  integration with multi-start».
- **Phase 3 — Use case + adapter + CLI.** Расширение
  `FitTubeFromPointsRequest` (variant Literal); dispatch в use
  case; tube_lib_writer два новых render-helpers с ngspice-syntax
  G1 modifier-term; CLI `--formula-variant` flag + mutually-
  exclusive validation; e2e tests. Commit: «T182 Phase 3: CLI
  flag + ngspice-portable .lib emission».
- **Phase 4 — Acceptance.** EL34 fixture (`fixtures/el34_mullard.
  json` из T031 Phase 0 §4 — manual transcribe 36 точек),
  6П13С fixture (copy из `/tmp/t031-probe/6P13S_iv.json`);
  300B fixture (WebFetch → vision-extract или manual). Probe
  scripts `phase-4-acceptance/{el34,300b,6p13s}.py` записывают
  knee/cutoff metrics + JSON results. Markdown summary `phase-4-
  acceptance.md`. Commit: «T182 Phase 4: acceptance EL34 + 300B
  + 6П13С».
- **Phase 5 — Docs + KB regression.** ADR-T182a (ROI matrix
  Koren / Reefman / Cohen-Hélie / neural); ADR-T182b (math formal
  variants); `CHANGELOG.md [Unreleased]` block; KB regression test
  для `agent.command-routing` (что вызов «fit а с modified knee»
  всё ещё попадает в `/tube-add-from-datasheet`, не путается с
  чем-то новым). Commit: «T182 Phase 5: DECISIONS ROI matrix +
  CHANGELOG».
- **Pre-push gates.** `uv run ruff check`, `uv run ruff format
  --check`, `uv run mypy src/`, `uv run pytest`. BOARD `Doing →
  Done` правка на ветке как **последний commit** перед push
  (см. CLAUDE.md «Closing-правка»). PR `gh pr create` →
  self-review → squash-merge решает Vladimir утром.

