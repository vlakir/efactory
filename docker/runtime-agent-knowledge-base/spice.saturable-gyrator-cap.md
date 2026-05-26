---
topic: spice.saturable-gyrator-cap
description: Saturable магнетика в SPICE — XSPICE gyrator-capacitor, не PWL current-source
tags: [spice, magnetics, ngspice, saturable, gyrator-cap]
---
# Saturable магнетика — XSPICE gyrator-capacitor

**Правило.** Когда нужно смоделировать насыщающийся магнитный
сердечник в SPICE с активными элементами (лампа, MOSFET с
нелинейностями), используй **XSPICE `core` + `lcouple`** (gyrator-
capacitor approach, Hamill 1993). НЕ используй PWL current-source +
C_int integrator с B-source.

**Почему.** PWL B-source с integrator + active Koren tube model даёт
**numerical blow-up** (magnitudes ~1e+65) из-за algebraic loop:
производные напряжений на C_int через B-source создают зависимость,
которую ngspice не может разрешить. Gyrator-cap изолирует
нелинейность в магнитной области через voltage⇄MMF и flux⇄current
gyration, активная электрическая часть остаётся «снаружи».

**Источник.** T131 Phase E redesign 2026-05-21. Изначально (Phase A)
использовали PWL подход — пилот не сходился; Phase E redesign на
XSPICE gyrator-cap — pilot acceptance passed.

**Anti-pattern.**
```
* НЕ ДЕЛАЙ ТАК — algebraic loop с активной нагрузкой
B_flux flux 0 V=idt(v(pri))
C_int flux 0 1
B_force pri 0 V=H_from_B(v(flux))
```

**Правильно.**
```
* XSPICE gyrator-capacitor (Hamill 1993)
.MODEL saturable_core core
A1 pri pri_int saturable_core
L_couple pri_int 0 1u           ; coupling indutor
```

**См.** `DECISIONS.md 2026-05-21` ADR «Saturable магнетика в SPICE:
XSPICE gyrator-capacitor». T131 spec `specs/T131-saturable-thd/`.
