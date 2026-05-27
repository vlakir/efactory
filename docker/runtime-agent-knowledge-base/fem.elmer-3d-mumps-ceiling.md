---
topic: fem.elmer-3d-mumps-ceiling
description: Elmer 3D MUMPS direct ceiling ~10K nodes на 4 GB — НЕ mesh > 20K без iterative
tags: [fem, elmer, mumps, mesh, memory]
---
# Elmer 3D MUMPS direct: ceiling ~10K nodes на 4 GB

**Правило.** Для Elmer 3D mesh full E-core OPT:
- **Default MUMPS direct** с mesh sizing **20μm/5mm** (proven
  baseline, ~10K nodes, ~14s on dev-host).
- **НЕ пытайся mesh > 20K nodes без verified iterative path** —
  система может перезагрузиться (Vladimir-а перезагружало).
- Если нужно finer mesh — либо больше RAM (>16 GB), либо адаптивный
  mesh refinement через Distance + Threshold fields (concentration
  nodes только near gaps), либо Elmer rebuild с AMS preconditioner
  (отдельная задача, см. BACKLOG).

**Почему.** MUMPS direct solver на edge basis (Maxwell formulation)
имеет O(N²·BW) memory blow-up. На dev-host 4 GB RAM 39K tetra даёт
**segfault rc=139 + system crash**.

Iterative alternatives в default elmerfem-csc PPA НЕ работают:
- `Preconditioning = BoomerAMG` (Hypre) не сходится для edge basis
  (designed для node Laplacian).
- `Preconditioning = "ams"` (Auxiliary Maxwell Space, proper для
  edge Maxwell) reports `Unknown preconditioner type: ams, feature
  disabled` — Hypre AMS не вкомпилирован в PPA build.

**Источник.** T133 Phase 3d.2 2026-05-21.

**Anti-pattern.**
```python
geometry = emit_e_core_geo_3d(..., mesh_size=10e-6)  # 39K tetra
# → segfault, system crash
```

**Правильно.**
```python
geometry = emit_e_core_geo_3d(..., mesh_size=20e-6, gap_local=5e-3)
# ≈10K nodes, ~14s, safe baseline
```

**См.** T133 phase 3d.2 retrospective. BACKLOG T136 (Elmer rebuild
с AMS) — потенциальное расширение.
