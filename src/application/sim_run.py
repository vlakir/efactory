"""sim_run — запуск симуляции на готовом netlist'е (T008 Phase 4 + T016 Phase C)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.sim_results import AnalysisType, SimResult

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, SimulationResult
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


_ANALYSIS_TYPE_MAP: dict[str, AnalysisType] = {
    'op': AnalysisType.OP,
    'tran': AnalysisType.TRAN,
    'ac': AnalysisType.AC,
    'four': AnalysisType.FOUR,
}


async def sim_run(
    *,
    netlist: Path,
    analysis: AnalysisSpec,
    simulator: Simulator,
    timeout_seconds: float = 60.0,
    sim_results_writer: SimResultsRepository | None = None,
    project_root: Path | None = None,
    tool: str = 'ngspice',
) -> SimulationResult:
    """
    Запустить указанный analysis на готовом netlist'е.

    Тонкая обёртка над `Simulator.run`. Бросает `SimulatorUnavailableError`
    / `SimulationFailedError` неизменно.

    T016: если переданы оба `sim_results_writer` и `project_root` —
    после успешной симуляции `SimResult` snapshot записывается через
    writer (см. `domain.sim_results`, `ports.outbound.sim_results`).
    Если задан только один — `ValueError` (неконсистентный вызов).
    """
    if (sim_results_writer is None) != (project_root is None):
        msg = (
            'sim_results_writer и project_root должны быть переданы парой '
            '(оба или ни одного).'
        )
        raise ValueError(msg)

    started_at = datetime.now(UTC)
    started_perf = time.perf_counter()
    result = await simulator.run(
        netlist,
        analysis,
        timeout_seconds=timeout_seconds,
    )
    duration_seconds = time.perf_counter() - started_perf

    if sim_results_writer is not None and project_root is not None:
        snapshot = _build_snapshot(
            sim_result=result,
            analysis=analysis,
            netlist=netlist,
            project_root=project_root,
            started_at=started_at,
            duration_seconds=duration_seconds,
            tool=tool,
        )
        await sim_results_writer.write(result=snapshot, project_root=project_root)

    return result


def _build_snapshot(
    *,
    sim_result: SimulationResult,
    analysis: AnalysisSpec,
    netlist: Path,
    project_root: Path,
    started_at: datetime,
    duration_seconds: float,
    tool: str,
) -> SimResult:
    try:
        source_file = str(netlist.resolve().relative_to(project_root.resolve()))
    except ValueError:
        source_file = netlist.name

    timestamp = started_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    return SimResult(
        timestamp=timestamp,
        analysis_type=_ANALYSIS_TYPE_MAP.get(analysis.type, AnalysisType.OTHER),
        source_file=source_file,
        tool=tool,
        duration_seconds=max(0.0, duration_seconds),
        summary=_render_summary(analysis=analysis, sim_result=sim_result),
    )


def _render_summary(*, analysis: AnalysisSpec, sim_result: SimulationResult) -> str:
    if analysis.type == 'op' and sim_result.operating_points is not None:
        return f'OP point: {len(sim_result.operating_points)} signals'
    if analysis.type == 'tran' and sim_result.time_series is not None:
        ts = sim_result.time_series
        return (
            f'tran {analysis.t_start}..{analysis.t_stop} s, '
            f'{len(ts.traces)} traces, {len(ts.time)} samples'
        )
    if analysis.type == 'ac' and sim_result.ac_sweep is not None:
        return (
            f'AC sweep {analysis.f_start}..{analysis.f_stop} Hz '
            f'({analysis.sweep}), {len(sim_result.ac_sweep.traces_real)} traces'
        )
    if analysis.type == 'four' and sim_result.fourier_result is not None:
        fr = sim_result.fourier_result
        return (
            f'fourier @ {analysis.fundamental_hz} Hz: '
            f'THD={fr.thd_percent:.3f}%, {len(fr.harmonics)} harmonics'
        )
    return f'{analysis.type} completed'


__all__ = ['sim_run']
