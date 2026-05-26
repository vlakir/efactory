---
topic: spice.floating-secondary-leak
description: Floating secondary OPT — auto-inject R_dc_leak (1 MΩ к GND) перед Fourier
tags: [spice, magnetics, ngspice, fourier, floating-node]
---
# Floating secondary OPT — R_dc_leak перед Fourier analysis

**Правило.** Если в схеме output transformer (OPT) с **floating
secondary** (оба конца подключены только к load resistor, ни один не
grounded), и ты собираешься делать Fourier analysis на `v(sec_a)` —
**обязательно inject `R_dc_leak sec_b 0 1MEG`** перед `.four`.

**Почему.** Без DC reference у floating node ngspice присваивает
arbitrary DC offset, и Fourier'у получает нерелевантную fundamental
magnitude (часто 0 или nonsense). Leak 1 MΩ к GND фиксирует DC
reference; signal через 8 Ω load испытывает ток ~8·10⁻⁶ A peak
(пренебрежимо).

**Источник.** T131 Phase D acceptance test post-processing
2026-05-21.

**Anti-pattern.**
```
* OPT secondary плавает — оба конца только в load
R_load sec_a sec_b 8
* Запуск Fourier на v(sec_a) — fundamental поломан
```

**Правильно.**
```
R_load sec_a sec_b 8
R_dc_leak sec_b 0 1MEG     ; ← обязательно
.tran 1u 10m
fourier 1000 v(sec_a)
```

**См.** `tests/acceptance/test_saturable_thd_se_amp.py::
_add_secondary_dc_leak` (canonical implementation).
