# Phase 4 — Acceptance probe T182

**Дата:** 2026-06-04
**Статус:** PARTIAL — modified variants дают чёткое улучшение (3-4× по knee
mean) над canonical T031, но строгие spec-thresholds (<30% knee mean,
<15% plateau) не достигнуты. Главное открытие — большая часть улучшения
приходит от **relative-error sigma weighting** (`σ = max(Ia, 1 mA)`),
встроенного в modified fitter'ы; structural knee modifier `(1-exp(-Va/Vk))`
дополнительно помогает в knee, но не закрывает gap.
**Артефакт спеки:** §4 (Success Criteria SC#2, SC#4, SC#6).

---

## 1. Summary table

| Test | Canonical (T031) | Modified + σ (T182) | Spec target | Verdict |
|------|------------------|---------------------|-------------|---------|
| **SC#2 EL34 knee mean** | 1.461 (146%) | **0.390 (39%)** | <0.30 | PARTIAL — 3.7× better, target not hit |
| SC#2 EL34 knee max | 2.336 (234%) | 0.727 (73%) | <0.40 | PARTIAL |
| SC#2 EL34 plateau mean | 0.148 (15%) | 0.180 (18%) | <0.15 | NEAR |
| **SC#4 300B cutoff mean** | 0.162 (16%) | **0.122 (12%)** | <0.30 | PASS (uplift 25%) |
| SC#4 300B mid mean | 0.174 (17%) | 0.191 (19%) | <0.15 | NEAR |
| **SC#6 6П13С KG1** | 50965 | **12925** | ∈[500, 10000] | DIRECTIONAL — 3.9× drop, just over upper |
| SC#6 6П13С EX | 2.673 | 2.400 | ∈[1.0, 2.0] | DIRECTIONAL — closer but >2.0 |
| SC#6 6П13С mean error | 0.213 (21%) | 0.151 (15%) | n/a | 28% улучшение |

**Net verdict.** SC#2/SC#4 не PASS по строгим thresholds, но
**direction-of-improvement демонстрирована** на каждом метрике для
каждой тубы. T182 ships как improvement, не как closure. Strict
target closure требует Tier-2 (Reefman) или Tier-1 (Cohen-Hélie)
formulations — отдельная T-задача (см. ADR-T182a ROI matrix).

## 2. Key finding: relative-error weighting vs knee modifier

В ходе Phase 4 эксперимента было обнаружено, что **большая часть
улучшения на EL34 приходит от `σ = max(Ia, 1 mA)` relative-error
weighting**, встроенного в modified fitter, а не от
`(1-exp(-Va/Vk))` knee modifier как такового.

Сравнение «canonical + sigma» (без modifier) vs «modified + sigma»
(с modifier) на EL34 даёт почти идентичные результаты:

| Fit variant | EL34 knee mean | plateau mean |
|-------------|-----------------|---------------|
| canonical, abs SSE (T031 default) | 1.461 | 0.148 |
| canonical + σ-weighting (probe) | 0.388 | 0.178 |
| modified-knee + σ-weighting (T182) | 0.390 | 0.180 |

**Интерпретация.** Knee modifier добавляет 1 параметр (`Vk`) — structural
gain в форме plate-term, но он *избыточен* на этой конкретной EL34
fixture, где KVB сам по себе (через `atan(Va/KVB)` с small KVB) уже
способен описать knee shape; не хватало правильной loss-функции.

**Implication для будущей работы.** σ-weighting может быть добавлен и
в canonical T031 fitter — это закроет большую часть EL34 knee gap
**без** перехода на modified variant. Однако это вне scope T182
(BACKLOG candidate, см. §6 follow-ups).

## 3. EL34 detail (SC#2)

Fixture: `el34_mullard.json` — 36 vision-extracted точек из Mullard
EL34 1962 datasheet (Vg2=250V), copy из T031 Phase 0 §4.

### Canonical T031 fit (absolute SSE, без modifier)

- params: `MU=14.65, EX=1.05 (lower bound!), KG1=162.6, KP=64.1, KVB=66.7`
- knee region (Va<150, Vg∈[-10,-20], n=3): **mean 146%, max 234%**
- plateau region (Va≥200, n=25): mean 15%
- **Symptom:** EX hits lower bound (1.05), KG1 small — fitter
  компенсирует absolute SSE доминированием high-Ia plateau точек.

### Modified-knee T182 fit (relative-error sigma + (1-exp(-Va/Vk)) modifier)

- params: `MU=14.60, EX=1.05 (still hits bound), KG1=181.3, KG2=2.4,
  KP=64.8, KVB=1.0 (hits bound), Vk=86.5`
- knee region: **mean 39%, max 73%** — 3.7× улучшение vs canonical
- plateau region: mean 18% — лёгкая деградация vs canonical (15%)
- **Symptom:** EX и KVB всё ещё на bounds; Vk нашёлся в физическом
  диапазоне 50-100 V.

### Spec target gap

- knee mean: 39% (target <30%) → **9 п.п. от target**.
- knee max: 73% (target <40%) → **33 п.п. от target**.
- plateau mean: 18% (target <15%) → 3 п.п. от target.

## 4. 300B detail (SC#4)

Fixture: `300b_we.json` — 31 vision-extracted точек из Western Electric
300B 1950 datasheet (Page 3 top, Ef=5.0V). Calibrated against published
op-point Eb=350V, Ec=-74V → Ia=60mA (Page 2): vision interp gives
59.5mA → 0.8% accuracy.

### Canonical T031 triode fit (absolute SSE)

- params: `MU=3.95 (≈ published 3.9 ✓), EX=1.98, KG1=11594, KP=152, KVB=5000 (hits bound)`
- cutoff region (Vg∈[-100,-60], n=11): mean 16%
- mid region (Vg∈[-60,-30], n=8): mean 17%

### Modified-cutoff T182 fit (relative-error sigma + sigmoid cutoff)

- params: `MU=3.76, EX=2.14, KG1=23496, KP=222, KVB=3296, Vc_off=-155.3, Vs_off=30.0 (hits bound)`
- cutoff region: **mean 12%** — 25% улучшение
- mid region: mean 19% — лёгкая деградация

### Notes

- Vc_off found at **-155 V** — far below the published cutoff knee
  (~-110V for Va=100). Это означает, что sigmoid модификатор сидит
  ниже data range и слабо влияет на cutoff region. Эффект приходит от
  σ-weighting, не от modifier.
- Vs_off=30 hits upper bound — sigmoid максимально мягкий, что
  подтверждает: modifier не активен.
- Cutoff уже <30% у canonical (16%), запас улучшения мал; модификатор
  не показал structural benefit на этой fixture.

## 5. 6П13С detail (SC#6 sanity-check)

Fixture: `6p13s_iv.json` — 19 vision-extracted точек, copy из T031
Phase 4 `/tmp/t031-probe/6P13S_iv.json` (Vg2=150V).

### Canonical T031 (T031 baseline на этой fixture)

- params: `MU=50.0, EX=2.673, KG1=50965 (!), KG2=10000, KP=37.0, KVB=8.6`
- mean error: 21%
- **Phase 4 T031 acceptance verdict** была ✓ (control point error
  4.5%), но params значения unusual — задача T182 проверяет, физичнее
  ли modified-knee.

### Modified-knee T182

- params: `MU=39.8, EX=2.400, KG1=12925 (3.9× меньше!), KG2=10000, KP=44.4, KVB=33.7, Vk=70.0`
- mean error: 15% — 28% улучшение
- **KG1 ∈ [500, 10000]**: 12925 — just over upper (target failed).
- **EX ∈ [1.0, 2.0]**: 2.400 — over (target failed).
- **Directional sanity ✓.** KG1 dropped 4× toward physical range,
  EX dropped 0.27 toward physical, mean error улучшен.

**Interpretation:** modified-knee частично корректирует
"off-physics" компенсацию canonical на 6П13С. Полная коррекция
(`KG1 < 10000`) требует sharper cutoff modifier или Tier-2 formula.

## 6. Follow-ups (BACKLOG candidates)

Из Phase 4 выделились новые задачи для BACKLOG:

- **T183 (candidate)** — добавить `σ = max(Ia, ε)` relative-error
  weighting в canonical T031 fitter (`fit_koren_triode`,
  `fit_ayumi_pentode`). Phase 4 показал — большая часть EL34
  улучшения приходит от σ, не от knee modifier. Должен проверить
  SC#1 round-trip не сломан.

- **T184 (candidate)** — Reefman / Cohen-Hélie pilot. Phase 4 EL34
  knee mean застрял на 39% (target 30%); Koren+modifier hit
  structural ceiling. Tier-2/Tier-1 pilot покажет, можно ли
  закрыть gap до <20% при приемлемом param count (Reefman ~8
  params).

- **T185 (candidate)** — improved EL34 fixture с более плотным knee
  sampling. Текущие 3 точки в Va<150 / Vg∈[-10,-20] недостаточны
  для статистики SC#2. Re-vision Mullard EL34 Page C2 с focus на
  knee.

## 7. Artefacts

- `fixtures/el34_mullard.json` — 36 точек, source T031 Phase 0 §4.
- `fixtures/300b_we.json` — 31 точка, vision-extracted T182 Phase 4
  из `frank.pocnet.net/sheets/084/3/300B.pdf`.
- `fixtures/6p13s_iv.json` — 19 точек, copy из T031 Phase 4
  `/tmp/t031-probe/`.
- `scripts/t182_phase4_probe.py` — probe runner (standalone, не unit-test;
  лежит в `scripts/` per ruff convention для one-off tooling).
  Запуск: `PYTHONPATH=src uv run python scripts/t182_phase4_probe.py`.
- `phase-4-results.json` — machine-readable acceptance metrics.

## 8. Phase 4 closure

Phase 4 **не блокер merge T182** (spec §4 SC#6 footnote: «не блокер
если хотя бы один bound не выполняется — требует разбора в Phase
4»). Закрываем с PARTIAL verdict и тремя BACKLOG candidates на
будущее.

Next: Phase 5 (DECISIONS + CHANGELOG + pre-push gates + PR).
