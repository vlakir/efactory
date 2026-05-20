"""
Unit: mag_verify_field use case (T113 Phase 2D, fake adapters).

Тестирует логику use case'а в изоляции от backend'ов — реальная
PyOM + GetDP integration в `tests/integration/application/`.
"""

from __future__ import annotations

import pytest

from application.mag_verify_field import mag_verify_field
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)
from ports.outbound.magnetic_field_solver import FemSolveOutcome


class _FakeAnalytics:
    def __init__(self, lp: float) -> None:
        self._lp = lp

    async def calculate_inductance(self, component: object) -> float:  # noqa: ARG002
        return self._lp


class _FakeFieldSolver:
    def __init__(
        self,
        lp: float,
        method: str = 'linear',
        peak_b: float | None = None,
    ) -> None:
        self._lp = lp
        self._method = method
        self._peak_b = peak_b

    async def solve(self, component: object) -> FemSolveOutcome:  # noqa: ARG002
        return FemSolveOutcome(
            inductance_h=self._lp,
            method=self._method,  # type: ignore[arg-type]
            peak_flux_density_t=self._peak_b,
        )


def _component() -> MagneticComponent:
    return MagneticComponent(
        name='test-component',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
        ),
    )


@pytest.mark.asyncio
async def test_analytical_only_path_returns_analytical_lp() -> None:
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
    )
    assert r.component_name == 'test-component'
    assert r.analytical_inductance_h == pytest.approx(6.96)
    assert r.fem_inductance_h is None
    assert r.relative_difference is None
    assert r.discrepancy_flagged is False


@pytest.mark.asyncio
async def test_fem_within_threshold_not_flagged() -> None:
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
        field_solver=_FakeFieldSolver(lp=7.2),  # 3.4% diff < 10% threshold
        verify_with_fem=True,
    )
    assert r.fem_inductance_h == pytest.approx(7.2)
    assert r.relative_difference == pytest.approx(0.03448, rel=1e-3)
    assert r.discrepancy_flagged is False


@pytest.mark.asyncio
async def test_fem_above_threshold_flagged() -> None:
    """Воспроизводит pilot result: analytical=6.96, FEM linear μ_r=23.78."""
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
        field_solver=_FakeFieldSolver(lp=23.78),
        verify_with_fem=True,
    )
    assert r.relative_difference == pytest.approx(2.4167, rel=1e-3)
    assert r.discrepancy_flagged is True


@pytest.mark.asyncio
async def test_custom_threshold_respected() -> None:
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
        field_solver=_FakeFieldSolver(lp=7.2),
        verify_with_fem=True,
        discrepancy_threshold=0.01,  # 1%, tight
    )
    # 3.4% > 1% → flagged
    assert r.discrepancy_flagged is True


@pytest.mark.asyncio
async def test_verify_with_fem_requires_field_solver() -> None:
    with pytest.raises(ValueError, match='требует field_solver'):
        await mag_verify_field(
            component=_component(),
            analytics=_FakeAnalytics(lp=6.96),
            field_solver=None,
            verify_with_fem=True,
        )


@pytest.mark.asyncio
async def test_zero_analytical_inductance_relative_diff_zero() -> None:
    """Edge case: analytical=0 → relative_difference=0 (no division by zero)."""
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=0.0),
        field_solver=_FakeFieldSolver(lp=5.0),
        verify_with_fem=True,
    )
    assert r.relative_difference == pytest.approx(0.0)
    assert r.discrepancy_flagged is False


@pytest.mark.asyncio
async def test_analytical_only_path_omits_fem_diagnostics() -> None:
    """Без FEM verify — fem_method и peak_flux_density_t остаются None."""
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
    )
    assert r.fem_method is None
    assert r.peak_flux_density_t is None


@pytest.mark.asyncio
async def test_fem_outcome_method_and_peak_propagate() -> None:
    """T129: fem_method + peak_flux_density_t из outcome пробрасываются в VR."""
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
        field_solver=_FakeFieldSolver(
            lp=7.05,
            method='nonlinear-frohlich',
            peak_b=1.18,
        ),
        verify_with_fem=True,
    )
    assert r.fem_method == 'nonlinear-frohlich'
    assert r.peak_flux_density_t == pytest.approx(1.18)


@pytest.mark.asyncio
async def test_fem_linear_method_default_propagates() -> None:
    """Linear FEM path: method='linear', peak=None — back-compat."""
    r = await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(lp=6.96),
        field_solver=_FakeFieldSolver(lp=23.78),
        verify_with_fem=True,
    )
    assert r.fem_method == 'linear'
    assert r.peak_flux_density_t is None
