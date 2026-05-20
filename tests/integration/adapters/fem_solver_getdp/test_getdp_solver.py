"""
Integration: GetDpFemSolver через реальный gmsh+getdp subprocess (T113 Phase 2C).

Skip если gmsh или getdp не установлены в PATH (на dev-host Vladimir'а
они доступны только внутри pilot.Dockerfile / efactory:linux). Внутри
container'а — должны быть установлены apt-пакетами `gmsh` + `getdp`
(Phase 2D Dockerfile update).

Acceptance: Lp на OPT 6П14П SE fixture matches pilot Stage B+C baseline
23.7816 H (с 5% толерантностью на mesh-converge variation).
"""

from __future__ import annotations

import shutil

import pytest

from adapters.outbound.fem_solver_getdp import GetDpFemSolver
from adapters.outbound.magnetic_analytics_pyopenmagnetics import (
    load_pyopenmagnetics,
)
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)

# Pilot Stage B+C baseline: getdp Lp = 23.7816 H на OPT 6П14П SE
# (Nanoperm μ_r=8000 linear, 12244 quadratic triangles, mesh-converged).
PILOT_GETDP_LP_H = 23.7816
# Tolerance ±5% — учитывает variation в mesh element count и rounding
# в PyOM core dims между sessions.
PILOT_REL_TOLERANCE = 0.05

_NEED_GMSH_AND_GETDP = pytest.mark.skipif(
    shutil.which('gmsh') is None or shutil.which('getdp') is None,
    reason='gmsh+getdp binaries не в PATH — integration test '
           'требует apt install (см. Phase 2D Dockerfile)',
)


@pytest.fixture(scope='module')
def pyom():  # noqa: ANN201
    return load_pyopenmagnetics()


def _opt_6p14p_se() -> MagneticComponent:
    """Pilot fixture spec — той же что Phase 2B PyOM analytical test."""
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


@_NEED_GMSH_AND_GETDP
@pytest.mark.asyncio
async def test_getdp_adapter_matches_pilot_baseline(pyom) -> None:  # noqa: ANN001
    """End-to-end pipeline Lp совпадает с pilot 23.7816 H ±5%."""
    solver = GetDpFemSolver(pyom)
    lp = await solver.solve_inductance(_opt_6p14p_se())
    assert lp == pytest.approx(PILOT_GETDP_LP_H, rel=PILOT_REL_TOLERANCE)
