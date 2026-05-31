"""
Crossover detection для phase-margin (T153 Phase B.4).

Pure-domain helpers:

* `unwrap_phase_deg(real, imag)` — atan2 → continuous unwrapped phase
  в градусах.
* `find_unity_crossover(loop_gain)` — gain crossover (где |T|=0 dB
  downward) + интерполированная phase в этой точке. Возвращает
  `CrossoverResult` VO.

Алгоритм (Spec §3 «Crossover detection»):

1. magnitudes в dB по комплексным `(real, imag)` каждой точки sweep'а.
2. Если `|T| > 1` во всех точках → `LoopGainAlwaysAboveUnityError`
   (Q5=c, актionable: расширь `--f-high`).
3. Если нет ни одного DOWNWARD crossing'а 0 dB (`mag_db[k] >= 0 >
   mag_db[k+1]`) → `NoUnityGainCrossoverError`. Этот case включает как
   «всё ≤ 1» (Q5=a), так и «есть только UPWARD crossings» (non-
   monotonic).
4. Primary crossover — самый низкочастотный DOWNWARD. Linear
   interpolation в `log10(f)` / dB:

       t = mag_db[k] / (mag_db[k] - mag_db[k+1])
       log_f_cross = log10(f[k]) + t * (log10(f[k+1]) - log10(f[k]))
       f_cross = 10**log_f_cross

5. Phase в crossover'е: linear interp unwrapped phase по `t` между
   `phase_deg[k]` и `phase_deg[k+1]`.
6. `extra_crossovers_hz` — все DOWNWARD/UPWARD crossings кроме primary,
   отсортированные по частоте.

Точность ±2° margin при `points_per_decade ≥ 50` (Spec §6).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field

from domain.phase_margin import (
    LoopGainAlwaysAboveUnityError,
    NoUnityGainCrossoverError,
)

if TYPE_CHECKING:
    from domain.phase_margin_injection import LoopGain

_FROZEN = ConfigDict(frozen=True, extra='forbid')

_PHASE_WRAP_THRESHOLD_DEG = 180.0
_PHASE_WRAP_CYCLE_DEG = 360.0


class CrossoverResult(BaseModel):
    """
    Crossover analysis result (intermediate, не persisted напрямую).

    Возвращается `find_unity_crossover()` для downstream consumption
    use case'ом `measure_phase_margin` (Spec §3, Spec §5).
    """

    model_config = _FROZEN

    crossover_hz: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    phase_at_crossover_deg: Annotated[float, Field(allow_inf_nan=False)]
    extra_crossovers_hz: tuple[float, ...] = ()


def unwrap_phase_deg(
    real: tuple[float, ...],
    imag: tuple[float, ...],
) -> tuple[float, ...]:
    """
    Convert (real, imag) → continuous unwrapped phase в градусах.

    atan2 reports phase in `[-180°, 180°]`. При мониторинге phase'а
    через single/multi-pole rolloff'ы (например, T(jω) идёт от 0°
    через -180° к -270°), raw atan2 «прыгает» с -180° к +180°.
    Unwrap'ит эти прыжки в continuous monotonic sequence.

    Args:
        real: параллельный tuple реальных частей T(jω) на свеппе.
        imag: параллельный tuple мнимых частей T(jω) на свеппе.

    Returns:
        Tuple unwrapped phases, длиной как `real`.

    """
    raw = [math.degrees(math.atan2(i, r)) for r, i in zip(real, imag, strict=True)]
    if not raw:
        return ()
    out = [raw[0]]
    for k in range(1, len(raw)):
        diff = raw[k] - raw[k - 1]
        while diff > _PHASE_WRAP_THRESHOLD_DEG:
            diff -= _PHASE_WRAP_CYCLE_DEG
        while diff < -_PHASE_WRAP_THRESHOLD_DEG:
            diff += _PHASE_WRAP_CYCLE_DEG
        out.append(out[-1] + diff)
    return tuple(out)


def find_unity_crossover(loop_gain: LoopGain) -> CrossoverResult:
    """
    Find primary unity-gain crossover + interpolated phase + extras.

    See module docstring для алгоритма.

    Raises:
        LoopGainAlwaysAboveUnityError: |T| > 1 во всех точках свеппа.
        NoUnityGainCrossoverError: нет downward crossing'а через 0 dB
            (включая case'ы «всё ≤ 1» и «только upward crossings»).

    """
    n = len(loop_gain.frequency)
    mag_db = tuple(
        _mag_db(r, i) for r, i in zip(loop_gain.real, loop_gain.imag, strict=True)
    )

    if all(db > 0.0 for db in mag_db):
        msg = (
            f'loop gain |T| > 1 across entire sweep '
            f'[{loop_gain.frequency[0]:g}, {loop_gain.frequency[-1]:g}] Hz — '
            f'crossover lies above f_high; extend sweep upper bound'
        )
        raise LoopGainAlwaysAboveUnityError(msg)

    downward: list[tuple[float, float, int]] = []  # (f_cross, t, k)
    upward: list[tuple[float, float, int]] = []
    for k in range(n - 1):
        db_lo, db_hi = mag_db[k], mag_db[k + 1]
        if db_lo >= 0.0 > db_hi:
            f_cross, t = _interp_log_freq(
                loop_gain.frequency[k],
                loop_gain.frequency[k + 1],
                db_lo,
                db_hi,
            )
            downward.append((f_cross, t, k))
        elif db_lo <= 0.0 < db_hi:
            f_cross, t = _interp_log_freq(
                loop_gain.frequency[k],
                loop_gain.frequency[k + 1],
                db_lo,
                db_hi,
            )
            upward.append((f_cross, t, k))

    if not downward:
        msg = (
            f'no downward unity-gain crossover in sweep '
            f'[{loop_gain.frequency[0]:g}, {loop_gain.frequency[-1]:g}] Hz — '
            f'loop gain stays at or below unity, or only upward crossings'
        )
        raise NoUnityGainCrossoverError(msg)

    downward.sort(key=lambda x: x[0])
    primary_f, primary_t, primary_k = downward[0]
    phase_deg = unwrap_phase_deg(loop_gain.real, loop_gain.imag)
    primary_phase = phase_deg[primary_k] + primary_t * (
        phase_deg[primary_k + 1] - phase_deg[primary_k]
    )

    extras = tuple(
        sorted(
            [f for f, _, _ in downward[1:]] + [f for f, _, _ in upward],
        )
    )

    return CrossoverResult(
        crossover_hz=primary_f,
        phase_at_crossover_deg=primary_phase,
        extra_crossovers_hz=extras,
    )


def _mag_db(real: float, imag: float) -> float:
    """20·log10(|T|), -inf если |T|=0."""
    mag = math.hypot(real, imag)
    if mag == 0.0:
        return -math.inf
    return 20.0 * math.log10(mag)


def _interp_log_freq(
    f_lo: float,
    f_hi: float,
    db_lo: float,
    db_hi: float,
) -> tuple[float, float]:
    """
    Linear interp в log10(f) / dB: где db=0.

    Returns:
        (f_at_zero_db, t) where t ∈ [0, 1] — fraction между f_lo и f_hi.

    """
    if db_lo == db_hi:
        return f_lo, 0.0  # degenerate; not expected due to sign check upstream
    t = db_lo / (db_lo - db_hi)
    log_f = math.log10(f_lo) + t * (math.log10(f_hi) - math.log10(f_lo))
    return 10.0**log_f, t


__all__ = [
    'CrossoverResult',
    'find_unity_crossover',
    'unwrap_phase_deg',
]
