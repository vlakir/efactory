---
topic: magnetics.interleaving-n-squared
description: Interleaving reduction Lσ ∝ 1/N² (N = inter-winding interfaces)
tags: [magnetics, leakage, opt, interleaving, hf-rolloff]
---
# Interleaving reduction: Lσ ∝ 1/N²

**Правило.** Если пользователь спрашивает «как уменьшить HF-rolloff
аудио OPT» — предложи **interleaved sandwich layout**, и оцени
эффект через **factor 1/N²**, где N = число inter-winding interfaces:
- P-S → N=1.
- P-S-P → N=2 → leakage / 4.
- P-S-P-S-P (5-section symmetric) → N=4 → leakage / 16.

**Источник.** Standard sandwich-transformer theorem; Erickson &
Maksimović §15.5 + Hurley & Wölfle §4.6. Verified exact для zero-
insulation case на pilot T132 (σ_2/σ_3 = 4.0, σ_2/σ_5 = 16.0).

**Применение.** Для compact-core OPT (E 42/15 на 6П14П SE) typical
HF-3dB ≈ 50 kHz с simple P-S layout. Interleaving до P-S-P-S-P
поднимает до ≈200 kHz при той же геометрии core.

**Anti-pattern.** Увеличивать turns ratio для лучшего HF-extension
— это работает в обратную сторону (больше turns → больше leakage).
Или менять core на physically больший — Bandwidth-bandwidth ↑ через
geometry, но cost ↑ и size ↑. Interleaving — самый дешёвый путь.

**Trade-off.** Inter-winding capacitance ↑ ~линейно с N — может
создать resonance на высокой частоте. На audio range (≤200 kHz)
обычно ниже первого peak.

**См.** `application/analyze_interleaved_leakage.py` use case.
`tests/acceptance/test_interleaved_leakage_monotonicity.py`.
