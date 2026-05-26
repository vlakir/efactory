"""measure_bandwidth use case — -N dB полоса пропускания (T023 Phase B)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from application.measure_bandwidth import measure_bandwidth
from domain.measurement import BandwidthMeasurement
from domain.simulation import (
    AcAnalysis,
    AcSweep,
    AnalysisSpec,
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
        self.ensure_ac_calls: list[tuple[str, float]] = []

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


def _ac_sweep_bandpass(
    *,
    output_signal: str = 'v(load)',
    frequencies: tuple[float, ...] = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0),
    magnitudes_db: tuple[float, ...] = (-30.0, -20.0, -2.0, 0.0, -2.0, -20.0),
) -> SimulationResult:
    """Bandpass АЧХ: midband на f=1k @ 0 dB, -2 dB на 100/10k (above -3 dB threshold).

    f_low/f_high crossing'и: интерполируются между [10/-20 → 100/-2] и
    [10000/-2 → 100000/-20] в log-freq linear space.
    """
    assert len(frequencies) == len(magnitudes_db)
    real = tuple(10 ** (m / 20.0) for m in magnitudes_db)
    imag = tuple(0.0 for _ in frequencies)
    return SimulationResult(
        ac_sweep=AcSweep(
            frequency=frequencies,
            traces_real={output_signal: real},
            traces_imag={output_signal: imag},
        ),
    )


def _ac_sweep_flat(
    *, frequencies: tuple[float, ...], magnitude: float, output_signal: str = 'v(load)',
) -> SimulationResult:
    n = len(frequencies)
    return SimulationResult(
        ac_sweep=AcSweep(
            frequency=frequencies,
            traces_real={output_signal: (magnitude,) * n},
            traces_imag={output_signal: (0.0,) * n},
        ),
    )


async def test_measure_bandwidth_returns_pass_band_endpoints(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    result = await measure_bandwidth(
        netlist=netlist, simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    assert isinstance(result, BandwidthMeasurement)
    assert result.midpoint_db == pytest.approx(0.0, abs=0.5)
    # Точки -2 dB выше threshold (-3 dB); crossings лежат между
    # -20 dB (f=10/100000) и -2 dB (f=100/10000) с log-freq linear interp.
    # f_low: log_f = 1 + (17/18) * (2-1) = 1.944, f_low ≈ 88 Hz.
    # f_high: log_f = 4 + (1 - 17/18) * (5-4) = 4.056, f_high ≈ 11377 Hz.
    assert 80.0 < result.f_low_hz < 100.0
    assert 10000.0 < result.f_high_hz < 12000.0
    assert result.bandwidth_hz == pytest.approx(
        result.f_high_hz - result.f_low_hz,
    )
    assert result.ref_db == -3.0
    assert result.midpoint_source == 'auto'
    assert result.passband_signal == 'v(load)'
    assert result.input_signal == 'V_in'


async def test_measure_bandwidth_uses_ac_analysis_with_sweep(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    await measure_bandwidth(
        netlist=netlist, f_low=1.0, f_high=1e6,
        n_points_per_decade=20, simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    _, analysis, _ = simulator.calls[0]
    assert isinstance(analysis, AcAnalysis)
    assert analysis.sweep == 'dec'
    assert analysis.n_points == 20
    assert analysis.f_start == pytest.approx(1.0)
    assert analysis.f_stop == pytest.approx(1e6)


async def test_measure_bandwidth_injects_ac_modifier(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())
    editor = _RecordingEditor()

    await measure_bandwidth(
        netlist=netlist, simulator=simulator, netlist_editor=editor,
    )

    assert editor.ensure_ac_calls == [('V_in', 1.0)]


async def test_measure_bandwidth_ref_freq_mode_uses_specified_midpoint(
    tmp_path: Path,
) -> None:
    """midpoint_source='ref_freq' → midpoint = |H(closest_to_ref_freq)|."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    # АЧХ с peak на f=100 (rather than 1000) — auto-mode дал бы midband на 100;
    # ref_freq=1000 даст midband на |H(1000)| = -6 dB.
    sim_result = _ac_sweep_bandpass(
        frequencies=(10.0, 100.0, 1000.0, 10000.0, 100000.0),
        magnitudes_db=(-20.0, 0.0, -6.0, -12.0, -30.0),
    )
    simulator = FakeSimulator(sim_result)

    result = await measure_bandwidth(
        netlist=netlist, midpoint_source='ref_freq', ref_freq_hz=1000.0,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.midpoint_source == 'ref_freq'
    assert result.ref_freq_hz == 1000.0
    assert result.midpoint_db == pytest.approx(-6.0, abs=0.1)


async def test_measure_bandwidth_ref_freq_required_when_mode_is_ref_freq(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    with pytest.raises(ValueError, match='ref_freq_hz'):
        await measure_bandwidth(
            netlist=netlist, midpoint_source='ref_freq',
            simulator=simulator, netlist_editor=_RecordingEditor(),
        )


async def test_measure_bandwidth_flat_response_returns_sweep_endpoints(
    tmp_path: Path,
) -> None:
    """АЧХ flat по всему sweep — нет roll-off, f_low/f_high = sweep edges."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    frequencies = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0)
    simulator = FakeSimulator(_ac_sweep_flat(frequencies=frequencies, magnitude=10.0))

    result = await measure_bandwidth(
        netlist=netlist, f_low=1.0, f_high=1e5,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.f_low_hz == pytest.approx(1.0)
    assert result.f_high_hz == pytest.approx(1e5)


async def test_measure_bandwidth_raises_when_no_passband_above_threshold(
    tmp_path: Path,
) -> None:
    """Если max |H| ≤ threshold нигде — нет passband, raise."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    # Все точки на -50 dB; midpoint=-50; threshold=-53; то есть все точки > threshold → flat,
    # значит нужно ниже -50, чтобы не нашлось ничего выше threshold (-53).
    # Лучше тест: midpoint выше threshold by virtue of single isolated peak,
    # но все точки ниже threshold → так не работает.
    # Альтернативный кейс: empty sweep result.
    sim_result = SimulationResult(
        ac_sweep=AcSweep(
            frequency=(1.0,),
            traces_real={'v(load)': (0.0,)},  # |H| = 0 → -inf dB
            traces_imag={'v(load)': (0.0,)},
        ),
    )
    simulator = FakeSimulator(sim_result)

    with pytest.raises(ValueError, match='passband'):
        await measure_bandwidth(
            netlist=netlist, simulator=simulator,
            netlist_editor=_RecordingEditor(),
        )


async def test_measure_bandwidth_custom_ref_db(tmp_path: Path) -> None:
    """`-6 dB` reference (другая конвенция)."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    result = await measure_bandwidth(
        netlist=netlist, ref_db=-6.0,
        simulator=simulator, netlist_editor=_RecordingEditor(),
    )

    assert result.ref_db == -6.0


async def test_measure_bandwidth_auto_detects_input_source(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    result = await measure_bandwidth(
        netlist=netlist, simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    assert result.input_signal == 'V_in'


async def test_measure_bandwidth_raises_multiple_sources(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_TWO_SOURCES)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    with pytest.raises(ValueError, match='multiple V-sources'):
        await measure_bandwidth(
            netlist=netlist, simulator=simulator,
            netlist_editor=_RecordingEditor(),
        )


async def test_measure_bandwidth_propagates_simulator_failed(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FailingSimulator(SimulationFailedError('no conv'))

    with pytest.raises(SimulationFailedError):
        await measure_bandwidth(
            netlist=netlist, simulator=simulator,
            netlist_editor=_RecordingEditor(),
        )


async def test_measure_bandwidth_propagates_simulator_unavailable(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FailingSimulator(SimulatorUnavailableError('no bin'))

    with pytest.raises(SimulatorUnavailableError):
        await measure_bandwidth(
            netlist=netlist, simulator=simulator,
            netlist_editor=_RecordingEditor(),
        )


async def test_measure_bandwidth_partial_writer_di_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    simulator = FakeSimulator(_ac_sweep_bandpass())

    class _DummyWriter:
        async def write(self, *, result: object, project_root: Path) -> None: ...

    with pytest.raises(ValueError, match='пара'):
        await measure_bandwidth(
            netlist=netlist, simulator=simulator,
            netlist_editor=_RecordingEditor(),
            sim_results_writer=_DummyWriter(),  # type: ignore[arg-type]
        )


async def test_measure_bandwidth_raises_when_output_signal_missing(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    sim_result = SimulationResult(
        ac_sweep=AcSweep(
            frequency=(1.0, 100.0, 10000.0),
            traces_real={'v(other)': (1.0, 1.0, 1.0)},
            traces_imag={'v(other)': (0.0, 0.0, 0.0)},
        ),
    )
    simulator = FakeSimulator(sim_result)

    with pytest.raises(ValueError, match='v\\(load\\)'):
        await measure_bandwidth(
            netlist=netlist, simulator=simulator,
            netlist_editor=_RecordingEditor(),
        )


def _interp_log_freq(
    *, freqs: tuple[float, ...], dbs: tuple[float, ...],
    threshold: float, idx_high: int,
) -> float:
    """Sanity check on log-freq linear interpolation между idx_high-1 и idx_high."""
    f_lo, f_hi = freqs[idx_high - 1], freqs[idx_high]
    db_lo, db_hi = dbs[idx_high - 1], dbs[idx_high]
    frac = (threshold - db_lo) / (db_hi - db_lo)
    log_f = math.log10(f_lo) + frac * (math.log10(f_hi) - math.log10(f_lo))
    return 10 ** log_f


async def test_measure_bandwidth_interpolation_is_log_freq_linear(
    tmp_path: Path,
) -> None:
    """f_low / f_high computed via log-freq linear interp between sweep points."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_NETLIST_SINGLE_SOURCE)
    # АЧХ: f=10 → -6 dB, f=100 → 0 dB (midpoint), f=1000 → -6 dB.
    # Threshold = 0 - 3 = -3 dB. Линейная интерполяция в log-freq:
    # crossing на участке [10, 100]: fraction = (-3 - -6) / (0 - -6) = 0.5
    # f_low = 10^(log10(10) + 0.5 * (log10(100) - log10(10))) = 10^1.5 ≈ 31.6
    # crossing на участке [100, 1000]: fraction = (-3 - 0) / (-6 - 0) = 0.5
    # f_high = 10^(log10(100) + 0.5 * (log10(1000) - log10(100))) = 10^2.5 ≈ 316
    sim_result = _ac_sweep_bandpass(
        frequencies=(10.0, 100.0, 1000.0),
        magnitudes_db=(-6.0, 0.0, -6.0),
    )
    simulator = FakeSimulator(sim_result)

    result = await measure_bandwidth(
        netlist=netlist, simulator=simulator,
        netlist_editor=_RecordingEditor(),
    )

    assert result.f_low_hz == pytest.approx(31.62, rel=0.01)
    assert result.f_high_hz == pytest.approx(316.2, rel=0.01)
