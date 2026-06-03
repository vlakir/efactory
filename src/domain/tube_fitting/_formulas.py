"""
Forward Ia(Vg, Va) computations — каноническая Koren triode и Ayumi pentode.

Используется в двух местах:

1. Synthetic IVDataset generation для round-trip тестов (S4):
   построить (Vg, Va, Ia) точки из известных params, затем прогнать
   через fitter, проверить восстановление параметров.
2. Inside `scipy.optimize.curve_fit` callback'е (fitter callback).

Числовые reference values:

* 12AX7 Koren (MU=100, EX=1.4, KG1=1060, KP=600, KVB=300) at
  Vg=-2 V, Va=250 V → **Ia ≈ 0.953 mA** (manual hand-calc).
* EL34 Koren-pentode (MU=11, EX=1.35, KG1=650, KP=60, KVB=24,
  screen_v=250) at Vg=-12.2 V, Va=250 V → **Ia ≈ 113.3 mA**
  (Phase 0 probe).

Каноническая формула содержит **2× множитель** в числителе — это не
артефакт ngspice .lib syntax'а, это часть оригинальной публикации
Koren'а (см. _params.py docstring).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from domain.tube_fitting._params import AyumiPentodeParams, KorenTriodeParams

SOFTPLUS_LARGE_ARG: Final[float] = 50.0
"""arg > этого порога: log1p(exp(arg)) ≈ arg (без exp overflow)."""

SOFTPLUS_DEEP_CUTOFF: Final[float] = -100.0
"""arg < этого порога: log1p(exp(arg)) численно 0 → Ia = 0 (deep cutoff)."""


def koren_triode_ia(vg: float, va: float, params: KorenTriodeParams) -> float:
    """
    Канонический Koren triode forward Ia (А).

    Formula:

        E1 = (Va/KP) * ln(1 + exp(KP * (1/MU + (Vg+Vct) / sqrt(KVB + Va^2))))
        Ia = 2 * E1^EX / KG1   при E1 > 0; 0 иначе

    `Vct` (cathode contact potential) опционален; `None` → 0.
    Возвращает Ia в **mА**, поскольку весь pipeline работает в mА.
    """
    vct = params.vct if params.vct is not None else 0.0
    plate_norm = math.sqrt(params.kvb + va * va)
    arg = params.kp * (1.0 / params.mu + (vg + vct) / plate_norm)
    # softplus = log1p(exp(arg)); защита от overflow на двух краях.
    if arg < SOFTPLUS_DEEP_CUTOFF:
        return 0.0
    softplus = arg if arg > SOFTPLUS_LARGE_ARG else math.log1p(math.exp(arg))
    e1 = (va / params.kp) * softplus
    if e1 <= 0.0:
        return 0.0
    # KG1 — это ngspice .lib coefficient: возвращает Ia в Amperes.
    # Конвертируем в mA (×1000), чтобы весь pipeline остался в mA
    # (IVPoint.ia, FitResult.rms_residual_ma, и т.п.).
    return 2.0 * (e1**params.ex) / params.kg1 * 1000.0


def ayumi_pentode_ia(vg: float, va: float, params: AyumiPentodeParams) -> float:
    """
    Ayumi-style (Koren-pentode form) forward Ia (mA).

    Formula:

        E1 = (Vg2/KP) * ln(1 + exp(KP * (1/MU + Vg/Vg2)))
        Ia = (2 * E1^EX / KG1) * atan(Va/KVB)   при E1 > 0; 0 иначе

    где `Vg2 = params.screen_v`. Plate-term `atan(Va/KVB)` отвечает
    за knee region; для plateau region `atan` → π/2.
    """
    arg = params.kp * (1.0 / params.mu + vg / params.screen_v)
    if arg < SOFTPLUS_DEEP_CUTOFF:
        return 0.0
    softplus = arg if arg > SOFTPLUS_LARGE_ARG else math.log1p(math.exp(arg))
    e1 = (params.screen_v / params.kp) * softplus
    if e1 <= 0.0:
        return 0.0
    # KG1 в ngspice convention → Ia в Amperes; конвертируем в mA.
    return (2.0 * (e1**params.ex) / params.kg1) * math.atan(va / params.kvb) * 1000.0
