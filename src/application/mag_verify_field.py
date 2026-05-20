"""
mag_verify_field — analytical inductance + опциональный FEM cross-check (T113).

Дёргает `MagneticAnalytics` для быстрого Lp; если `verify_with_fem=True`
— дополнительно `MagneticFieldSolver` для FEM Lp, считает relative
difference и flag'ует расхождение > threshold (default 10%, per T113
spec Phase 2 acceptance).

Известный physics gap на pilot OPT 6П14П SE (см. T113 Phase 1 results):
analytical PyOM ZHANG = 6.96 H vs FEM linear μ_r=8000 = 23.78 H (242%
diff). Это известный gap (operating-point μ_eff vs constant μ_r),
fixable nonlinear B-H curve — BACKLOG T128. Use case в Phase 2D
просто корректно репортит discrepancy_flagged=True; этого достаточно
для интеграции в LLM-orchestration pipeline (агент видит "FEM
расходится — нужна revisit").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.magnetic import (
    DEFAULT_DISCREPANCY_THRESHOLD,
    MagneticVerificationResult,
)

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent
    from ports.outbound.magnetic_analytics import MagneticAnalytics
    from ports.outbound.magnetic_field_solver import MagneticFieldSolver


async def mag_verify_field(
    *,
    component: MagneticComponent,
    analytics: MagneticAnalytics,
    field_solver: MagneticFieldSolver | None = None,
    verify_with_fem: bool = False,
    discrepancy_threshold: float = DEFAULT_DISCREPANCY_THRESHOLD,
) -> MagneticVerificationResult:
    """
    Вычислить magnetizing inductance компонента (analytical + FEM optional).

    Args:
        component: magnetic component spec (core + windings + operating).
        analytics: `MagneticAnalytics` port (PyOpenMagnetics adapter).
        field_solver: `MagneticFieldSolver` port (GetDP adapter), required
            если `verify_with_fem=True`, ignored иначе.
        verify_with_fem: True → запустить FEM cross-check; False → только
            analytical (default — fast path).
        discrepancy_threshold: relative threshold для discrepancy_flagged;
            default 10% (см. `DEFAULT_DISCREPANCY_THRESHOLD`).

    Returns:
        `MagneticVerificationResult` — всегда содержит analytical Lp;
        FEM-поля заполнены только когда verify_with_fem=True.

    Raises:
        ValueError: если verify_with_fem=True, но field_solver=None.
        Backend errors (analytical/FEM) propagate as-is из port'а.

    """
    analytical_lp = await analytics.calculate_inductance(component)

    if not verify_with_fem:
        return MagneticVerificationResult(
            component_name=component.name,
            analytical_inductance_h=analytical_lp,
            discrepancy_threshold=discrepancy_threshold,
        )

    if field_solver is None:
        msg = 'verify_with_fem=True требует field_solver, но передан None'
        raise ValueError(msg)

    outcome = await field_solver.solve(component)
    fem_lp = outcome.inductance_h
    rel_diff = abs(fem_lp - analytical_lp) / analytical_lp if analytical_lp > 0 else 0.0
    return MagneticVerificationResult(
        component_name=component.name,
        analytical_inductance_h=analytical_lp,
        fem_inductance_h=fem_lp,
        relative_difference=rel_diff,
        discrepancy_flagged=rel_diff > discrepancy_threshold,
        discrepancy_threshold=discrepancy_threshold,
        fem_method=outcome.method,
        peak_flux_density_t=outcome.peak_flux_density_t,
    )


__all__ = ['mag_verify_field']
