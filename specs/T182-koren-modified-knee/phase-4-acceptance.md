# Phase 4 — Acceptance probe T182 / T183 / T184 / T185

**Дата:** 2026-06-04
**Статус:** PARTIAL — все 4 variant-задачи реализованы и сравнены;
strict spec-thresholds не закрыты, но direction-of-improvement и
trade-offs полностью документированы.
**Артефакт спеки:** §4 (Success Criteria SC#2, SC#4, SC#6).

## 1. Summary table (4-variant comparison)

### EL34 SC#2 (T185 denser fixture, 58 points, Vg2=250V)

| Variant | knee mean | plateau mean | overall mean |
|---------|-----------|--------------|--------------|
| canonical T031 (no σ) | **286%** | 15% | high |
| canonical + σ (T183) | 55% | 48% | mid |
| **modified-knee (T182)** | **36%** | 45% | mid |
| reefman (T184) | 55% | 48% | mid |

**Verdict:** SC#2 target <30% knee NOT MET; best = 36% (modified-knee).
T185 denser fixture слегка улучшил best (39% → 36%) и **expose'ил**
что canonical был оптимистично-оценён в первом Phase 4 (146%): со
denser knee sampling canonical knee error растёт до 286%, что
показывает истинный structural gap canonical-вариант.

### 300B SC#4 (31 points)

| Variant | cutoff mean | mid mean |
|---------|-------------|----------|
| canonical T031 (no σ) | 16% | 17% |
| canonical + σ (T183) | 21% | 29% |
| **modified-cutoff (T182)** | **12%** | 19% |

**Verdict:** SC#4 cutoff target <30% MET (best 12% modified-cutoff);
SC#4 mid target <15% NOT MET (best 17% canonical). Sigma weighting
**degrades** performance на 300B (~17% noise vision data с wide Ia
range), что contradicts EL34 finding — sigma optimum зависит от
data quality + Ia range.

### 6П13С SC#6 (19 points, sanity-check)

| Variant | KG1 | EX | Vk | mean err |
|---------|-----|-----|----|----|
| canonical T031 | 50965 | 2.67 | — | 21% |
| modified-knee (T182) | **12925** | 2.40 | 70 | 15% |

KG1 target ∈ [500, 10000]: FAIL (12925 just above). EX ∈ [1.0, 2.0]:
FAIL (2.40). DIRECTIONAL improvement holds: KG1 dropped 3.9×, EX
dropped 0.27, mean err improved 28%.

## 2. Key findings

### A. Sigma weighting закрывает большую часть canonical gap, но trade-offs

**EL34 finding:** canonical+σ улучшает knee 286% → 55% (5× drop), но
plateau 15% → 48% (3× degradation). Sigma re-distributes weight от
high-Ia plateau к low-Ia knee — фундаментальный trade-off для wide-
range data.

**300B finding:** canonical+σ **ухудшает** оба cutoff (16% → 21%) и
mid (17% → 29%). Возможные причины:
- 300B vision-extracted noise хуже EL34 (1962 vs 1950 datasheet quality);
- triode формула без modifier'а уже балансирует σ-effect через `sqrt(KVB+Va²)` term;
- σ amplifies noise points при low Ia → шумная convergence.

**Conclusion:** σ weighting — **conditional improvement**, не universal
panacea. Default `relative_weights=False` остаётся правильным для
backwards-compat T031 acceptance. Opt-in flag даёт пользователю выбор.

### B. Modified-knee всё ещё лучший для EL34 knee

T182 modified-knee variant даёт best knee mean = 36% на denser fixture,
тогда как canonical+σ и Reefman оба сидят на 55%. Это означает что
`(1-exp(-Va/Vk))` modifier **structurally** добавляет ~20 п.п. к knee
улучшению, что и было целью T182.

Однако plateau (45%) хуже canonical-T031 (15%) — modified-knee
жертвует plateau accuracy за knee. Это видно в fitted parameters:
KVB=1.0 (lower bound), EX=1.05 (lower bound), KG1=181 (vs canonical
1000s). Fitter ищет local minimum который over-fits knee region при
заплате plateau.

**Open question:** Может быть, weighted-region loss (knee + plateau
с custom weights) — лучший подход чем global σ. Но это вне T182 scope.

### C. T184 Reefman pentode = canonical equivalence для EL34

Reefman model (Sec 4.2 Eq 14-17) использует triode-like E1 form
`sqrt(KVB + Vg2²)` вместо bare `Vg2`. Для EL34 (Vg2=250, KVB~24):

```
ratio = sqrt(24 + 250²) / 250 = 1.000192
```

→ Numerically identical к canonical (delta < 0.02%). Phase 4 results
confirm: Reefman knee=55%, canonical+σ=55%, Reefman plateau=48%,
canonical+σ=48% — bit-exact match.

**Theoretical value:** Reefman даёт **strict consistency** между
pentode и triode-strapped pentode mode (см. Reefman paper Sec 3.4.2).
Для low-Vg2 small-signal pentodes (Vg2 ≤ 100V) Reefman E1 substantially
diverges от canonical, что должно дать measurable improvement.

**Practical T184 status:** реализация ngspice-portable, bit-exact match
Python forward formula (`ngspice OP i(v3)=-113.44 mA` vs Python
`113.438 mA`). EL34 acceptance — no improvement (expected). Польза
проявится на other tubes (small-signal pentodes + triode-strapped).

### D. T185 denser EL34 fixture закрывает sampling gap

Phase 4 первого захода имело только 3 точки в SC#2 knee region
(Va<150, Vg∈[-10,-20]) → статистически слабо.

T185 добавил 22 точки в knee-Va range (Va ∈ [20, 175]) — теперь
knee region покрыт 10+ точками. Это:
- Поднял истинный canonical-T031 knee error с 146% → 286% (true
  reflection of structural limit).
- Дал stable метрику для variant сравнения.
- Acceptance verdict (best=36% modified-knee) теперь statistically
  defensible.

## 3. Acceptance verdicts (по spec §4)

| SC | Target | Best result | Verdict |
|----|--------|-------------|---------|
| SC#1 round-trip 12AX7/Ayumi-EL34 synthetic | ≤5%/≤2% | passes all variants | ✓ PASS |
| SC#2 EL34 knee mean <30%, max <40%, plateau <15% | 30%/40%/15% | **36%/72%/45%** | ✗ PARTIAL — modified-knee best |
| SC#3 modified-knee round-trip | ≤7%/≤3%/≤15% | passes (synthetic) | ✓ PASS |
| SC#3b modified-cutoff round-trip | ≤7%/≤3%/≤20%/≤25% | passes (synthetic) | ✓ PASS |
| SC#4 300B cutoff <30%, mid <15% | 30%/15% | **12%/17%** | ✗ PARTIAL — cutoff ✓, mid ✗ |
| SC#5 ngspice OP smoke | bit-exact | passes for all variants | ✓ PASS |
| SC#6 6П13С KG1 ∈ [500, 10000], EX ∈ [1.0, 2.0] | bounds | **12925/2.40** | ✗ DIRECTIONAL |
| SC#7 DECISIONS ROI matrix | ADR-T182a/b | written | ✓ PASS |

**Net:** 5/8 PASS, 3/8 PARTIAL/DIRECTIONAL — T182 ships как
substantial improvement-with-honest-gaps, not as full closure.

## 4. Artifacts

- `fixtures/el34_mullard.json` — 58 точек (Phase 0 36 + T185 22), Mullard EL34 1960.
- `fixtures/300b_we.json` — 31 точка, Western Electric 300B 1950.
- `fixtures/6p13s_iv.json` — 19 точек, USSR 6П13С handbook.
- `scripts/t182_phase4_probe.py` — 4-variant comparison probe runner.
- `phase-4-results.json` — machine-readable acceptance metrics.

## 5. Future work (не блокеры T182)

- **T184 follow-up** — Reefman improvement пилот на small-signal pentode
  (low Vg2). EL34 не показал benefit; lo-Vg2 EF86/PF86 должны.
- **Derk pentode model** (Reefman paper Sec 4.4, Eq 23-25) — 3 extra
  params (α_s, β, A) для knee modeling. Может закрыть EL34 knee gap
  если modified-knee не хватает. Открыть отдельной T-задачей если
  понадобится.
- **Per-region weighted loss** — gradient-aware loss с разными
  weights для knee/plateau regions (вместо global σ). Возможный путь
  закрыть SC#2 target <30%.
