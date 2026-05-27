---
topic: fem.elmer-stranded-coil-loop
description: Elmer Stranded Coil для OPT primary через 2 windows — нужны mesh bridges или Body Force
tags: [fem, elmer, coil, opt, e-core, current-density]
---
# Elmer Stranded Coil mechanism — connected 3D loop required

**Правило.** Если моделируешь OPT primary winding на center leg в 3D
Elmer с E-core (primary проходит через **2 disjoint windows** —
left + right), Coil mechanism требует **connected loop**. Варианты:

- **Mesh bridges через top + bottom yokes** (preferred — physically
  correct): добавь `coil_bridge_top` + `coil_bridge_bottom` Volume
  boxes; `Master Bodies(4) = 2 3 [bridge_top] [bridge_bottom]`;
  `Coil Closed = Logical True`.
- **Simple Body Force** с явной current density:
  `Current Density 3 = N·I/A` vector (работает для acceptance ±25%,
  но `div(J)` implicitly violated — physics approximation).

**Почему.** Closed coil (`Coil Closed = Logical True`) с двумя
disjoint window volumes даёт:
```
CoilSolver: Crappy potentials: No positive/negative current sources
```
Windows не connected без yoke bridges, current loop не замкнут.

Open coil + `Coil Start` / `Coil End` BCs пропускает current через
CoilSolver, но **Whitney AV не consume coil current без proper
Component-binding syntax**. Component-level `Coil Type` /
`Number of Turns` reported как `Unused keywords` — требуется
investigation в Elmer Models Manual.

**Источник.** T133 Phase 3d.2 Coil probe 2026-05-21.

**Anti-pattern.**
```
! Disjoint windows + Coil Closed → CoilSolver fail
Component 1
  Master Bodies(2) = 2 3
  Coil Closed = Logical True
End
```

**Правильно (вариант с mesh bridges).**
```
! Add coil_bridge_top + coil_bridge_bottom Volume boxes in .geo
Component 1
  Master Bodies(4) = 2 3 4 5
  Coil Closed = Logical True
End
```

**Правильно (вариант с Body Force, simpler).**
```
! Skip Coil mechanism, direct current density vector
Body Force 1
  Current Density 3 = Real $ N*I/A_window
End
```

**См.** T133 Phase 3d.2 retrospective. BACKLOG follow-up для proper
Component-binding.
