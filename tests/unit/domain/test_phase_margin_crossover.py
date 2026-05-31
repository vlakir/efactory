"""Crossover detection helpers для phase-margin (T153 Phase B.4)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from domain.phase_margin import (
    LoopGainAlwaysAboveUnityError,
    NoUnityGainCrossoverError,
)
from domain.phase_margin_crossover import (
    CrossoverResult,
    find_unity_crossover,
    unwrap_phase_deg,
)
from domain.phase_margin_injection import LoopGain


def _make_lg(
    frequency: tuple[float, ...],
    complex_values: tuple[complex, ...],
) -> LoopGain:
    return LoopGain(
        frequency=frequency,
        real=tuple(z.real for z in complex_values),
        imag=tuple(z.imag for z in complex_values),
    )


# ============================== unwrap_phase_deg ==============================


def test_unwrap_no_wrap_returns_raw_atan2() -> None:
    # All in [-π, π]: no unwrap needed.
    real = (1.0, 1.0, 0.5)
    imag = (0.0, 1.0, 0.5)
    out = unwrap_phase_deg(real, imag)
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(45.0)
    assert out[2] == pytest.approx(45.0)


def test_unwrap_descending_through_minus_180_boundary() -> None:
    # atan2: -90° at imag=-1+0j*real, then wraps to +90° when we go below -180°.
    # Synthetic: phases progress -45° → -135° → -225° (which raw atan2 reports as +135°)
    # → -315° (raw +45°).
    real = (1.0, -1.0, -1.0, 1.0)
    imag = (-1.0, -1.0, 1.0, 1.0)
    # raw atan2 in deg: -45, -135, +135, +45
    out = unwrap_phase_deg(real, imag)
    assert out[0] == pytest.approx(-45.0)
    assert out[1] == pytest.approx(-135.0)
    # going from -135 to +135 в raw — diff = +270 > 180 → subtract 360 → diff = -90
    assert out[2] == pytest.approx(-225.0)
    # going from raw +135 to raw +45 — diff = -90 → no wrap
    assert out[3] == pytest.approx(-315.0)


def test_unwrap_zero_complex_atan2_returns_zero_at_origin() -> None:
    out = unwrap_phase_deg((1.0, 0.0), (0.0, 0.0))
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(0.0)


# ============================== find_unity_crossover ============================


def test_crossover_at_exact_sample_point() -> None:
    # |T|: 10, 1, 0.1 at f: 1, 100, 10000. Phase 0°.
    lg = _make_lg(
        frequency=(1.0, 100.0, 10000.0),
        complex_values=(10.0 + 0j, 1.0 + 0j, 0.1 + 0j),
    )
    result = find_unity_crossover(lg)
    assert isinstance(result, CrossoverResult)
    assert result.crossover_hz == pytest.approx(100.0, rel=1e-9)
    assert result.phase_at_crossover_deg == pytest.approx(0.0)
    assert result.extra_crossovers_hz == ()


def test_crossover_between_samples_log_interpolation() -> None:
    # f: 1, 10, 100, 1000. |T|: 10, 5, 0.5, 0.1.
    # dB: 20, ~13.98, ~-6.02, -20.
    # Downward through 0 dB between k=1 (13.98 dB, f=10) and k=2 (-6.02 dB, f=100).
    # t = 13.98/(13.98 - (-6.02)) = 13.98/20 = 0.699.
    # log_f_cross = 1 + 0.699*(2-1) = 1.699 → f ≈ 50.0 Hz.
    lg = _make_lg(
        frequency=(1.0, 10.0, 100.0, 1000.0),
        complex_values=(10.0 + 0j, 5.0 + 0j, 0.5 + 0j, 0.1 + 0j),
    )
    result = find_unity_crossover(lg)
    assert result.crossover_hz == pytest.approx(50.0, rel=0.05)
    assert result.phase_at_crossover_deg == pytest.approx(0.0)


def test_crossover_phase_interpolated_between_samples() -> None:
    # |T|: 2, 0.5, phase: -60°, -120°. Crossover at half-way.
    # T values: 2*(cos -60 + j sin -60), 0.5*(cos -120 + j sin -120)
    z1 = 2.0 * complex(math.cos(math.radians(-60)), math.sin(math.radians(-60)))
    z2 = 0.5 * complex(math.cos(math.radians(-120)), math.sin(math.radians(-120)))
    lg = _make_lg(frequency=(10.0, 100.0), complex_values=(z1, z2))
    result = find_unity_crossover(lg)
    # dB1 = 20·log(2) ≈ 6.02, dB2 = 20·log(0.5) ≈ -6.02.
    # t = 6.02/(6.02+6.02) = 0.5. log_f = 1 + 0.5 = 1.5 → f ≈ 31.62.
    assert result.crossover_hz == pytest.approx(31.62, rel=0.05)
    # phase: -60 + 0.5*(-120 - (-60)) = -90°.
    assert result.phase_at_crossover_deg == pytest.approx(-90.0, abs=0.5)


def test_all_above_unity_raises_loop_gain_always_above() -> None:
    lg = _make_lg(
        frequency=(1.0, 10.0, 100.0),
        complex_values=(10.0 + 0j, 5.0 + 0j, 2.0 + 0j),
    )
    with pytest.raises(LoopGainAlwaysAboveUnityError, match='above f_high'):
        find_unity_crossover(lg)


def test_all_below_unity_raises_no_crossover() -> None:
    lg = _make_lg(
        frequency=(1.0, 10.0, 100.0),
        complex_values=(0.5 + 0j, 0.2 + 0j, 0.1 + 0j),
    )
    with pytest.raises(NoUnityGainCrossoverError, match='crossover'):
        find_unity_crossover(lg)


def test_upward_only_crossing_no_downward_raises() -> None:
    # |T| goes from 0.1 → 0.5 → 2.0 — upward through unity but no downward.
    lg = _make_lg(
        frequency=(1.0, 10.0, 100.0),
        complex_values=(0.1 + 0j, 0.5 + 0j, 2.0 + 0j),
    )
    with pytest.raises(NoUnityGainCrossoverError):
        find_unity_crossover(lg)


def test_multiple_downward_crossings_returns_lowest_and_extras() -> None:
    # |T|: 2 → 0.5 → 2 → 0.5 → primary downward at f=10..100, second at f=1000..10000.
    lg = _make_lg(
        frequency=(1.0, 10.0, 100.0, 1000.0, 10000.0),
        complex_values=(2.0 + 0j, 2.0 + 0j, 0.5 + 0j, 2.0 + 0j, 0.5 + 0j),
    )
    result = find_unity_crossover(lg)
    # primary — first downward (between f=10 (6dB) and f=100 (-6dB)).
    # t = 6/12 = 0.5, log_f = 1 + 0.5 = 1.5 → f ≈ 31.62.
    assert result.crossover_hz == pytest.approx(31.62, rel=0.05)
    # extras — upward (f=100..1000) и downward (f=1000..10000).
    assert len(result.extra_crossovers_hz) == 2
    # upward между (0.5 → 2) → t=0.5 → log_f=2.5 → 316.2
    # downward между (2 → 0.5) → t=0.5 → log_f=3.5 → 3162
    sorted_extras = sorted(result.extra_crossovers_hz)
    assert sorted_extras[0] == pytest.approx(316.2, rel=0.05)
    assert sorted_extras[1] == pytest.approx(3162.0, rel=0.05)


def test_single_pole_loop_gain_realistic_margin() -> None:
    """T(jω) = G0/(1 + jω/ωp), G0=100, ωp=2π·1 rad/s.

    Unity-gain crossing где |T|=1 ⇔ ω/ωp = sqrt(G0² - 1) ≈ G0
    ⇒ ω_gc ≈ G0·ωp = 2π·100 rad/s ⇒ f_gc ≈ 100 Hz.
    Phase в этой точке ≈ -arctan(100) ≈ -89.4°. Margin ≈ 90.6°.
    """
    g0 = 100.0
    fp = 1.0  # pole frequency Hz
    frequencies = (0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)
    cv = []
    for f in frequencies:
        x = f / fp  # ω/ωp normalized
        # T = G0 / (1 + jx)
        denom = complex(1.0, x)
        cv.append(g0 / denom)
    lg = _make_lg(frequency=frequencies, complex_values=tuple(cv))
    result = find_unity_crossover(lg)
    assert result.crossover_hz == pytest.approx(100.0, rel=0.05)
    # Margin = 180° + phase. Phase at f=100 ≈ -arctan(100) ≈ -89.4°.
    margin = 180.0 + result.phase_at_crossover_deg
    assert margin == pytest.approx(90.6, abs=1.0)


def test_two_pole_loop_gain_margin_smaller() -> None:
    """T = G0/(1+jω/ωp)², G0=100, fp=10 Hz. Crossover ≈ √100·10 = 100 Hz.
    Phase = -2·arctan(ω/ωp). At ω/ωp=10 → -2·arctan(10) ≈ -168.6°. Margin ≈ 11.4°.
    """
    g0 = 100.0
    fp = 10.0
    frequencies = tuple(10.0 ** k for k in (-1, 0, 1, 2, 3, 4))
    cv = []
    for f in frequencies:
        x = f / fp
        denom = complex(1.0, x)
        t_val = g0 / (denom * denom)
        cv.append(t_val)
    lg = _make_lg(frequency=frequencies, complex_values=tuple(cv))
    result = find_unity_crossover(lg)
    # |T| = G0 / (1+x²) = 1 ⇒ x² = G0-1 = 99 ⇒ x = √99 ≈ 9.95
    # ⇒ f = fp · x ≈ 99.5 Hz.
    assert result.crossover_hz == pytest.approx(99.5, rel=0.05)
    margin = 180.0 + result.phase_at_crossover_deg
    assert margin == pytest.approx(11.4, abs=2.0)


def test_crossover_result_is_frozen() -> None:
    result = CrossoverResult(
        crossover_hz=100.0,
        phase_at_crossover_deg=-90.0,
        extra_crossovers_hz=(),
    )
    with pytest.raises(ValidationError):
        result.crossover_hz = 200.0  # type: ignore[misc]


def test_crossover_result_validates_positive_freq() -> None:
    with pytest.raises(ValidationError):
        CrossoverResult(
            crossover_hz=-1.0,
            phase_at_crossover_deg=-90.0,
            extra_crossovers_hz=(),
        )


def test_crossover_result_rejects_nan_phase() -> None:
    with pytest.raises(ValidationError):
        CrossoverResult(
            crossover_hz=100.0,
            phase_at_crossover_deg=math.nan,
            extra_crossovers_hz=(),
        )
