---
topic: magnetics.pyom-bobbin-patch
description: PyOM bobbin processedDescription columnWidth/Depth — uninitialized garbage, patch обязателен
tags: [magnetics, pyopenmagnetics, bobbin, fem, patch]
---
# PyOM bobbin patch для FEM-touching paths

**Правило.** Если вызываешь ЛЮБОЙ PyOM API, который trigger'ит mesh
validation (`calculate_magnetic_field_strength_field`, `plot_
field_map`, и т.п.) — **обязательно patch** bobbin
`processedDescription.columnWidth` и `columnDepth` ПЕРЕД вызовом:

```python
bobbin = pyom.find_bobbin_by_name('Bobbin E42/15')
bobbin.processedDescription.columnWidth = (
    bobbin.functionalDescription.windingWindows[0].width
)
bobbin.processedDescription.columnDepth = core.processedDescription.depth
```

**Почему.** Bug в PyOM C++ catalog initializer:
- `columnWidth = None`
- `columnDepth ≈ 5.45569116e-315` (uninitialized memory garbage)

PyOM `calculate_leakage_inductance` bails out с `INVALID_BOBBIN_DATA`
без patch'а. Mesh-touching API additionally требуют full geometry —
без patch'а получишь segfault или wrong results.

**Альтернатива.** Использовать только PyOM **catalog-only APIs**
(`find_*_by_name`, `calculate_core_data`, `get_bobbins`) — они НЕ
trigger'ят mesh validation, bobbin garbage там не релевантен.

**Источник.** T132 Phase B probe 2026-05-21.

**См.** `DECISIONS.md 2026-05-21` ADR.
