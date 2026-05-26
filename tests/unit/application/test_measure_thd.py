"""measure_thd use case — single-point THD на as-is netlist (T023 Phase B)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from application.measure_thd import measure_thd
from domain.measurement import ThdMeasurement
from domain.simulation import (
    AnalysisSpec,
    FourierAnalysis,
    FourierResult,
    HarmonicSample,
    SimulationResult,
)
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)

_NETLIST_SINGLE_SOURCE = (
    'V_in /in 0 SIN(0 0.1 1000)\n'
    'R_load /load 0 8\n'
    '.end\n'
)

_NETLIST_TWO_SOURCES = (
    'V_in /in 0 SIN(0 0.1 1000)\n'
    'V_bplus /bplus 0 DC 250\n'
    'R_load /load 0 8\n'
    '.end\n'
)


class FakeSimulator:
    def __init__(self, result: SimulationResult) -> None:
        self._result = result
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        return self._result


class FailingSimulator:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        raise self._exc


class _RecordingEditor:
    def __init__(self) -> None:
        from adapters.outbound.ngspice.netlist_substitution import (
            NgspiceNetlistEditor,
        )

        self._inner = NgspiceNetlistEditor()
        self.set_sin_calls: list[tuple[str, float, float]] = []

    def substitute_subckt_library(
        self, netlist_text: str, target_subckt_name: str, new_subckt_text: str,
    ) -> str:
        return self._inner.substitute_subckt_library(
            netlist_text, target_subckt_name, new_subckt_text,
        )

    def set_sin_source_amplitude(
        self, netlist_text: str, *, source_ref: str,
        amplitude_peak: float, frequency_hz: float, offset: float = 0.0,
    ) -> str:
        self.set_sin_calls.append((source_ref, amplitude_peak, frequency_hz))
        return self._inner.set_sin_source_amplitude(
            netlist_text, source_ref=source_ref,
            amplitude_peak=amplitude_peak, frequency_hz=frequency_hz,
            offset=offset,
        )

    def ensure_ac_modifier(
        self, netlist_text: str, *, source_ref: str, ac_magnitude: float = 1.0,
    ) -> str:
        return self._inner.ensure_ac_modifier(
            netlist_text, source_ref=source_ref, ac_magnitude=ac_magnitude,
        )

    def find_top_level_v_sources(self, netlist_text: str) -> tuple[str, ...]:
        return self._inner.find_top_level_v_sources(netlist_text)


def _fourier_result(
    *,
    fundamental_magnitude: float = 1.0,
    thd_percent: float = 2.5,
    dominant_n: int = 2,
    dominant_normalized: float = 0.02,
    fundamental_hz: float = 1000.0,
) -> SimulationResult:
    harmonics = [
        HarmonicSample(
            n=0, frequency_hz=0.0, magnitude=0.0, phase_deg=0.0, normalized=0.0,
        ),
        HarmonicSample(
            n=1, frequency_hz=fundamental_hz, magnitude=fundamental_magnitude,
            phase_deg=0.0, normalized=1.0,
        ),
    ]
    for n in range(2, 11):
        normalized = dominant_normalized if n == dominant_n else dominant_normalized / 5.0
        harmonics.append(
            HarmonicSample(
                n=n, frequency_hz=n * fundamental_hz,
                magnitude=fundamental_magnitude * normalized,
                phase_deg=0.0, normalized=normalized,
            ),
        )
    return SimulationResult(
        fourier_result=FourierResult(
            fundamental_hz=fundamental_hz,
            thd_percent=thd_percent,
            harmonics=tuple(harmonics),
        ),
    )


async def test_measure_thd_returns_extracted_metrics(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(
        _fourier_result(
            fundamental_magnitude=4.0, thd_percent=3.7,
            dominant_n=2, dominant_normalized=0.037,
        ),
    )

    result = await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
        simulator=simulator, netlist_editor=_RecordingEditor(),
        load_ohm=8.0,
    )

    assert isinstance(result, ThdMeasurement)
    assert result.thd_percent == pytest.approx(3.7)
    assert result.fundamental_hz == pytest.approx(1000.0)
    assert result.v_in_peak == pytest.approx(0.1)
    assert result.dominant_harmonic_n == 2
    assert result.dominant_harmonic_percent == pytest.approx(3.7)
    assert result.signal == 'v(load)'
    assert result.n_harmonics == 10


async def test_measure_thd_measured_power_from_fundamental(tmp_path: Path) -> None:
    """measured_power = (V_fund_rms)² / R_load = (V_peak/√2)² / R_load."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(
        _fourier_result(fundamental_magnitude=4.0, thd_percent=1.0),
    )

    result = await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
        simulator=simulator, netlist_editor=_RecordingEditor(),
        load_ohm=8.0,
    )

    expected_rms = 4.0 / math.sqrt(2.0)
    expected_power = expected_rms ** 2 / 8.0
    assert result.measured_power_w == pytest.approx(expected_power)


async def test_measure_thd_sets_sin_source_amplitude_and_freq(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_fourier_result())
    editor = _RecordingEditor()

    await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.25,
        simulator=simulator, netlist_editor=editor,
    )

    assert editor.set_sin_calls == [('V_in', 0.25, 1000.0)]


async def test_measure_thd_uses_fourier_analysis(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_fourier_result())

    await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    _, analysis, _ = simulator.calls[0]
    assert isinstance(analysis, FourierAnalysis)
    assert analysis.fundamental_hz == 1000.0
    assert analysis.signal == 'v(load)'
    assert analysis.n_harmonics == 10
    assert analysis.tran.t_stop == pytest.approx(10.0 / 1000.0)
    assert analysis.tran.t_step == pytest.approx((1.0 / 1000.0) / 100.0)


async def test_measure_thd_custom_n_harmonics_and_periods(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_fourier_result())

    await measure_thd(
        netlist=netlist, frequency_hz=500.0, v_in_peak=0.1,
        n_harmonics=15, periods=20, samples_per_period=200,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    _, analysis, _ = simulator.calls[0]
    assert isinstance(analysis, FourierAnalysis)
    assert analysis.n_harmonics == 15
    assert analysis.tran.t_stop == pytest.approx(20.0 / 500.0)
    assert analysis.tran.t_step == pytest.approx((1.0 / 500.0) / 200.0)


async def test_measure_thd_auto_detects_single_source(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_fourier_result())
    editor = _RecordingEditor()

    await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
        simulator=simulator, netlist_editor=editor,
    )

    assert editor.set_sin_calls[0][0] == 'V_in'


async def test_measure_thd_raises_on_multiple_sources(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_TWO_SOURCES)
    simulator = FakeSimulator(_fourier_result())

    with pytest.raises(ValueError, match='multiple V-sources'):
        await measure_thd(
            netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_thd_explicit_input_source(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_TWO_SOURCES)
    simulator = FakeSimulator(_fourier_result())
    editor = _RecordingEditor()

    await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
        input_source='V_in', simulator=simulator, netlist_editor=editor,
    )

    assert editor.set_sin_calls[0][0] == 'V_in'


async def test_measure_thd_finds_dominant_harmonic_correctly(tmp_path: Path) -> None:
    """Dominant = max normalized среди n≥2 (DC/fundamental исключены)."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(
        _fourier_result(
            fundamental_magnitude=1.0, thd_percent=5.0,
            dominant_n=3, dominant_normalized=0.05,  # n=3 — самая большая
        ),
    )

    result = await measure_thd(
        netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.dominant_harmonic_n == 3
    assert result.dominant_harmonic_percent == pytest.approx(5.0)


async def test_measure_thd_raises_on_no_fourier_result(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(SimulationResult(operating_points={'p': 0.0}))

    with pytest.raises(ValueError, match='fourier_result'):
        await measure_thd(
            netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_thd_raises_when_no_fundamental(tmp_path: Path) -> None:
    """FourierResult без n=1 harmonic — нелогично, raise."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = SimulationResult(
        fourier_result=FourierResult(
            fundamental_hz=1000.0, thd_percent=1.0,
            harmonics=(
                HarmonicSample(
                    n=0, frequency_hz=0.0, magnitude=0.0,
                    phase_deg=0.0, normalized=0.0,
                ),
                HarmonicSample(
                    n=2, frequency_hz=2000.0, magnitude=0.5,
                    phase_deg=0.0, normalized=0.5,
                ),
            ),
        ),
    )
    simulator = FakeSimulator(sim_result)

    with pytest.raises(ValueError, match='fundamental'):
        await measure_thd(
            netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_thd_propagates_simulator_failed(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FailingSimulator(SimulationFailedError('no conv'))

    with pytest.raises(SimulationFailedError):
        await measure_thd(
            netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_thd_propagates_simulator_unavailable(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FailingSimulator(SimulatorUnavailableError('no bin'))

    with pytest.raises(SimulatorUnavailableError):
        await measure_thd(
            netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_thd_partial_writer_di_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_fourier_result())

    class _DummyWriter:
        async def write(self, *, result: object, project_root: Path) -> None: ...

    with pytest.raises(ValueError, match='пара'):
        await measure_thd(
            netlist=netlist, frequency_hz=1000.0, v_in_peak=0.1,
            simulator=simulator, netlist_editor=_RecordingEditor(),
            sim_results_writer=_DummyWriter(),  # type: ignore[arg-type]
        )
