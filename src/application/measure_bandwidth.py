"""
measure_bandwidth — `-N dB` полоса пропускания через AC sweep (T023 Phase B).

Pipeline:
1. Auto-detect input V-source (Clarify Q-G → c) или явный `input_source`.
2. `ensure_ac_modifier(source_ref, 1.0)` (как small-gain — A6 fix).
3. Write modified netlist в `TemporaryDirectory` (T165 cleanup).
4. Run `AcAnalysis(sweep='dec', ...)` через `Simulator`.
5. Compute `|H(f)| = √(real² + imag²)` для `output_signal` (с case-
   insensitive trace lookup).
6. Compute midpoint_db:
   - `midpoint_source='auto'` (default): midband = `max(|H|)` по sweep'у,
     `midpoint_db = 20·log10(midband)`.
   - `midpoint_source='ref_freq'`: midband = `|H(closest_to_ref_freq)|`
     (Clarify Q-H → c).
7. `threshold_db = midpoint_db + ref_db` (default `-3 dB`).
8. f_low = first crossing threshold_db from below (linear interp в log-
   freq); f_high = last crossing from above. Flat response (всё выше
   threshold) → endpoints = sweep edges.
9. Return `BandwidthMeasurement`; optional SimResult persistence.
"""

from __future__ import annotations

import asyncio
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from domain.measurement import BandwidthMeasurement
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import AcAnalysis

if TYPE_CHECKING:
    from ports.outbound.netlist_editor import NetlistEditor
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


_DEFAULT_F_LOW = 1.0
_DEFAULT_F_HIGH = 1e6
_DEFAULT_N_POINTS_PER_DECADE = 10
_DEFAULT_REF_DB = -3.0


async def measure_bandwidth(
    *,
    netlist: Path,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    f_low: float = _DEFAULT_F_LOW,
    f_high: float = _DEFAULT_F_HIGH,
    n_points_per_decade: int = _DEFAULT_N_POINTS_PER_DECADE,
    output_signal: str = 'v(load)',
    input_source: str | None = None,
    ref_db: float = _DEFAULT_REF_DB,
    midpoint_source: Literal['auto', 'ref_freq'] = 'auto',
    ref_freq_hz: float | None = None,
    timeout_seconds: float = 60.0,
    sim_results_writer: SimResultsRepository | None = None,
    project_root: Path | None = None,
    tool: str = 'ngspice',
) -> BandwidthMeasurement:
    """
    Измерить полосу пропускания по `ref_db` относительно midband.

    Args:
        netlist: путь к SPICE-netlist'у.
        simulator: outbound port (ngspice).
        netlist_editor: outbound port (text manipulation).
        f_low: нижняя граница AC sweep'а (Hz, default 1).
        f_high: верхняя граница AC sweep'а (Hz, default 1e6 — audio
            envelope, Analyze A10).
        n_points_per_decade: разрешение sweep'а (default 10).
        output_signal: trace name (default `v(load)`).
        input_source: V-source ref для AC modifier'а (auto при None).
        ref_db: reference (default `-3 dB` относительно midband).
        midpoint_source: `'auto'` (max|H|) или `'ref_freq'`
            (|H(ref_freq_hz)|).
        ref_freq_hz: обязательно при `midpoint_source='ref_freq'`.
        timeout_seconds: лимит на simulator.run (default 60s).
        sim_results_writer: optional outbound port для persistence
            результата в `.efactory/sim-results/`.
        project_root: обязателен парно с `sim_results_writer`.
        tool: имя инструмента для SimResult snapshot (default ngspice).

    Returns:
        `BandwidthMeasurement` с f_low/f_high (linear interp в log-freq
        space между sweep points), midpoint_db, ref_db.

    Raises:
        ValueError: при `midpoint_source='ref_freq'` без `ref_freq_hz`;
            при отсутствующем output_signal; при невыполнении passband
            (max|H| ≤ threshold); для partial sim-results DI; multiple
            V-sources без `input_source`.
        SimulatorUnavailableError / SimulationFailedError: forward'аются.

    """
    if midpoint_source == 'ref_freq' and ref_freq_hz is None:
        msg = 'measure_bandwidth: ref_freq_hz required when midpoint_source="ref_freq".'
        raise ValueError(msg)
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

    prepared = netlist_editor.ensure_ac_modifier(
        base_text,
        source_ref=source_ref,
        ac_magnitude=1.0,
    )

    analysis = AcAnalysis(
        sweep='dec',
        n_points=n_points_per_decade,
        f_start=f_low,
        f_stop=f_high,
    )
    with tempfile.TemporaryDirectory(prefix='efactory-bw-') as tmp_dir:
        tmp_netlist = Path(tmp_dir) / f'{netlist.stem}.tmp_bw.cir'
        await asyncio.to_thread(tmp_netlist.write_text, prepared)
        sim_result = await simulator.run(
            tmp_netlist,
            analysis,
            timeout_seconds=timeout_seconds,
        )
    if sim_result.ac_sweep is None:
        msg = 'measure_bandwidth: simulator вернул нет ac_sweep result'
        raise ValueError(msg)

    frequencies = sim_result.ac_sweep.frequency
    real = _trace_or_raise(sim_result.ac_sweep.traces_real, output_signal)
    imag = _trace_or_raise(sim_result.ac_sweep.traces_imag, output_signal)
    magnitudes_db = tuple(
        _db(math.hypot(r, i)) for r, i in zip(real, imag, strict=True)
    )

    midpoint_db = _compute_midpoint_db(
        frequencies=frequencies,
        magnitudes_db=magnitudes_db,
        midpoint_source=midpoint_source,
        ref_freq_hz=ref_freq_hz,
    )
    threshold_db = midpoint_db + ref_db

    if max(magnitudes_db) <= threshold_db:
        msg = (
            f'measure_bandwidth: max |H| = {max(magnitudes_db):.2f} dB '
            f'≤ threshold {threshold_db:.2f} dB — no passband above '
            f'{ref_db:+.1f} dB reference.'
        )
        raise ValueError(msg)

    f_low_hz, f_high_hz = _find_passband_endpoints(
        frequencies=frequencies,
        magnitudes_db=magnitudes_db,
        threshold_db=threshold_db,
    )

    result = BandwidthMeasurement(
        f_low_hz=f_low_hz,
        f_high_hz=f_high_hz,
        bandwidth_hz=f_high_hz - f_low_hz,
        ref_db=ref_db,
        midpoint_db=midpoint_db,
        midpoint_source=midpoint_source,
        ref_freq_hz=ref_freq_hz,
        passband_signal=output_signal,
        input_signal=source_ref,
    )

    if sim_results_writer is not None and project_root is not None:
        snapshot = _build_snapshot(
            measurement=result,
            netlist=netlist,
            project_root=project_root,
            tool=tool,
        )
        await sim_results_writer.write(result=snapshot, project_root=project_root)

    return result


def _resolve_input_source(
    *,
    netlist_text: str,
    editor: NetlistEditor,
    explicit: str | None,
) -> str:
    if explicit is not None:
        return explicit
    sources = editor.find_top_level_v_sources(netlist_text)
    if len(sources) == 1:
        return sources[0]
    if len(sources) == 0:
        msg = 'measure_bandwidth: no V-source in netlist; pass input_source explicitly.'
        raise ValueError(msg)
    candidates = ', '.join(sources)
    msg = (
        f'measure_bandwidth: multiple V-sources in netlist '
        f'({candidates}); pass input_source explicitly.'
    )
    raise ValueError(msg)


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
        f'measure_bandwidth: signal {name!r} not found in simulator '
        f'output; available: [{available}]'
    )
    raise ValueError(msg)


def _db(linear: float) -> float:
    if linear <= 0.0:
        return -math.inf
    return 20.0 * math.log10(linear)


def _compute_midpoint_db(
    *,
    frequencies: tuple[float, ...],
    magnitudes_db: tuple[float, ...],
    midpoint_source: Literal['auto', 'ref_freq'],
    ref_freq_hz: float | None,
) -> float:
    if midpoint_source == 'auto':
        return max(magnitudes_db)
    if ref_freq_hz is None:
        # Caller-уровень уже guards это (см. measure_bandwidth) — defensive.
        msg = '_compute_midpoint_db: ref_freq_hz required for ref_freq mode'
        raise ValueError(msg)
    # Closest freq в sweep array к ref_freq_hz:
    idx = min(
        range(len(frequencies)),
        key=lambda i: abs(math.log10(frequencies[i]) - math.log10(ref_freq_hz)),
    )
    return magnitudes_db[idx]


def _find_passband_endpoints(
    *,
    frequencies: tuple[float, ...],
    magnitudes_db: tuple[float, ...],
    threshold_db: float,
) -> tuple[float, float]:
    """Найти f_low / f_high по log-freq linear interpolation."""
    above = [i for i, db in enumerate(magnitudes_db) if db > threshold_db]
    if not above:
        msg = 'no points above threshold — should be caught upstream'
        raise ValueError(msg)
    first = above[0]
    last = above[-1]

    f_low_hz = (
        frequencies[first]
        if first == 0
        else _interp_log(
            f_lo=frequencies[first - 1],
            f_hi=frequencies[first],
            db_lo=magnitudes_db[first - 1],
            db_hi=magnitudes_db[first],
            threshold_db=threshold_db,
        )
    )
    f_high_hz = (
        frequencies[last]
        if last == len(frequencies) - 1
        else _interp_log(
            f_lo=frequencies[last],
            f_hi=frequencies[last + 1],
            db_lo=magnitudes_db[last],
            db_hi=magnitudes_db[last + 1],
            threshold_db=threshold_db,
        )
    )
    return f_low_hz, f_high_hz


def _interp_log(
    *,
    f_lo: float,
    f_hi: float,
    db_lo: float,
    db_hi: float,
    threshold_db: float,
) -> float:
    """Linear interpolation в log-freq space (AC sweep — geometric)."""
    if db_hi == db_lo:
        return f_lo
    frac = (threshold_db - db_lo) / (db_hi - db_lo)
    log_f = math.log10(f_lo) + frac * (math.log10(f_hi) - math.log10(f_lo))
    return 10.0**log_f


def _build_snapshot(
    *,
    measurement: BandwidthMeasurement,
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
        f'BW: {measurement.f_low_hz:.0f} Hz … '
        f'{measurement.f_high_hz:.0f} Hz '
        f'({measurement.bandwidth_hz:.0f} Hz @ {measurement.ref_db:+.1f} dB)'
    )
    return SimResult(
        timestamp=timestamp,
        analysis_type=AnalysisType.BANDWIDTH,
        source_file=source_file,
        tool=tool,
        duration_seconds=0.0,
        summary=summary,
        metrics={
            'f_low_hz': measurement.f_low_hz,
            'f_high_hz': measurement.f_high_hz,
            'bandwidth_hz': measurement.bandwidth_hz,
            'ref_db': measurement.ref_db,
            'midpoint_db': measurement.midpoint_db,
            'midpoint_source': measurement.midpoint_source,
            'ref_freq_hz': measurement.ref_freq_hz,
            'passband_signal': measurement.passband_signal,
            'input_signal': measurement.input_signal,
        },
    )


__all__ = ['measure_bandwidth']
