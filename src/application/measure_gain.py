"""
measure_gain — gain в точке частоты (T023 Phase B).

Two modes (Clarify Q-C → c):

- ``mode='small'``: AC analysis с n_points=2 workaround (Analyze A2).
  V-source auto-injection'ит `AC 1` modifier (ensure_ac_modifier — Phase B
  mid-decision 2026-05-26). `value_linear = |H(f)| = |V_out / V_in|`
  (AC magnitude 1 → H напрямую). `value_db = 20·log10(value_linear)`.
- ``mode='large'``: TRAN с sin-source amplitude `v_in_peak`, RMS-based
  ratio output / input на settle-portion (последние ~2 периода). Default
  `t_stop = 10/freq`, `t_step = period/100`.
"""

from __future__ import annotations

import asyncio
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from domain.measurement import GainMeasurement
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import AcAnalysis, TranAnalysis

if TYPE_CHECKING:
    from ports.outbound.netlist_editor import NetlistEditor
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


_AC_NPOINTS = 2
_AC_F_STOP_FACTOR = 1.0001
_TRAN_PERIODS = 10
_TRAN_SAMPLES_PER_PERIOD = 100
_SETTLE_PERIODS = 8  # из 10 — последние 2 периода для RMS measurement


async def measure_gain(
    *,
    netlist: Path,
    frequency_hz: float,
    mode: Literal['small', 'large'],
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    output_signal: str = 'v(load)',
    input_source: str | None = None,
    input_signal: str | None = None,
    v_in_peak: float | None = None,
    t_stop: float | None = None,
    t_step: float | None = None,
    timeout_seconds: float = 60.0,
    sim_results_writer: SimResultsRepository | None = None,
    project_root: Path | None = None,
    tool: str = 'ngspice',
) -> GainMeasurement:
    """
    Измерить gain в точке `frequency_hz` (small AC или large TRAN).

    Args:
        netlist: путь к SPICE-netlist'у. Use case читает его, мутирует
            (`ensure_ac_modifier` для small / `set_sin_source_amplitude`
            для large), записывает результат в `TemporaryDirectory`
            (T165 — cleanup гарантирован context manager'ом) и
            передаёт в simulator.
        frequency_hz: частота измерения.
        mode: ``'small'`` (AC) или ``'large'`` (TRAN).
        simulator: outbound port (ngspice).
        netlist_editor: outbound port (text manipulation).
        output_signal: trace name для измерения (default ``v(load)``).
            Должен присутствовать в результате симулятора.
        input_source: V-source ref для мутации (`ensure_ac_modifier` /
            `set_sin_source_amplitude`). При ``None`` — auto-detect
            через `netlist_editor.find_top_level_v_sources` (Clarify
            Q-G → c). Ambiguity → ValueError.
        input_signal: trace name для VO и для RMS-computation в large
            mode. В small mode default = ``input_source`` (source ref
            хранится в VO). В large mode caller обязан передать имя
            trace'а явно (например ``v(/in)``).
        v_in_peak: обязательно для ``mode='large'``.
        t_stop: TRAN override; default — 10 циклов входной частоты.
        t_step: TRAN override; default — period/100.
        timeout_seconds: лимит на simulator.run (default 60s).
        sim_results_writer: optional outbound port для persistence
            результата в `.efactory/sim-results/`.
        project_root: обязателен парно с `sim_results_writer`.
        tool: имя инструмента для SimResult snapshot (default ngspice).

    Returns:
        `GainMeasurement` с `value_db`, `value_linear`, и точкой
        измерения.

    Raises:
        ValueError: для `mode='large'` без `v_in_peak`; для multiple
            V-sources без `input_signal`; для отсутствующего output
            signal в результате; для partial sim-results DI.
        SimulatorUnavailableError / SimulationFailedError: forward'аются
            из simulator.

    """
    if (sim_results_writer is None) != (project_root is None):
        msg = (
            'sim_results_writer и project_root должны быть переданы пара '
            '(оба или ни одного).'
        )
        raise ValueError(msg)

    base_text = await asyncio.to_thread(netlist.read_text)
    source_ref = _resolve_input_source(
        netlist_text=base_text,
        editor=netlist_editor,
        explicit=input_source,
    )

    if mode == 'small':
        result_dto = await _measure_small(
            netlist=netlist,
            base_text=base_text,
            frequency_hz=frequency_hz,
            input_source_ref=source_ref,
            input_signal=input_signal,
            output_signal=output_signal,
            simulator=simulator,
            netlist_editor=netlist_editor,
            timeout_seconds=timeout_seconds,
        )
    else:
        if v_in_peak is None:
            msg = 'measure_gain: v_in_peak required for mode="large"'
            raise ValueError(msg)
        if input_signal is None:
            msg = (
                'measure_gain: input_signal required for mode="large" '
                '(trace name like "v(/in)"); pass it explicitly.'
            )
            raise ValueError(msg)
        result_dto = await _measure_large(
            netlist=netlist,
            base_text=base_text,
            frequency_hz=frequency_hz,
            input_source_ref=source_ref,
            input_signal=input_signal,
            output_signal=output_signal,
            v_in_peak=v_in_peak,
            t_stop=t_stop,
            t_step=t_step,
            simulator=simulator,
            netlist_editor=netlist_editor,
            timeout_seconds=timeout_seconds,
        )

    if sim_results_writer is not None and project_root is not None:
        snapshot = _build_snapshot(
            measurement=result_dto,
            netlist=netlist,
            project_root=project_root,
            tool=tool,
        )
        await sim_results_writer.write(result=snapshot, project_root=project_root)

    return result_dto


def _resolve_input_source(
    *,
    netlist_text: str,
    editor: NetlistEditor,
    explicit: str | None,
) -> str:
    """Auto-detect V-source ref для mutation (или вернуть explicit)."""
    if explicit is not None:
        return explicit
    sources = editor.find_top_level_v_sources(netlist_text)
    if len(sources) == 1:
        return sources[0]
    if len(sources) == 0:
        msg = 'measure_gain: no V-source in netlist; pass input_source explicitly.'
        raise ValueError(msg)
    candidates = ', '.join(sources)
    msg = (
        f'measure_gain: multiple V-sources in netlist '
        f'({candidates}); pass input_source explicitly.'
    )
    raise ValueError(msg)


async def _measure_small(
    *,
    netlist: Path,
    base_text: str,
    frequency_hz: float,
    input_source_ref: str,
    input_signal: str | None,
    output_signal: str,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    timeout_seconds: float,
) -> GainMeasurement:
    prepared = netlist_editor.ensure_ac_modifier(
        base_text,
        source_ref=input_source_ref,
        ac_magnitude=1.0,
    )

    analysis = AcAnalysis(
        sweep='dec',
        n_points=_AC_NPOINTS,
        f_start=frequency_hz,
        f_stop=frequency_hz * _AC_F_STOP_FACTOR,
    )
    with tempfile.TemporaryDirectory(prefix='efactory-gain-') as tmp_dir:
        tmp_netlist = Path(tmp_dir) / f'{netlist.stem}.tmp_gain.cir'
        await asyncio.to_thread(tmp_netlist.write_text, prepared)
        sim_result = await simulator.run(
            tmp_netlist,
            analysis,
            timeout_seconds=timeout_seconds,
        )
    if sim_result.ac_sweep is None:
        msg = 'measure_gain: simulator вернул нет ac_sweep result в small mode'
        raise ValueError(msg)

    real = _trace_or_raise(sim_result.ac_sweep.traces_real, output_signal)
    imag = _trace_or_raise(sim_result.ac_sweep.traces_imag, output_signal)
    magnitude = math.hypot(real[0], imag[0])
    return GainMeasurement(
        value_linear=magnitude,
        value_db=_db(magnitude),
        frequency_hz=frequency_hz,
        mode='small',
        input_signal=input_signal if input_signal is not None else input_source_ref,
        output_signal=output_signal,
        v_in_peak=None,
    )


async def _measure_large(
    *,
    netlist: Path,
    base_text: str,
    frequency_hz: float,
    input_source_ref: str,
    input_signal: str,
    output_signal: str,
    v_in_peak: float,
    t_stop: float | None,
    t_step: float | None,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    timeout_seconds: float,
) -> GainMeasurement:
    prepared = netlist_editor.set_sin_source_amplitude(
        base_text,
        source_ref=input_source_ref,
        amplitude_peak=v_in_peak,
        frequency_hz=frequency_hz,
    )

    period_s = 1.0 / frequency_hz
    effective_t_stop = t_stop if t_stop is not None else _TRAN_PERIODS * period_s
    effective_t_step = (
        t_step if t_step is not None else period_s / _TRAN_SAMPLES_PER_PERIOD
    )

    analysis = TranAnalysis(t_step=effective_t_step, t_stop=effective_t_stop)
    with tempfile.TemporaryDirectory(prefix='efactory-gain-') as tmp_dir:
        tmp_netlist = Path(tmp_dir) / f'{netlist.stem}.tmp_gain.cir'
        await asyncio.to_thread(tmp_netlist.write_text, prepared)
        sim_result = await simulator.run(
            tmp_netlist,
            analysis,
            timeout_seconds=timeout_seconds,
        )
    if sim_result.time_series is None:
        msg = 'measure_gain: simulator вернул нет time_series в large mode'
        raise ValueError(msg)

    in_trace = _trace_or_raise(sim_result.time_series.traces, input_signal)
    out_trace = _trace_or_raise(sim_result.time_series.traces, output_signal)

    settle_idx = _settle_start_index(
        time=sim_result.time_series.time,
        period_s=period_s,
        settle_periods=_SETTLE_PERIODS,
    )
    rms_in = _rms(in_trace[settle_idx:])
    rms_out = _rms(out_trace[settle_idx:])
    if rms_in <= 0.0:
        msg = (
            f'measure_gain: RMS({input_signal}) = 0 на settle-portion — '
            f'input source не работает или netlist некорректен.'
        )
        raise ValueError(msg)

    linear = rms_out / rms_in
    return GainMeasurement(
        value_linear=linear,
        value_db=_db(linear),
        frequency_hz=frequency_hz,
        mode='large',
        input_signal=input_signal,
        output_signal=output_signal,
        v_in_peak=v_in_peak,
    )


def _trace_or_raise(
    traces: dict[str, tuple[float, ...]],
    name: str,
) -> tuple[float, ...]:
    if name in traces:
        return traces[name]
    lower_map = {k.lower(): v for k, v in traces.items()}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    available = ', '.join(sorted(traces))
    msg = (
        f'measure_gain: signal {name!r} not found in simulator output; '
        f'available: [{available}]'
    )
    raise ValueError(msg)


def _settle_start_index(
    *,
    time: tuple[float, ...],
    period_s: float,
    settle_periods: int,
) -> int:
    threshold = settle_periods * period_s
    for i, t in enumerate(time):
        if t >= threshold:
            return i
    return max(0, len(time) - 1)


def _rms(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    sq = sum(v * v for v in values)
    return math.sqrt(sq / len(values))


def _db(linear: float) -> float:
    if linear <= 0.0:
        return -math.inf
    return 20.0 * math.log10(linear)


def _build_snapshot(
    *,
    measurement: GainMeasurement,
    netlist: Path,
    project_root: Path,
    tool: str,
) -> SimResult:
    try:
        source_file = str(netlist.resolve().relative_to(project_root.resolve()))
    except ValueError:
        source_file = netlist.name
    timestamp = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    summary = (
        f'gain {measurement.mode}: {measurement.value_db:.2f} dB '
        f'(x{measurement.value_linear:.3g}) @ {measurement.frequency_hz:.0f} Hz'
    )
    return SimResult(
        timestamp=timestamp,
        analysis_type=AnalysisType.GAIN,
        source_file=source_file,
        tool=tool,
        duration_seconds=0.0,
        summary=summary,
        metrics={
            'value_db': measurement.value_db,
            'value_linear': measurement.value_linear,
            'frequency_hz': measurement.frequency_hz,
            'mode': measurement.mode,
            'input_signal': measurement.input_signal,
            'output_signal': measurement.output_signal,
            'v_in_peak': measurement.v_in_peak,
        },
    )


__all__ = ['measure_gain']
