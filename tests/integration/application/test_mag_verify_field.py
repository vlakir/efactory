"""
Integration: mag_verify_field с реальными PyOM + GetDP adapters (T113 + T129).

Acceptance закрытия T129 Primary:
> На pilot fixture с material_model='nonlinear-frohlich' и DC-bias load
> line FEM Lp совпадает с PyOM analytical ZHANG в пределах ±10%
> (на DC bias = 0.05 A — operating-point μ_eff из spec §3).

Secondary (back-compat T113 Phase 1 pilot baseline):
> Linear mode без DC bias даёт тот же ~23.78 H ±5% что T113.

Покрываемые сценарии:
1. analytical-only path работает через реальный PyOM adapter (fast).
2. linear FEM + verify_with_fem на pilot (без DC bias) → known 242% gap
   к analytical → discrepancy_flagged=True (Secondary back-compat).
3. nonlinear FEM + DC bias на pilot → relative_difference ≤ 0.10
   (Primary T129 acceptance).
"""

from __future__ import annotations

import shutil

import pytest

from adapters.outbound.fem_solver_getdp import GetDpFemSolver
from adapters.outbound.magnetic_analytics_pyopenmagnetics import (
    PyOpenMagneticsAnalytics,
    load_pyopenmagnetics,
)
from application.mag_verify_field import mag_verify_field
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)

_NEED_GMSH_AND_GETDP = pytest.mark.skipif(
    shutil.which('gmsh') is None or shutil.which('getdp') is None,
    reason='gmsh+getdp binaries не в PATH — integration test '
           'требует apt install (см. Phase 2D Dockerfile).',
)

# Pilot baselines (T113 Phase 1):
PILOT_ANALYTICAL_LP_H = 6.956400080747171  # PyOM ZHANG
PILOT_FEM_LP_H = 23.7816                   # GetDP 2D-planar μ_r=8000
PILOT_REL_DIFF = (PILOT_FEM_LP_H - PILOT_ANALYTICAL_LP_H) / PILOT_ANALYTICAL_LP_H


@pytest.fixture(scope='module')
def pyom():  # noqa: ANN201
    return load_pyopenmagnetics()


@pytest.fixture(scope='module')
def analytics(pyom):  # noqa: ANN001, ANN201
    return PyOpenMagneticsAnalytics(pyom)


@pytest.fixture(scope='module')
def field_solver_linear(pyom):  # noqa: ANN001, ANN201
    return GetDpFemSolver(pyom, material_model='linear')


@pytest.fixture(scope='module')
def field_solver_nonlinear(pyom):  # noqa: ANN001, ANN201
    return GetDpFemSolver(pyom, material_model='nonlinear-frohlich')


# DC bias из pilot config (scripts/pilot/build_fixture.py PRIMARY_DC_BIAS_A):
# 50 mA plate current класса A для 6П14П SE → H_dc ≈ 1289 A/m в core
# (deep saturation, см. T129 spec §1).
PILOT_DC_BIAS_A = 0.05


def _opt_6p14p_se(dc_bias_a: float = 0.0) -> MagneticComponent:
    return MagneticComponent(
        name='OPT 6П14П SE',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary',
                number_turns=100,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
            primary_dc_bias_a=dc_bias_a,
        ),
    )


@pytest.mark.asyncio
async def test_analytical_only_on_pilot_fixture(analytics) -> None:  # noqa: ANN001
    """Path без FEM — fast, не нуждается в gmsh/getdp."""
    r = await mag_verify_field(
        component=_opt_6p14p_se(),
        analytics=analytics,
    )
    assert r.analytical_inductance_h == pytest.approx(
        PILOT_ANALYTICAL_LP_H, rel=1e-3,
    )
    assert r.fem_inductance_h is None
    assert r.discrepancy_flagged is False
    assert r.fem_method is None
    assert r.peak_flux_density_t is None


@_NEED_GMSH_AND_GETDP
@pytest.mark.asyncio
async def test_linear_fem_on_pilot_keeps_baseline(
    analytics,  # noqa: ANN001
    field_solver_linear,  # noqa: ANN001
) -> None:
    """Secondary (back-compat): linear path даёт T113 baseline 23.78 H ±5%."""
    r = await mag_verify_field(
        component=_opt_6p14p_se(),
        analytics=analytics,
        field_solver=field_solver_linear,
        verify_with_fem=True,
    )
    assert r.analytical_inductance_h == pytest.approx(
        PILOT_ANALYTICAL_LP_H, rel=1e-3,
    )
    assert r.fem_inductance_h == pytest.approx(PILOT_FEM_LP_H, rel=0.05)
    # Known physics gap — linear μ_r vs operating-point μ_eff (T113 ADR).
    assert r.discrepancy_flagged is True
    assert r.relative_difference == pytest.approx(PILOT_REL_DIFF, rel=0.1)
    assert r.fem_method == 'linear'
    assert r.peak_flux_density_t is None


@_NEED_GMSH_AND_GETDP
@pytest.mark.asyncio
async def test_analytical_plus_fem_pilot_regression(
    analytics,  # noqa: ANN001
    field_solver_nonlinear,  # noqa: ANN001
) -> None:
    """Primary T129 acceptance: nonlinear + DC bias → ±10% к PyOM ZHANG."""
    r = await mag_verify_field(
        component=_opt_6p14p_se(dc_bias_a=PILOT_DC_BIAS_A),
        analytics=analytics,
        field_solver=field_solver_nonlinear,
        verify_with_fem=True,
    )
    assert r.analytical_inductance_h == pytest.approx(
        PILOT_ANALYTICAL_LP_H, rel=1e-3,
    )
    assert r.fem_method == 'nonlinear-frohlich'
    assert r.fem_inductance_h is not None
    assert r.relative_difference is not None
    # Primary acceptance — закрытие T113 Phase 1 pilot 242% gap.
    assert r.relative_difference <= 0.10
    assert r.discrepancy_flagged is False
