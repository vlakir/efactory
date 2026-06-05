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

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.magnetic import (
    DEFAULT_DISCREPANCY_THRESHOLD,
    MagneticVerificationResult,
)
from domain.magnetic_summary import (
    MagneticsSummary,
    MagneticsSummaryCoreSection,
    MagneticsSummaryOperatingSection,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.magnetic import MagneticComponent
    from ports.outbound.magnetic_analytics import MagneticAnalytics
    from ports.outbound.magnetic_field_solver import MagneticFieldSolver
    from ports.outbound.magnetic_results import MagneticResultsRepository


async def mag_verify_field(
    *,
    component: MagneticComponent,
    analytics: MagneticAnalytics,
    field_solver: MagneticFieldSolver | None = None,
    verify_with_fem: bool = False,
    discrepancy_threshold: float = DEFAULT_DISCREPANCY_THRESHOLD,
    magnetics_results_writer: MagneticResultsRepository | None = None,
    project_root: Path | None = None,
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
        magnetics_results_writer: T189 outbound port для persist
            `MagneticsSummary` JSON sidecar. Передаётся парно с
            `project_root`; missing one без другого → `ValueError`.
        project_root: T189 каталог проекта (writes в
            `<project>/out/fem/<ts>/summary.json`).

    Returns:
        `MagneticVerificationResult` — всегда содержит analytical Lp;
        FEM-поля заполнены только когда verify_with_fem=True.

    Raises:
        ValueError: если verify_with_fem=True, но field_solver=None.
        Backend errors (analytical/FEM) propagate as-is из port'а.

    """
    if (magnetics_results_writer is None) != (project_root is None):
        msg = (
            'magnetics_results_writer и project_root должны быть переданы '
            'парой (оба или ни одного).'
        )
        raise ValueError(msg)

    analytical_lp = await analytics.calculate_inductance(component)
    timestamp = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

    if not verify_with_fem:
        result = MagneticVerificationResult(
            component_name=component.name,
            analytical_inductance_h=analytical_lp,
            discrepancy_threshold=discrepancy_threshold,
        )
        await _persist_summary_if_requested(
            result=result,
            component=component,
            timestamp=timestamp,
            writer=magnetics_results_writer,
            project_root=project_root,
        )
        return result

    if field_solver is None:
        msg = 'verify_with_fem=True требует field_solver, но передан None'
        raise ValueError(msg)

    outcome = await field_solver.solve(component)
    fem_lp = outcome.inductance_h
    rel_diff = abs(fem_lp - analytical_lp) / analytical_lp if analytical_lp > 0 else 0.0
    result = MagneticVerificationResult(
        component_name=component.name,
        analytical_inductance_h=analytical_lp,
        fem_inductance_h=fem_lp,
        relative_difference=rel_diff,
        discrepancy_flagged=rel_diff > discrepancy_threshold,
        discrepancy_threshold=discrepancy_threshold,
        fem_method=outcome.method,
        peak_flux_density_t=outcome.peak_flux_density_t,
    )
    await _persist_summary_if_requested(
        result=result,
        component=component,
        timestamp=timestamp,
        writer=magnetics_results_writer,
        project_root=project_root,
    )
    return result


async def _persist_summary_if_requested(
    *,
    result: MagneticVerificationResult,
    component: MagneticComponent,
    timestamp: str,
    writer: MagneticResultsRepository | None,
    project_root: Path | None,
) -> None:
    """T189: записать `MagneticsSummary` через injected writer."""
    if writer is None or project_root is None:
        return
    summary = MagneticsSummary(
        timestamp=timestamp,
        component_name=result.component_name,
        analytical_inductance_h=result.analytical_inductance_h,
        fem_inductance_h=result.fem_inductance_h,
        relative_difference=result.relative_difference,
        fem_method=result.fem_method,
        peak_flux_density_t=result.peak_flux_density_t,
        core=MagneticsSummaryCoreSection(
            shape_name=component.core.shape_name,
            material_name=component.core.material_name,
            gap_length_m=component.core.gap_length_m,
            gap_type=component.core.gap_type.value,
        ),
        operating_point=MagneticsSummaryOperatingSection(
            frequency_hz=component.operating_point.frequency_hz,
            primary_peak_voltage_v=component.operating_point.primary_peak_voltage_v,
            primary_dc_bias_a=component.operating_point.primary_dc_bias_a,
        ),
    )
    await writer.write(summary=summary, project_root=project_root)


__all__ = ['mag_verify_field']
