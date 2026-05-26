---
topic: magnetics.pyom-leakage-broken
description: PyOM calculate_leakage_inductance broken — use Erickson analytical formula
tags: [magnetics, pyopenmagnetics, leakage, erickson, formula]
---
# PyOM `calculate_leakage_inductance` mesh broken — use Erickson

**Правило.** НЕ используй `pyom.calculate_leakage_inductance(...)`
для расчёта leakage inductance OPT — функция broken на ВСЕХ versions
PyOM 1.3.0 → 1.3.12. Используй existing efactory adapter
`adapters.outbound.leakage_inductance_analytical.AnalyticalLeakage`
(pure-Python Erickson sandwich-transformer formula + PyOM только для
geometry lookup).

**Почему.** PyOM MKF C++ mesh layer consistently возвращает:
```
[CALCULATION_ERROR] Mesh generation failed: induced field data is empty
```
Даже через official `simulate(inputs, magnetic, models)` pipeline.
Cross-material sweep (12 materials), version sweep, `magnetic_
autocomplete` / `process_inputs` orchestration — НЕ помогают.

**Источник.** T132 Phase B investigation 2026-05-21 (4+ часа).

**Anti-pattern.**
```python
# 4 часа потерь
mag = pyom.wind(magnetic_spec)
result = pyom.calculate_leakage_inductance(mag, freq, idx)
# → [CALCULATION_ERROR] всегда
```

**Правильно.**
```python
from adapters.outbound.leakage_inductance_analytical import AnalyticalLeakage
analyzer = AnalyticalLeakage(pyom_module=pyom, magnetic_analytics=...)
result = await analyzer.analyze(component, frequency_hz=...)
# Erickson formula + PyOM-catalog geometry lookup, без mesh.
```

**См.** `DECISIONS.md 2026-05-21` ADR «Leakage inductance:
Erickson analytical». `specs/T132-interleaved-leakage/spec.md`.
