---
topic: fem.2d-planar-zhang-gap
description: 2D-planar FEM E-core ~3x inherent gap к ZHANG — для closure нужен 3D mesh
tags: [fem, elmer, getdp, e-core, 3d, zhang]
---
# 2D-planar FEM на E-core: inherent gap ~3× к ZHANG analytical

**Правило.** Если требуется FEM cross-check к ZHANG-style analytical
(`PyOM calculate_inductance`) для **E-core / EI / EE** OPT — сразу
планируй **3D mesh** (`emit_e_core_geo_3d` + `dimensionality='3d'`).
**Пропусти 2D iteration** для этой геометрии.

Для axisymmetric topology (toroidal, pot-core) 2D-axisymmetric OK.
Для leakage-only расчётов (T132 / T135) 2D также достаточен (поле
сосредоточено в window, out-of-plane эффекты вторичны).

**Почему.** Все 2D-planar варианты дают +182…242% к PyOM ZHANG на
pilot OPT 6П14П SE:
- Split-coil + Dirichlet BC.
- Single-coil + Infinity BC (Robin).
- Linear µ_r=8000 или nonlinear Frohlich.

Это **physics, не bug.** ZHANG reluctance model assumes fully closed
magnetic circuit; 2D-planar inherently captures 3D out-of-plane
leakage + fringing effects. 3D mesh с air gaps закрыл gap до -13.3%
(Lp = 6.04 H, acceptance ±25% к ZHANG 6.96 H).

**Источник.** T133 Phase 3 empirical 2026-05-21.

**Anti-pattern.**
```bash
# Часы на 2D iteration с E-core — бесполезно
elmer-emit-e-core-geo.py --dim 2d-planar --split-coil
ElmerSolver case.sif   # gap > 200% к analytical
```

**Правильно.**
```python
from adapters.outbound.fem_elmer import emit_e_core_geo_3d
geometry = emit_e_core_geo_3d(dimensions, gap_m=20e-6)
# Mesh sizing 20μm/5mm = ~10K nodes (см. fem.elmer-3d-mumps-ceiling).
```

**См.** `DECISIONS.md 2026-05-21` ADR «FEM 2D-planar inherent gap».
T133 spec `specs/T133-elmer-fem-pivot/`.
