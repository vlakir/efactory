---
topic: tubes.formula-variant-choice
description: Decision tree выбора `--formula-variant` для `efactory tube fit-from-points` (T182/T184/T186 cascade). Default `auto` per tube_type — обычно ничего менять не нужно.
tags: [tubes, fitting, koren, modified-knee, modified-cutoff, formula-variant]
---

# `--formula-variant` choice — когда и зачем

В T182/T184/T186 efactory обзавёлся 4 Koren-style formula variants для
tube-fitting. Большинство случаев — **default `auto`** даёт оптимум.
Этот topic — про edge cases.

## Default `auto` (что происходит без `--formula-variant`)

CLI выбирает variant по `--type`:

| --type | auto → variant | Why |
|--------|---------------|-----|
| `pentode` | **`koren-modified-knee`** | Phase 4 best на EL34 (knee 36% vs canonical 286%) |
| `triode` | **`koren-canonical`** | T031 baseline; small-signal triodes (12AX7/ECC83) хорошо ложатся |

**Practical advice: не задавай `--formula-variant` руками** — auto
покрывает 95% случаев правильно.

## Когда `koren-modified-cutoff` (триод opt-in)

Override default `koren-canonical` для триода если:

- **Power triode** (300B, 2A3, EL84-strapped-triode) с published curves
  до глубокого cutoff (Vg < -50V) — canonical's плавный cutoff даёт
  systematic underestimation strong-cutoff region.
- **Acceptance focus** на cutoff transition (например, validating
  bias point near cutoff edge) — modified-cutoff даёт 12% mean vs
  canonical 16% на Western Electric 300B (Phase 4 SC#4).

**Symptom canonical-fit на 300B:** plateau region OK (mean 17%), но
deep-cutoff Vg=-100V predict overshoots actual Mullard data на ~25-40%.

**Trade-off:** modified-cutoff увеличивает mid-region error с 17% до
19% (Phase 4) — лёгкая degradation в mid trade'ится за резкий cutoff.
Если mid-region точность критична — оставь canonical.

```bash
# Power triode opt-in:
efactory tube fit-from-points X300B --type triode \
    --points 300b.json --formula-variant koren-modified-cutoff
```

**Mutually exclusive с `--include-vct`** — оба моделируют cathode-side
cutoff edge (semantic overlap). Use case rejects combination.

## Когда `koren-canonical` (override default)

Override default `koren-modified-knee` для пентода если:

- **Backwards-compat с existing built-in `.lib`** — все T031-Phase-5
  встроенные модели (6Ж38П / 6П13С / 6Ж32П) fit'нуты canonical;
  для consistency-test re-fit идёт через canonical.
- **Plateau-only datasheet** — если у тебя курвы только при Va ≥ 200V
  (no knee data), modified-knee modifier `(1-exp(-Va/Vk))` не
  identifiable; canonical проще и не уступит.
- **Round-trip test** против T031 baseline — explicit canonical нужен.

```bash
# Backwards-compat re-fit:
efactory tube fit-from-points 6P13S --type pentode \
    --points 6p13s.json --formula-variant koren-canonical
```

## Research variants (не используй без явной причины)

В domain layer есть ещё два variant'а — **доступны только через
Python API**, не через CLI:

- **`koren-reefman-pentode`** (T184, Reefman 2016 Sec 4.2) — для
  high-Vg2 power-pentodes (EL34 типичный) **numerically near-identical**
  к canonical (E1 form ratio sqrt(KVB+Vg2²)/Vg2 ≈ 1.0002 при Vg2=250).
  Польза — для small-signal pentodes (Vg2 ≤ 100V) и
  triode-strapped consistency. Не has CLI flag — research/API only.
- **`koren-derk-pentode`** (T186, Reefman 2016 Sec 4.4 Eq 23-27) —
  9-param super-formula с α_s/β/A modifiers + derived α constraint.
  Phase 4 EL34 показал: knee mean=61% (worse чем modified-knee
  36%) — overparametrized без joint Ia+Ig2 data. Targeted на
  small-signal pentodes с screen-current measurements
  (Reefman Fig 4 PF86 success demo). Не has CLI flag — research/API only.

См. `DECISIONS.md` ADR-T182c (Derk empirical collapse) и
`specs/T182-koren-modified-knee/phase-4-acceptance.md` §C-bis.

## Decision tree summary (TL;DR для агента)

```
Tube type pentode? → default auto = koren-modified-knee → ship.
  Edge case: backwards-compat / plateau-only → --formula-variant koren-canonical
Tube type triode?  → default auto = koren-canonical → ship.
  Edge case: power triode (300B/2A3, cutoff focus) → --formula-variant koren-modified-cutoff
                                                    (НЕ комбинируй с --include-vct)
```

## Phase 4 acceptance evidence

См. `specs/T182-koren-modified-knee/phase-4-acceptance.md` §1
(5-variant comparison table) для empirical numbers. Quick recap
для EL34 (T185 denser fixture, 58 points, Vg2=250V):

| Variant | knee mean | plateau mean | params |
|---------|-----------|--------------|--------|
| canonical (no σ) | 286% | 15% | 6 |
| canonical + σ | 55% | 48% | 6 |
| **modified-knee (default)** | **36%** | 45% | 7 |
| reefman (research) | 55% | 48% | 6 |
| derk (research) | 61% | 45% | 9 |

«Best» зависит от региона интереса:
- Plateau accuracy critical → canonical (15%) — но modified-knee
  тоже acceptable (45%) при значительно лучшем knee.
- Knee/cutoff accuracy critical → modified-knee (36%) — default auto.
- 300B-style power triode strong-cutoff → modified-cutoff (12%).

## См. также

- KB `tubes.curve-fitting` — основной T031 pipeline + KG2 fallback
  + JSON schema.
- Spec `specs/T182-koren-modified-knee/spec.md` — full variant
  definitions (modified-knee Eq, modified-cutoff sigmoid).
- ADR-T182a (ROI matrix), ADR-T182b (variants formal definition),
  ADR-T182c (Derk empirical collapse), ADR-T182d (CLI cleanup
  decision) в `DECISIONS.md`.
