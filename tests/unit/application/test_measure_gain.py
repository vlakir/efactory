"""measure_gain use case — small/large mode gain measurement (T023 Phase B)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from application.measure_gain import measure_gain
from domain.measurement import GainMeasurement
from domain.simulation import (
    AcAnalysis,
    AcSweep,
    AnalysisSpec,
    SimulationResult,
    TimeSeries,
    TranAnalysis,
)
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)

_NETLIST_SINGLE_SOURCE = (
    '* sample tube amp\n'
    'V_in /in 0 SIN(0 0.1 1000)\n'
    'R_load /load 0 8\n'
    '.end\n'
)

_NETLIST_TWO_SOURCES = (
    '* tube amp с B+ supply\n'
    'V_in /in 0 SIN(0 0.1 1000)\n'
    'V_bplus /bplus 0 DC 250\n'
    'R_load /load 0 8\n'
    '.end\n'
)

_NETLIST_NO_SOURCE = '* passive RC\nR1 a b 1k\nC1 b 0 1u\n'


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
    """Реальный NgspiceNetlistEditor + запись calls (для assertions)."""

    def __init__(self) -> None:
        from adapters.outbound.ngspice.netlist_substitution import (
            NgspiceNetlistEditor,
        )

        self._inner = NgspiceNetlistEditor()
        self.ensure_ac_calls: list[tuple[str, float]] = []
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
        self.ensure_ac_calls.append((source_ref, ac_magnitude))
        return self._inner.ensure_ac_modifier(
            netlist_text, source_ref=source_ref, ac_magnitude=ac_magnitude,
        )

    def find_top_level_v_sources(self, netlist_text: str) -> tuple[str, ...]:
        return self._inner.find_top_level_v_sources(netlist_text)


def _ac_sweep_result_with_gain(
    output_signal: str, *, linear_gain: float,
) -> SimulationResult:
    """AC sweep с n_points=2 на одной частоте — линейный gain `linear_gain`."""
    return SimulationResult(
        ac_sweep=AcSweep(
            frequency=(1000.0, 1000.1),
            traces_real={output_signal: (linear_gain, linear_gain)},
            traces_imag={output_signal: (0.0, 0.0)},
        ),
    )


def _tran_result_with_sine(
    input_signal: str, output_signal: str,
    *, v_in_peak: float, gain_linear: float,
) -> SimulationResult:
    """TRAN с idealized sine: V_in = peak·sin, V_out = peak·gain·sin."""
    n = 1000
    t_stop = 0.01
    time = tuple(i * t_stop / n for i in range(n))
    v_in = tuple(v_in_peak * math.sin(2.0 * math.pi * 1000.0 * t) for t in time)
    v_out = tuple(g * gain_linear for g in v_in)
    return SimulationResult(
        time_series=TimeSeries(
            time=time,
            traces={input_signal: v_in, output_signal: v_out},
        ),
    )


# ----------------------------------------------------------- small mode ---


async def test_measure_gain_small_mode_returns_db_and_linear(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=10.0))
    editor = _RecordingEditor()

    result = await measure_gain(
        netlist=netlist,
        frequency_hz=1000.0,
        mode='small',
        simulator=simulator,
        netlist_editor=editor,
    )

    assert isinstance(result, GainMeasurement)
    assert result.mode == 'small'
    assert result.value_linear == pytest.approx(10.0)
    assert result.value_db == pytest.approx(20.0)
    assert result.frequency_hz == 1000.0
    assert result.input_signal == 'V_in'
    assert result.output_signal == 'v(load)'
    assert result.v_in_peak is None


async def test_measure_gain_small_mode_uses_ac_analysis_with_two_points(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=5.0))

    await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='small',
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert len(simulator.calls) == 1
    _, analysis, _ = simulator.calls[0]
    assert isinstance(analysis, AcAnalysis)
    assert analysis.n_points == 2
    assert analysis.f_start == pytest.approx(1000.0)
    assert analysis.f_stop > analysis.f_start
    assert analysis.f_stop == pytest.approx(1000.0 * 1.0001)


async def test_measure_gain_small_mode_injects_ac_modifier(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=2.0))
    editor = _RecordingEditor()

    await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='small',
        simulator=simulator, netlist_editor=editor,
    )

    assert editor.ensure_ac_calls == [('V_in', 1.0)]


async def test_measure_gain_attenuator_db_negative(tmp_path: Path) -> None:
    """Gain < 1 → value_db < 0."""
    netlist = tmp_path / 'attenuator.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=0.5))

    result = await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='small',
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.value_linear == pytest.approx(0.5)
    assert result.value_db == pytest.approx(-6.0206, abs=1e-3)


async def test_measure_gain_small_mode_complex_transfer_function(
    tmp_path: Path,
) -> None:
    """Phase-shifted output: |H|=√(real² + imag²)."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = SimulationResult(
        ac_sweep=AcSweep(
            frequency=(1000.0, 1000.1),
            traces_real={'v(load)': (3.0, 3.0)},
            traces_imag={'v(load)': (4.0, 4.0)},
        ),
    )
    simulator = FakeSimulator(sim_result)

    result = await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='small',
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.value_linear == pytest.approx(5.0)  # |3+4i|
    assert result.value_db == pytest.approx(20.0 * math.log10(5.0), abs=1e-6)


# ----------------------------------------------------------- large mode ---


async def test_measure_gain_large_mode_returns_rms_ratio(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = _tran_result_with_sine(
        'v(in)', 'v(load)', v_in_peak=0.1, gain_linear=10.0,
    )
    simulator = FakeSimulator(sim_result)

    result = await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='large',
        v_in_peak=0.1, input_signal='v(in)', simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    assert result.mode == 'large'
    assert result.v_in_peak == pytest.approx(0.1)
    assert result.value_linear == pytest.approx(10.0, rel=1e-3)
    assert result.value_db == pytest.approx(20.0, abs=1e-3)


async def test_measure_gain_large_mode_uses_tran_with_defaults(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = _tran_result_with_sine(
        'v(in)', 'v(load)', v_in_peak=0.1, gain_linear=10.0,
    )
    simulator = FakeSimulator(sim_result)

    await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='large',
        v_in_peak=0.1, input_signal='v(in)', simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    _, analysis, _ = simulator.calls[0]
    assert isinstance(analysis, TranAnalysis)
    assert analysis.t_stop == pytest.approx(10.0 / 1000.0)
    assert analysis.t_step == pytest.approx((1.0 / 1000.0) / 100.0)


async def test_measure_gain_large_mode_sets_sin_amplitude(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = _tran_result_with_sine(
        'v(in)', 'v(load)', v_in_peak=0.1, gain_linear=10.0,
    )
    simulator = FakeSimulator(sim_result)
    editor = _RecordingEditor()

    await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='large',
        v_in_peak=0.1, input_signal='v(in)', simulator=simulator,
        netlist_editor=editor,
    )

    assert editor.set_sin_calls == [('V_in', 0.1, 1000.0)]


async def test_measure_gain_large_mode_requires_v_in_peak(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(
        _tran_result_with_sine('v(in)', 'v(load)', v_in_peak=0.1, gain_linear=1.0),
    )

    with pytest.raises(ValueError, match='v_in_peak'):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='large',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_gain_large_mode_custom_t_stop_and_t_step(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = _tran_result_with_sine(
        'v(in)', 'v(load)', v_in_peak=0.1, gain_linear=1.0,
    )
    simulator = FakeSimulator(sim_result)

    await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='large',
        v_in_peak=0.1, input_signal='v(in)', t_stop=0.1, t_step=1e-6,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    _, analysis, _ = simulator.calls[0]
    assert isinstance(analysis, TranAnalysis)
    assert analysis.t_stop == pytest.approx(0.1)
    assert analysis.t_step == pytest.approx(1e-6)


# ---------------------------------------------- input source auto-detect ---


async def test_measure_gain_auto_detects_single_v_source(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=1.0))

    result = await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='small',
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.input_signal == 'V_in'


async def test_measure_gain_raises_on_multiple_sources_without_hint(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_TWO_SOURCES)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=1.0))

    with pytest.raises(ValueError, match='multiple V-sources'):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='small',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_gain_raises_on_no_v_sources(tmp_path: Path) -> None:
    netlist = tmp_path / 'passive.cir'
    netlist.write_text(_NETLIST_NO_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=1.0))

    with pytest.raises(ValueError, match='no V-source'):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='small',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_gain_explicit_input_source_overrides_auto(
    tmp_path: Path,
) -> None:
    """В netlist'е 2 source'а, caller указал input_source — никакого error."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_TWO_SOURCES)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=2.0))

    result = await measure_gain(
        netlist=netlist, frequency_hz=1000.0, mode='small',
        input_source='V_in', simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    assert result.input_signal == 'V_in'


# ---------------------------------------------------- output signal handling ---


async def test_measure_gain_raises_when_output_signal_missing(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = SimulationResult(
        ac_sweep=AcSweep(
            frequency=(1000.0, 1000.1),
            traces_real={'v(other_node)': (1.0, 1.0)},
            traces_imag={'v(other_node)': (0.0, 0.0)},
        ),
    )
    simulator = FakeSimulator(sim_result)

    with pytest.raises(ValueError, match='v\\(load\\)'):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='small',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


# ------------------------------------------------------ error propagation ---


async def test_measure_gain_propagates_simulator_unavailable(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FailingSimulator(SimulatorUnavailableError('no ngspice'))

    with pytest.raises(SimulatorUnavailableError):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='small',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_gain_propagates_simulation_failed(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FailingSimulator(SimulationFailedError('no convergence'))

    with pytest.raises(SimulationFailedError):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='small',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


# --------------------------------------------------- sim_results writer ---


async def test_measure_gain_partial_writer_di_raises(tmp_path: Path) -> None:
    """sim_results_writer + project_root должны быть переданы парой."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_result_with_gain('v(load)', linear_gain=1.0))

    class _DummyWriter:
        async def write(self, *, result: object, project_root: Path) -> None: ...

    with pytest.raises(ValueError, match='пара'):
        await measure_gain(
            netlist=netlist, frequency_hz=1000.0, mode='small',
            simulator=simulator, netlist_editor=_RecordingEditor(),
            sim_results_writer=_DummyWriter(),  # type: ignore[arg-type]
        )
