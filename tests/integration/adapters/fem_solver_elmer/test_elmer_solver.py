"""
Integration: ElmerFemSolver через реальный gmsh+ElmerGrid+ElmerSolver
subprocess pipeline (T133 Phase 1 linear + Phase 3 empirical baseline).

Skip если elmer toolchain не в PATH (на dev-host Vladimir'а Elmer
доступен только внутри `efactory:linux` после Phase 1 Dockerfile +
elmerfem-csc PPA). Внутри container'а — установлен через PPA
`elmer-csc-ubuntu/elmer-csc-ppa`.

**T133 Phase 3 acceptance probe finding (2026-05-21):** Elmer 2D linear
single-coil + Infinity BC на OPT 6П14П SE даёт Lp = 19.65 H — это
**+182% к PyOM ZHANG analytical (6.96 H)**. Inherent 2D-planar gap,
не bug solver'а или topology'и (auto-memory
`feedback_fem_2d_inherent_gap_to_zhang`). Test использует 19.65 H как
**regression baseline (±5%)** для catch numerical drift между Elmer
versions / mesh density changes — но НЕ как acceptance к ZHANG.
Acceptance closure к ZHANG требует 3D mesh (Phase 3+).
"""

from __future__ import annotations

import shutil

import pytest

from adapters.outbound.fem_solver_elmer import ElmerFemSolver
from adapters.outbound.fem_solver_elmer.adapter import (
    EMPIRICAL_LP_OPT_6P14P_SE_LINEAR_H,
)
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

# Regression tolerance — Elmer numerical reproducibility между runs.
# Не acceptance к ZHANG (см. auto-memory feedback_fem_2d_inherent_gap_to_zhang).
LP_REGRESSION_TOLERANCE_REL = 0.05

_NEED_ELMER_TOOLCHAIN = pytest.mark.skipif(
    shutil.which('gmsh') is None
    or shutil.which('ElmerGrid') is None
    or shutil.which('ElmerSolver') is None,
    reason='gmsh / ElmerGrid / ElmerSolver не в PATH — integration test '
    'требует elmerfem-csc PPA (см. Dockerfile T133 Phase 1)',
)


@pytest.fixture(scope='module')
def pyom():  # noqa: ANN201
    return load_pyopenmagnetics()


def _opt_6p14p_se() -> MagneticComponent:
    """Pilot fixture (тот же что T113 / T129 / GetDP integration)."""
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


@_NEED_ELMER_TOOLCHAIN
@pytest.mark.asyncio
async def test_elmer_linear_pipeline_regression_to_empirical_baseline(
    pyom,  # noqa: ANN001
) -> None:
    """Elmer 2D linear single-coil + Infinity BC регрессия к empirical baseline.

    На OPT 6П14П SE с μ_r=8000 Nanoperm linear → Lp ≈ 19.65 H (T133
    Phase 3 probe 2026-05-21). Catches numerical drift в Elmer/gmsh
    upgrades, mesh density change. НЕ acceptance к ZHANG (inherent
    2D-planar +182% gap; closure — 3D mesh path).
    """
    solver = ElmerFemSolver(pyom)
    outcome = await solver.solve(_opt_6p14p_se())
    assert outcome.method == 'linear'
    assert outcome.peak_flux_density_t is None  # Phase 1 не вычисляет diagnostic
    assert outcome.inductance_h == pytest.approx(
        EMPIRICAL_LP_OPT_6P14P_SE_LINEAR_H,
        rel=LP_REGRESSION_TOLERANCE_REL,
    )
