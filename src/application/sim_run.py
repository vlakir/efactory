"""sim_run — симуляция на готовом netlist'е (T008 + T016 + T145)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.raw_waveform import RawWaveform, WaveformAnalysisType
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import (
    AcAnalysis,
    OpAnalysis,
    SimulationResult,
    TranAnalysis,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, TimeSeries
    from ports.outbound.raw_waveforms import RawWaveformRepository
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


_DEFAULT_OP_FALLBACK_T_STEP = 1e-6
_DEFAULT_OP_FALLBACK_T_STOP = 100e-3
_DEFAULT_OP_FALLBACK_TAIL_FRACTION = 0.1


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
    raw_waveform_writer: RawWaveformRepository | None = None,
    project_root: Path | None = None,
    tool: str = 'ngspice',
    enable_op_fallback: bool = False,
    op_fallback_t_step: float = _DEFAULT_OP_FALLBACK_T_STEP,
    op_fallback_t_stop: float = _DEFAULT_OP_FALLBACK_T_STOP,
) -> SimulationResult:
    """
    Запустить указанный analysis на готовом netlist'е.

    Тонкая обёртка над `Simulator.run`. Бросает `SimulatorUnavailableError`
    / `SimulationFailedError` неизменно.

    T016: если переданы оба `sim_results_writer` и `project_root` —
    после успешной симуляции `SimResult` snapshot записывается через
    writer (см. `domain.sim_results`, `ports.outbound.sim_results`).
    Если задан только один — `ValueError` (неконсистентный вызов).

    T145: при `enable_op_fallback=True` + `OpAnalysis` —
    `sim_run` **подменяет** `.OP` на `.TRAN ... uic=True` (t_step
    `op_fallback_t_step`, t_stop `op_fallback_t_stop`), запускает
    transient и собирает synthetic `operating_points` из settled tail
    (последние ~10% samples per signal). Используется для tube /
    saturable circuits, где DC-solver `.OP` сходится к trivial idle
    solution.
    Допускается только для `OpAnalysis`; иначе — `ValueError`.

    T190: при `raw_waveform_writer is not None` + `project_root is not None`
    — после успешной симуляции `RawWaveform` sidecar записывается через
    writer для TRAN/AC (DC — через расширение T188). OP результат не
    persist'ится (нет временной/частотной оси).
    """
    if sim_results_writer is not None and project_root is None:
        msg = (
            'sim_results_writer задан без project_root '
            '(нет каталога куда persist'
            "'ить snapshot)."
        )
        raise ValueError(msg)
    if project_root is not None and (
        sim_results_writer is None and raw_waveform_writer is None
    ):
        msg = (
            'project_root задан без sim_results_writer / raw_waveform_writer '
            '(оба writer-а отсутствуют → нечего persist`ить).'
        )
        raise ValueError(msg)

    if enable_op_fallback and not isinstance(analysis, OpAnalysis):
        msg = (
            f'enable_op_fallback применим только к OpAnalysis '
            f'(получен {type(analysis).__name__})'
        )
        raise ValueError(msg)

    started_at = datetime.now(UTC)
    started_perf = time.perf_counter()
    if enable_op_fallback:
        tran_analysis = TranAnalysis(
            t_step=op_fallback_t_step,
            t_stop=op_fallback_t_stop,
            uic=True,
        )
        tran_result = await simulator.run(
            netlist,
            tran_analysis,
            timeout_seconds=timeout_seconds,
        )
        if tran_result.time_series is None:
            msg = (
                'enable_op_fallback: simulator returned result without '
                'time_series — cannot extract synthetic OP'
            )
            raise ValueError(msg)
        op_dict = _extract_op_from_tran_tail(tran_result.time_series)
        result = SimulationResult(operating_points=op_dict)
    else:
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

    if raw_waveform_writer is not None and project_root is not None:
        waveform = _build_waveform(
            sim_result=result,
            analysis=analysis,
            netlist=netlist,
            project_root=project_root,
            started_at=started_at,
        )
        if waveform is not None:
            await raw_waveform_writer.write(
                waveform=waveform,
                project_root=project_root,
            )

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


def _build_waveform(
    *,
    sim_result: SimulationResult,
    analysis: AnalysisSpec,
    netlist: Path,
    project_root: Path,
    started_at: datetime,
) -> RawWaveform | None:
    """
    Convert SimulationResult → RawWaveform для TRAN / AC (T190).

    Возвращает None для OP / FOUR (нет временной/частотной оси —
    persistence не имеет смысла).
    """
    try:
        source_netlist = str(netlist.resolve().relative_to(project_root.resolve()))
    except ValueError:
        source_netlist = netlist.name
    timestamp = started_at.strftime('%Y-%m-%dT%H:%M:%SZ')

    if isinstance(analysis, TranAnalysis) and sim_result.time_series is not None:
        ts = sim_result.time_series
        return RawWaveform(
            timestamp=timestamp,
            analysis_type=WaveformAnalysisType.TRAN,
            source_netlist=source_netlist,
            x_axis_name='time',
            x_axis=ts.time,
            traces=dict(ts.traces),
        )
    if isinstance(analysis, AcAnalysis) and sim_result.ac_sweep is not None:
        ac = sim_result.ac_sweep
        return RawWaveform(
            timestamp=timestamp,
            analysis_type=WaveformAnalysisType.AC,
            source_netlist=source_netlist,
            x_axis_name='frequency',
            x_axis=ac.frequency,
            traces=dict(ac.traces_real),
            traces_imag=dict(ac.traces_imag),
        )
    return None


def _extract_op_from_tran_tail(
    time_series: TimeSeries,
    fraction: float = _DEFAULT_OP_FALLBACK_TAIL_FRACTION,
) -> dict[str, float]:
    """
    Извлечь synthetic operating-point из settled tail TRAN-результата (T145).

    Average values per trace over last `fraction` of samples (default 10%,
    min 1 sample). Сравним с реальным `.OP` для tube/saturable circuits,
    которые DC-solver не может найти прямо.
    """
    n = len(time_series.time)
    take = max(1, int(n * fraction))
    out: dict[str, float] = {}
    for signal, values in time_series.traces.items():
        tail = values[-take:]
        out[signal] = sum(tail) / len(tail)
    return out


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


__all__ = ['_extract_op_from_tran_tail', 'sim_run']
