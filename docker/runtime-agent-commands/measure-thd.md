---
description: Измерить THD на одной частоте (TRAN + ngspice fourier).
argument-hint: '[NETLIST] --freq <Hz> --v-in-peak <V> [--load-ohm Ω]'
allowed-tools: Bash
---

Пользователь хочет измерить single-point THD через `efactory bridge
measure thd` на готовом SPICE-netlist'е.

Args от пользователя: `$ARGUMENTS` (минимум `--freq` и `--v-in-peak`;
netlist — позиционный или auto-detect).

1. Определи `NETLIST` (тот же auto-detect pattern, что `/measure-gain`).

2. Запусти: `efactory bridge measure thd <NETLIST> --freq <Hz>
   --v-in-peak <V> [...]`.

3. T023 НЕ делает target-power calibration loop — для этого нужен
   полный sweep через `analyze_distortion_spectrum` (T131). Если
   пользователь спрашивает «какой THD на 1 Вт?», вычисли v_in_peak
   обратной формулой (V_peak ≈ √(2·P·R_load)·gain⁻¹) или предложи
   запустить sweep через T131-aware пайплайн.

4. Default `--load-ohm 8` (audio standard). Если в netlist'е нагрузка
   другая (1 кΩ для divider'а, например) — передай `--load-ohm
   <Ом>` для корректного `measured_power_w`.

5. Покажи stdout (`thd_percent`, `dominant_harmonic_n`, `measured_power`).
   На ошибке — stderr.

6. После успеха упомяни запись в `.efactory/sim-results/
   <TS>-thd.json`.
