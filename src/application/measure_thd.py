"""
measure_thd — single-point THD на as-is netlist'е (T023 Phase B).

Независимый use case (Clarify Q-D → b), не wrapper T131
`analyze_distortion_spectrum`. T131 — sweep по (freq, power) cells через
saturable injection в OPT-aware netlist; T023 — одна точка на arbitrary
netlist'е без знаний о magnetic component'ах.

Pipeline:
1. Auto-detect input V-source (Clarify Q-G → c) или явный `input_source`.
2. `set_sin_source_amplitude(source_ref, v_in_peak, frequency_hz)`.
3. Write modified netlist в tmp file.
4. Run `FourierAnalysis` (TRAN + ngspice `fourier`) через `Simulator`.
5. Extract из `FourierResult`: `thd_percent`, fundamental, dominant
   harmonic (max normalized среди n ≥ 2).
6. Compute `measured_power_w = (V_fund_peak / √2)² / R_load`.
7. Return `ThdMeasurement`; optional SimResult persistence.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.measurement import ThdMeasurement
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import FourierAnalysis, TranAnalysis

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import HarmonicSample
    from ports.outbound.netlist_editor import NetlistEditor
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


_FIRST_DISTORTION_HARMONIC = 2  # DC=0, fundamental=1, n=2 — первая «настоящая»
_DEFAULT_PERIODS = 10
_DEFAULT_SAMPLES_PER_PERIOD = 100
_DEFAULT_N_HARMONICS = 10


async def measure_thd(
    *,
    netlist: Path,
    frequency_hz: float,
    v_in_peak: float,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    signal: str = 'v(load)',
    input_source: str | None = None,
    load_ohm: float = 8.0,
    n_harmonics: int = _DEFAULT_N_HARMONICS,
    periods: int = _DEFAULT_PERIODS,
    samples_per_period: int = _DEFAULT_SAMPLES_PER_PERIOD,
    timeout_seconds: float = 60.0,
    sim_results_writer: SimResultsRepository | None = None,
    project_root: Path | None = None,
    tool: str = 'ngspice',
) -> ThdMeasurement:
    """
    Измерить THD в точке `(frequency_hz, v_in_peak)` через TRAN + Fourier.

    Args:
        netlist: путь к SPICE-netlist'у.
        frequency_hz: fundamental частота (Hz).
        v_in_peak: peak amplitude входного источника (V). Caller знает
            нужное значение — T023 НЕ делает target-power calibration
            loop (это специализация T131).
        simulator: outbound port (ngspice).
        netlist_editor: outbound port (text manipulation).
        signal: trace name для Fourier-измерения (default `v(load)`).
        input_source: V-source ref для mutation (auto-detect при None).
        load_ohm: нагрузка (Ω) для derive measured_power_w (default 8 —
            audio standard).
        n_harmonics: число harmonics для Fourier analysis (3..20).
        periods: число периодов входной частоты для TRAN (default 10).
        samples_per_period: точек на период для TRAN (default 100).
        timeout_seconds: лимит на simulator.run (default 60s).
        sim_results_writer: optional outbound port для persistence
            результата в `.efactory/sim-results/`.
        project_root: обязателен парно с `sim_results_writer`.
        tool: имя инструмента для SimResult snapshot (default ngspice).

    Returns:
        `ThdMeasurement` со всеми metrics + контекстом точки.

    Raises:
        ValueError: для multiple V-sources без `input_source`; для
            отсутствующего `fourier_result` / fundamental harmonic;
            для partial sim-results DI.
        SimulatorUnavailableError / SimulationFailedError: forward'аются.

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

    prepared = netlist_editor.set_sin_source_amplitude(
        base_text,
        source_ref=source_ref,
        amplitude_peak=v_in_peak,
        frequency_hz=frequency_hz,
    )
    tmp_netlist = netlist.with_suffix('.tmp_thd.cir')
    await asyncio.to_thread(tmp_netlist.write_text, prepared)

    period_s = 1.0 / frequency_hz
    tran = TranAnalysis(
        t_step=period_s / samples_per_period,
        t_stop=periods * period_s,
    )
    analysis = FourierAnalysis(
        tran=tran,
        fundamental_hz=frequency_hz,
        n_harmonics=n_harmonics,
        signal=signal,
    )
    sim_result = await simulator.run(
        tmp_netlist,
        analysis,
        timeout_seconds=timeout_seconds,
    )
    fourier = sim_result.fourier_result
    if fourier is None:
        msg = (
            f'measure_thd: simulator вернул нет fourier_result '
            f'(freq={frequency_hz} Hz, v_in_peak={v_in_peak})'
        )
        raise ValueError(msg)

    fundamental = next((h for h in fourier.harmonics if h.n == 1), None)
    if fundamental is None:
        msg = (
            f'measure_thd: no fundamental (n=1) harmonic in result '
            f'(freq={frequency_hz} Hz)'
        )
        raise ValueError(msg)

    dominant = _dominant_harmonic(fourier.harmonics)
    v_fund_rms = fundamental.magnitude / math.sqrt(2.0)
    measured_power_w = v_fund_rms * v_fund_rms / load_ohm

    result = ThdMeasurement(
        thd_percent=fourier.thd_percent,
        fundamental_hz=fourier.fundamental_hz,
        v_in_peak=v_in_peak,
        measured_power_w=measured_power_w,
        dominant_harmonic_n=dominant.n,
        dominant_harmonic_percent=dominant.normalized * 100.0,
        signal=signal,
        n_harmonics=n_harmonics,
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
        msg = 'measure_thd: no V-source in netlist; pass input_source explicitly.'
        raise ValueError(msg)
    candidates = ', '.join(sources)
    msg = (
        f'measure_thd: multiple V-sources in netlist '
        f'({candidates}); pass input_source explicitly.'
    )
    raise ValueError(msg)


def _dominant_harmonic(
    harmonics: tuple[HarmonicSample, ...],
) -> HarmonicSample:
    candidates = [h for h in harmonics if h.n >= _FIRST_DISTORTION_HARMONIC]
    if not candidates:
        msg = (
            'measure_thd: no harmonics with n≥2 in Fourier result — '
            'n_harmonics должен быть ≥3 (Pydantic validation catches earlier)'
        )
        raise ValueError(msg)
    return max(candidates, key=lambda h: h.normalized)


def _build_snapshot(
    *,
    measurement: ThdMeasurement,
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
        f'THD: {measurement.thd_percent:.3f}% @ '
        f'{measurement.fundamental_hz:.0f} Hz '
        f'(dominant n={measurement.dominant_harmonic_n})'
    )
    return SimResult(
        timestamp=timestamp,
        analysis_type=AnalysisType.THD,
        source_file=source_file,
        tool=tool,
        duration_seconds=0.0,
        summary=summary,
        metrics={
            'thd_percent': measurement.thd_percent,
            'fundamental_hz': measurement.fundamental_hz,
            'v_in_peak': measurement.v_in_peak,
            'measured_power_w': measurement.measured_power_w,
            'dominant_harmonic_n': measurement.dominant_harmonic_n,
            'dominant_harmonic_percent': measurement.dominant_harmonic_percent,
            'signal': measurement.signal,
            'n_harmonics': measurement.n_harmonics,
        },
    )


__all__ = ['measure_thd']
