"""
Integration: mag_verify_field с реальными PyOM + GetDP adapters (T113).

Phase 2 acceptance criterion из spec:
> OPT 6П14П analytical L (PyOpenMagnetics) совпадает с FEM-solver L
> в пределах ±10%.

⚠️ Это criteria НЕ выполняется на pilot fixture (linear μ_r=8000 vs
PyOM operating-point μ_eff, 242% diff — задокументировано в T113 spec
+ ADR 2026-05-20). Use case корректно flag'ует discrepancy
(discrepancy_flagged=True), что для LLM-агента — adequate сигнал
"need revisit"; numeric agreement требует nonlinear B-H curve
(BACKLOG T128).

Этот integration test проверяет:
1. analytical-only path работает через реальный PyOM adapter;
2. verify_with_fem path выполняется end-to-end (если gmsh+getdp в PATH);
3. discrepancy_flagged корректно True на known-gap fixture (pilot
   regression — мы должны увидеть exactly те же ~242% diff).
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
def field_solver(pyom):  # noqa: ANN001, ANN201
    return GetDpFemSolver(pyom)


def _opt_6p14p_se() -> MagneticComponent:
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


@_NEED_GMSH_AND_GETDP
@pytest.mark.asyncio
async def test_analytical_plus_fem_pilot_regression(
    analytics,  # noqa: ANN001
    field_solver,  # noqa: ANN001
) -> None:
    """End-to-end: analytical+FEM на pilot fixture, известный 242% gap."""
    r = await mag_verify_field(
        component=_opt_6p14p_se(),
        analytics=analytics,
        field_solver=field_solver,
        verify_with_fem=True,
    )
    assert r.analytical_inductance_h == pytest.approx(
        PILOT_ANALYTICAL_LP_H, rel=1e-3,
    )
    assert r.fem_inductance_h == pytest.approx(PILOT_FEM_LP_H, rel=0.05)
    # Known physics gap — use case correctly flags it (T128 follow-up
    # с nonlinear B-H закроет numeric mismatch).
    assert r.discrepancy_flagged is True
    assert r.relative_difference == pytest.approx(PILOT_REL_DIFF, rel=0.1)
