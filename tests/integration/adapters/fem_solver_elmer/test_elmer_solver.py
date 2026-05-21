"""
Integration: ElmerFemSolver через реальный gmsh+ElmerGrid+ElmerSolver
subprocess pipeline (T133 Phase 1 linear smoke).

Skip если elmer toolchain не в PATH (на dev-host Vladimir'а Elmer
доступен только внутри `efactory:linux` после Phase 1 Dockerfile +
elmerfem-csc PPA). Внутри container'а — установлен через PPA
`elmer-csc-ubuntu/elmer-csc-ppa`.

Phase 1 smoke: pipeline сходится, возвращает finite Lp. Numerical
сравнение с T113 baseline (23.78 H) НЕ применимо в этой задаче —
single-coil + Infinity BC топология даёт другой baseline (вероятно
ниже, поскольку отсутствует antisymmetric contribution). Точное
числовое значение зафиксируется в Phase 3 acceptance.
"""

from __future__ import annotations

import shutil

import pytest

from adapters.outbound.fem_solver_elmer import ElmerFemSolver
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
async def test_elmer_linear_pipeline_smoke(pyom) -> None:  # noqa: ANN001
    """End-to-end pipeline сходится → finite Lp > 0."""
    solver = ElmerFemSolver(pyom)
    outcome = await solver.solve(_opt_6p14p_se())
    assert outcome.method == 'linear'
    assert outcome.peak_flux_density_t is None  # Phase 1 — не вычисляется
    # Smoke-уровень: positive, finite, в разумных пределах для
    # OPT-class трансформатора (0.1 H ... 1000 H).
    assert outcome.inductance_h > 0.0
    assert outcome.inductance_h < 1000.0
