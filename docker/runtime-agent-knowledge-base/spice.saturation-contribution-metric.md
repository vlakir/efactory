---
topic: spice.saturation-contribution-metric
description: Saturation contribution = THD@f_low - THD@f_high — diagnostic для saturable models
tags: [spice, magnetics, thd, acceptance, saturation]
---
# Saturation contribution metric для saturable acceptance gating

**Правило.** Когда задаёшь acceptance-gate для saturable transformer
THD-теста, **обязательно включай diagnostic** `saturation_contribution
= THD@f_low - THD@f_high > threshold_pp` (например > 0.5 pp).

**Почему.** Чистая abs-THD bound (`THD < 5%`) недостаточна:
- Compact-core configurations (E 42/15 в SE 6П14П) выходят за
  published bands для больших cores — false fail.
- Если saturable модель тихо broken (saturation curve не engaging),
  THD@f_low ≈ THD@f_high (только tube-only baseline) — abs-THD
  test pass, но реальной saturation modeling нет → false pass.

Positive `saturation_contribution` доказывает, что saturable модель
реально активна. Физика: при низкой частоте flux excursion `B =
V_pri / (2π f N A)` максимален → насыщение работает; при высокой
частоте B → 0 → saturable OPT прозрачен → THD@f_high == tube-only
THD.

**Источник.** T131 Phase E acceptance gate 2026-05-21.

**Anti-pattern.**
```python
assert thd_at_1kHz < 5.0  # tube-only тоже проходит — false pass
```

**Правильно.**
```python
thd_low = measure_thd(freq=100, ...).thd_percent
thd_high = measure_thd(freq=10_000, ...).thd_percent
saturation_contribution = thd_low - thd_high
assert saturation_contribution > 0.5, 'saturable модель не engaging'
assert thd_low < 15.0, 'абс THD слишком высока'  # широкая bound OK
```

**См.** `specs/T131-saturable-thd/spec.md` §acceptance.
