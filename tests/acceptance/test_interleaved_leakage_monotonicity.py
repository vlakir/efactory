"""
T132 acceptance: interleaved OPT leakage monotonicity + absolute range.

Spec `specs/T132-interleaved-leakage/spec.md` §Q7/Q8 — physics-based gate:

- **Monotonicity:** `Lσ(P-S) > Lσ(P-S-P) > Lσ(P-S-P-S-P)` — interleaving
  reduction theorem (Erickson §15 / Hurley §4.6, 1/N² factor).
- **Absolute bound:** `Lσ(5-section) ∈ [0.1 mH, 10 mH]` для OPT_SE_5K_8-
  class fixture (3500 primary turns, E 42/15 core; Patrick Turner
  empirical range для 5kΩ:8Ω audio OPT).

Backend: pure-Python analytical (Erickson sandwich formula); PyOM
catalog для geometry/wire dim resolution. PyOM `calculate_leakage_
inductance` исключён из pipeline (mesh broken, T135 BACKLOG).
"""

from __future__ import annotations

import pytest

from adapters.outbound.leakage_inductance_analytical import AnalyticalLeakage
from adapters.outbound.magnetic_analytics_pyopenmagnetics import (
    PyOpenMagneticsAnalytics,
    load_pyopenmagnetics,
)
from application.analyze_interleaved_leakage import analyze_interleaved_leakage
from domain.magnetic import (
    Core,
    GapType,
    InterleavingPattern,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
    WindingSection,
)

PILOT_PRIMARY_TURNS = 3500
PILOT_SECONDARY_TURNS = 140  # 25:1 turn ratio = 5kΩ:8Ω impedance

# Spec §Q7 absolute bound для 5-section pilot
LEAKAGE_LOWER_BOUND_H = 0.1e-3  # 0.1 mH
LEAKAGE_UPPER_BOUND_H = 10e-3   # 10 mH


@pytest.fixture(scope='module')
def adapter():  # noqa: ANN201
    pyom = load_pyopenmagnetics()
    inductance = PyOpenMagneticsAnalytics(pyom)
    return AnalyticalLeakage(pyom, inductance)


def _opt_se_5k_8(layout: InterleavingPattern) -> MagneticComponent:
    """Hammond 1627A-class fixture с заданным sandwich layout."""
    return MagneticComponent(
        name=f'OPT_SE_5K_8 layout={layout.pattern}',
        core=Core(
            shape_name='E 42/21/15',
            material_name='3C95',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=PILOT_PRIMARY_TURNS,
                isolation_side=IsolationSide.PRIMARY,
                wire_name='Round 0.224 - Grade 1',
            ),
            Winding(
                name='secondary',
                number_turns=PILOT_SECONDARY_TURNS,
                isolation_side=IsolationSide.SECONDARY,
                wire_name='Round 0.5 - Grade 1',
            ),
        ),
        operating_point=OperatingPoint(
            name='1 kHz mid-band',
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
            primary_dc_bias_a=0.05,
            primary_ac_peak_a=0.01,
        ),
        section_layout=layout,
    )


def _p_s() -> InterleavingPattern:
    return InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
        ),
    )


def _p_s_p() -> InterleavingPattern:
    return InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
        ),
    )


def _p_s_p_s_p() -> InterleavingPattern:
    return InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
        ),
    )


@pytest.mark.asyncio
async def test_leakage_monotonic_decrease_with_interleaving(adapter) -> None:  # noqa: ANN001
    """Spec Q7 main gate: Lσ(P-S) > Lσ(P-S-P) > Lσ(P-S-P-S-P)."""
    r_2 = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(_p_s()), analyzer=adapter,
    )
    r_3 = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(_p_s_p()), analyzer=adapter,
    )
    r_5 = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(_p_s_p_s_p()), analyzer=adapter,
    )

    σ_2 = r_2.leakage_to['secondary']
    σ_3 = r_3.leakage_to['secondary']
    σ_5 = r_5.leakage_to['secondary']

    assert σ_2 > σ_3 > σ_5, (
        f'expected monotonic decrease (2-sec > 3-sec > 5-sec); '
        f'got 2-sec={σ_2*1e3:.3f} mH, 3-sec={σ_3*1e3:.3f} mH, '
        f'5-sec={σ_5*1e3:.3f} mH'
    )


@pytest.mark.asyncio
async def test_leakage_5_section_within_absolute_range(adapter) -> None:  # noqa: ANN001
    """Spec Q7 absolute bound: Lσ(5-section) ∈ [0.1 mH, 10 mH]."""
    result = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(_p_s_p_s_p()), analyzer=adapter,
    )
    σ = result.leakage_to['secondary']
    assert LEAKAGE_LOWER_BOUND_H < σ < LEAKAGE_UPPER_BOUND_H, (
        f'Lσ(5-section) = {σ*1e3:.3f} mH вне ожидаемого range '
        f'[{LEAKAGE_LOWER_BOUND_H*1e3}, {LEAKAGE_UPPER_BOUND_H*1e3}] mH'
    )


@pytest.mark.asyncio
async def test_leakage_5_section_strong_coupling(adapter) -> None:  # noqa: ANN001
    """Hi-end OPT: 5-section должен дать k > 0.99 (Lσ ≪ L_self)."""
    result = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(_p_s_p_s_p()), analyzer=adapter,
    )
    assert result.coupling_factor > 0.99


@pytest.mark.asyncio
async def test_leakage_n_squared_ratio_for_zero_insulation(adapter) -> None:  # noqa: ANN001
    """Sanity: c a=0, σ_5/σ_2 ≈ 1/16 (N² reduction только; a-terms скрыты)."""
    # Create patterns with zero insulation
    p_s_no_ins = InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
        ),
        inter_section_thickness_m=0.0,
    )
    p_s_p_s_p_no_ins = InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
        ),
        inter_section_thickness_m=0.0,
    )
    r_2 = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(p_s_no_ins), analyzer=adapter,
    )
    r_5 = await analyze_interleaved_leakage(
        component=_opt_se_5k_8(p_s_p_s_p_no_ins), analyzer=adapter,
    )
    ratio = r_5.leakage_to['secondary'] / r_2.leakage_to['secondary']
    # 1/16 exact for zero-insulation case
    assert ratio == pytest.approx(1.0 / 16.0, rel=1e-6)
