"""
analyze_distortion_spectrum — THD-спектр через saturable SPICE (T131 Phase C).

Use case-orchestrator:

1. Сгенерировать saturable transformer subckt (Phase A) из
   `MagneticComponent` + `FrohlichBHCurve` (spec'а).
2. Заменить library reference в netlist'е (`.include <target>.lib`)
   на inline saturable subckt с тем же subckt-name (Phase C
   `substitute_subckt_library`).
3. Для каждой cell `(frequency_hz, target_power_w)`:
   a. Single-pass voltage calibration: `V_in_peak =
      voltage_per_root_power · √target_power_w` (caller-provided
      constant включает sqrt(2·R_load) и линейный gain усилителя).
   b. Переписать source amplitude+frequency у `input_source_ref`
      (Phase C `set_sin_source_amplitude`).
   c. Запустить `.TRAN` + ngspice `fourier <fund> <signal>` через
      `Simulator` (FourierAnalysis branch из Phase B).
   d. Извлечь fundamental rms → measured_power_w; dominant n≥2 harmonic
      по max normalized.
4. Aggregate `ThdSpectrum`.

Calibration **single-pass**, не closed-loop — ThdSweepSpec.find_closest
с tolerance ±20% обеспечивает acceptance gating уже на стороне caller'а
(см. T131 spec Q3 / Analyze W1).
"""

from __future__ import annotations

import asyncio
import math
from time import monotonic
from typing import TYPE_CHECKING

from adapters.outbound.ngspice.netlist_substitution import (
    set_sin_source_amplitude,
    substitute_subckt_library,
)
from adapters.outbound.spice_models.saturable_core import (
    generate_saturable_transformer_subckt,
)
from domain.magnetic import IsolationSide
from domain.simulation import FourierAnalysis, TranAnalysis
from domain.thd import ThdMeasurementPoint, ThdSpectrum
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.magnetic import Winding
    from domain.simulation import HarmonicSample
    from domain.thd import ThdSweepSpec
    from ports.outbound.simulator import Simulator


_DEFAULT_TIMEOUT_PER_CELL_SECONDS = 60.0
_FIRST_DISTORTION_HARMONIC = 2  # DC=0, fundamental=1, n=2 — первая «настоящая»


async def analyze_distortion_spectrum(
    *,
    base_netlist: Path,
    spec: ThdSweepSpec,
    simulator: Simulator,
    workdir: Path,
    timeout_per_cell_seconds: float = _DEFAULT_TIMEOUT_PER_CELL_SECONDS,
) -> ThdSpectrum:
    """
    Прогнать THD-спектр на (freq × power) матрицы для magnetic component.

    Args:
        base_netlist: путь к netlist'у, полученному `kicad-cli sch
            export netlist --format spice`. Должен содержать `.include`
            (или inline `.SUBCKT`) с именем `spec.target_subckt_name` и
            voltage source с ref `spec.input_source_ref` в форме
            ``<ref> <node1> <node2> ... SIN(...)``.
        spec: ThdSweepSpec — компонент + B-H curve + sweep matrix +
            netlist-связка + calibration constant.
        simulator: outbound port (NgspiceSimulator).
        workdir: куда писать cell netlist'ы (one per (freq, power) cell).
        timeout_per_cell_seconds: timeout per cell.

    Raises:
        SimulationFailedError: при ошибке симулятора или отсутствии
            fundamental harmonic в результате.
        ValueError: при отсутствии `.include`/`.SUBCKT <target>` или
            source ref'а в netlist'е.

    """
    await asyncio.to_thread(workdir.mkdir, parents=True, exist_ok=True)
    base_text = await asyncio.to_thread(base_netlist.read_text)

    saturable_text = _generate_saturable(spec)
    substituted_text = substitute_subckt_library(
        base_text,
        spec.target_subckt_name,
        saturable_text,
    )

    points: list[ThdMeasurementPoint] = []
    started = monotonic()
    for frequency_hz in spec.frequencies_hz:
        for target_power_w in spec.output_powers_w:
            point = await _measure_cell(
                substituted_text=substituted_text,
                frequency_hz=frequency_hz,
                target_power_w=target_power_w,
                spec=spec,
                simulator=simulator,
                workdir=workdir,
                timeout_seconds=timeout_per_cell_seconds,
            )
            points.append(point)
    runtime = monotonic() - started

    return ThdSpectrum(
        component_name=spec.component.name,
        points=tuple(points),
        runtime_seconds=runtime,
    )


def _generate_saturable(spec: ThdSweepSpec) -> str:
    """Сгенерировать saturable subckt-текст из ThdSweepSpec."""
    primary = spec.component.primary_winding
    secondary = _find_secondary(spec.component.windings)
    return generate_saturable_transformer_subckt(
        subckt_name=spec.target_subckt_name,
        n_primary=primary.number_turns,
        n_secondary=secondary.number_turns,
        a_core_m2=spec.a_core_m2,
        l_path_m=spec.l_path_m,
        r_primary_ohm=spec.r_primary_ohm,
        r_secondary_ohm=spec.r_secondary_ohm,
        bh_curve=spec.bh_curve,
    )


def _find_secondary(windings: tuple[Winding, ...]) -> Winding:
    for w in windings:
        if w.isolation_side is IsolationSide.SECONDARY:
            return w
    msg = (
        'magnetic component has no SECONDARY winding — saturable subckt '
        'requires both primary and secondary'
    )
    raise ValueError(msg)


async def _measure_cell(
    *,
    substituted_text: str,
    frequency_hz: float,
    target_power_w: float,
    spec: ThdSweepSpec,
    simulator: Simulator,
    workdir: Path,
    timeout_seconds: float,
) -> ThdMeasurementPoint:
    amplitude_peak = spec.voltage_per_root_power * math.sqrt(target_power_w)
    cell_text = set_sin_source_amplitude(
        substituted_text,
        source_ref=spec.input_source_ref,
        amplitude_peak=amplitude_peak,
        frequency_hz=frequency_hz,
    )
    cell_netlist = workdir / _cell_filename(frequency_hz, target_power_w)
    await asyncio.to_thread(cell_netlist.write_text, cell_text)

    analysis = _build_fourier_analysis(spec, frequency_hz)
    result = await simulator.run(
        cell_netlist,
        analysis,
        timeout_seconds=timeout_seconds,
    )
    fourier = result.fourier_result
    if fourier is None:
        msg = (
            f'simulator returned no fourier_result for cell '
            f'(freq={frequency_hz} Hz, target_power={target_power_w} W)'
        )
        raise SimulationFailedError(msg)

    fundamental = next(
        (h for h in fourier.harmonics if h.n == 1),
        None,
    )
    if fundamental is None:
        msg = (
            f'no fundamental (n=1) harmonic in result for cell '
            f'(freq={frequency_hz} Hz, target_power={target_power_w} W)'
        )
        raise SimulationFailedError(msg)

    v_load_rms = fundamental.magnitude / math.sqrt(2.0)
    measured_power_w = v_load_rms * v_load_rms / spec.load_ohm
    dominant_n = _dominant_harmonic_n(fourier.harmonics)

    return ThdMeasurementPoint(
        frequency_hz=frequency_hz,
        target_power_w=target_power_w,
        measured_power_w=measured_power_w,
        thd_percent=fourier.thd_percent,
        dominant_harmonic_n=dominant_n,
        harmonics=fourier.harmonics,
    )


def _build_fourier_analysis(
    spec: ThdSweepSpec,
    frequency_hz: float,
) -> FourierAnalysis:
    period_s = 1.0 / frequency_hz
    tran = TranAnalysis(
        t_step=period_s / spec.samples_per_period,
        t_stop=spec.periods_per_run * period_s,
    )
    return FourierAnalysis(
        tran=tran,
        fundamental_hz=frequency_hz,
        n_harmonics=spec.n_harmonics,
        signal=spec.signal_node,
    )


def _dominant_harmonic_n(harmonics: tuple[HarmonicSample, ...]) -> int:
    """Индекс гармоники с max normalized magnitude среди n≥2."""
    candidates = [h for h in harmonics if h.n >= _FIRST_DISTORTION_HARMONIC]
    if not candidates:
        msg = (
            'fourier result has no harmonics with n≥2 — '
            'spec.n_harmonics должен быть ≥3 (Pydantic validation should '
            'catch this earlier)'
        )
        raise SimulationFailedError(msg)
    return max(candidates, key=lambda h: h.normalized).n


def _cell_filename(frequency_hz: float, target_power_w: float) -> str:
    return f'cell_{frequency_hz:.0f}Hz_{target_power_w * 1000:.0f}mW.cir'


__all__ = ['analyze_distortion_spectrum']
