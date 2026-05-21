"""Domain: Simulation + SimulationStatus + SimulationResult (T004 / T008)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from domain.simulation import (
    AcSweep,
    FourierAnalysis,
    FourierResult,
    HarmonicSample,
    Simulation,
    SimulationResult,
    SimulationStatus,
    TimeSeries,
    TranAnalysis,
)


def test_simulation_status_enum() -> None:
    assert set(SimulationStatus) == {
        SimulationStatus.PENDING,
        SimulationStatus.NETLIST_READY,
        SimulationStatus.SIMULATED,
        SimulationStatus.FAILED,
    }


def test_simulation_minimum_fields() -> None:
    sim = Simulation(
        project_id=uuid4(),
        schematic_path=Path('/p/proj/schematic/x.kicad_sch'),
    )
    assert sim.status is SimulationStatus.PENDING
    assert sim.netlist_path is None
    assert sim.result is None
    assert isinstance(sim.id, UUID)
    assert isinstance(sim.created_at, datetime)


def test_simulation_with_netlist_ready_status() -> None:
    sim = Simulation(
        project_id=uuid4(),
        schematic_path=Path('/p/proj/schematic/x.kicad_sch'),
        netlist_path=Path('/p/proj/sim/x.cir'),
        status=SimulationStatus.NETLIST_READY,
    )
    assert sim.status is SimulationStatus.NETLIST_READY
    assert sim.netlist_path == Path('/p/proj/sim/x.cir')


def test_simulation_is_frozen() -> None:
    sim = Simulation(
        project_id=uuid4(),
        schematic_path=Path('/p/x.kicad_sch'),
    )
    with pytest.raises(ValidationError):
        sim.status = SimulationStatus.SIMULATED  # type: ignore[misc]


def test_simulation_result_with_op_values() -> None:
    result = SimulationResult(
        operating_points={'V(out)': 5.0, 'I(R1)': 0.001},
    )
    assert result.operating_points == {'V(out)': 5.0, 'I(R1)': 0.001}
    assert result.time_series is None
    assert result.ac_sweep is None


def test_simulation_result_with_time_series() -> None:
    ts = TimeSeries(
        time=(0.0, 1e-3, 2e-3),
        traces={'V(out)': (0.0, 0.5, 1.0)},
    )
    result = SimulationResult(time_series=ts)
    assert result.time_series is ts
    assert result.operating_points is None
    assert result.ac_sweep is None


def test_simulation_result_with_ac_sweep() -> None:
    ac = AcSweep(
        frequency=(1.0, 10.0, 100.0),
        traces_real={'V(out)': (1.0, 0.707, 0.0)},
        traces_imag={'V(out)': (0.0, -0.707, -1.0)},
    )
    result = SimulationResult(ac_sweep=ac)
    assert result.ac_sweep is ac
    assert result.operating_points is None
    assert result.time_series is None


def test_simulation_result_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        SimulationResult()


def test_simulation_result_rejects_multiple_branches() -> None:
    ts = TimeSeries(time=(0.0,), traces={'V(out)': (0.0,)})
    with pytest.raises(ValidationError):
        SimulationResult(
            operating_points={'V(out)': 1.0},
            time_series=ts,
        )


def test_simulation_result_is_frozen() -> None:
    result = SimulationResult(operating_points={'V(out)': 1.0})
    with pytest.raises(ValidationError):
        result.operating_points = {'a': 1.0}  # type: ignore[misc]


def test_time_series_construction() -> None:
    ts = TimeSeries(
        time=(0.0, 1e-3, 2e-3),
        traces={'V(out)': (0.0, 0.5, 1.0), 'V(in)': (1.0, 1.0, 1.0)},
    )
    assert ts.time == (0.0, 1e-3, 2e-3)
    assert ts.traces['V(out)'] == (0.0, 0.5, 1.0)


def test_time_series_rejects_length_mismatch() -> None:
    with pytest.raises(ValidationError):
        TimeSeries(
            time=(0.0, 1.0),
            traces={'V(out)': (0.0, 0.5, 1.0)},
        )


def test_time_series_rejects_empty_time() -> None:
    with pytest.raises(ValidationError):
        TimeSeries(time=(), traces={})


def test_time_series_is_frozen() -> None:
    ts = TimeSeries(time=(0.0,), traces={'V(out)': (0.0,)})
    with pytest.raises(ValidationError):
        ts.time = (1.0,)  # type: ignore[misc]


def test_ac_sweep_construction() -> None:
    ac = AcSweep(
        frequency=(1.0, 10.0, 100.0),
        traces_real={'V(out)': (1.0, 0.5, 0.0)},
        traces_imag={'V(out)': (0.0, -0.5, -1.0)},
    )
    assert ac.frequency == (1.0, 10.0, 100.0)
    assert ac.traces_real['V(out)'] == (1.0, 0.5, 0.0)
    assert ac.traces_imag['V(out)'] == (0.0, -0.5, -1.0)


def test_ac_sweep_rejects_length_mismatch_in_real() -> None:
    with pytest.raises(ValidationError):
        AcSweep(
            frequency=(1.0, 10.0),
            traces_real={'V(out)': (1.0,)},
            traces_imag={'V(out)': (0.0, 0.0)},
        )


def test_ac_sweep_rejects_traces_imag_missing_key() -> None:
    with pytest.raises(ValidationError):
        AcSweep(
            frequency=(1.0,),
            traces_real={'V(out)': (1.0,)},
            traces_imag={'V(in)': (0.0,)},
        )


def test_ac_sweep_rejects_empty_frequency() -> None:
    with pytest.raises(ValidationError):
        AcSweep(frequency=(), traces_real={}, traces_imag={})


def test_ac_sweep_is_frozen() -> None:
    ac = AcSweep(
        frequency=(1.0,),
        traces_real={'V(out)': (1.0,)},
        traces_imag={'V(out)': (0.0,)},
    )
    with pytest.raises(ValidationError):
        ac.frequency = (2.0,)  # type: ignore[misc]


# ---------- FourierAnalysis (T131 Phase B) ----------


def _tran_for_fundamental(freq_hz: float, periods: int = 10) -> TranAnalysis:
    t_stop = periods / freq_hz
    t_step = (1.0 / freq_hz) / 100.0
    return TranAnalysis(t_step=t_step, t_stop=t_stop)


def test_fourier_analysis_minimum_fields() -> None:
    four = FourierAnalysis(
        tran=_tran_for_fundamental(1000.0),
        fundamental_hz=1000.0,
        n_harmonics=10,
        signal='v(load)',
    )
    assert four.type == 'four'
    assert four.fundamental_hz == 1000.0
    assert four.n_harmonics == 10
    assert four.signal == 'v(load)'


def test_fourier_analysis_rejects_non_positive_fundamental() -> None:
    with pytest.raises(ValidationError):
        FourierAnalysis(
            tran=_tran_for_fundamental(1000.0),
            fundamental_hz=0.0,
            n_harmonics=10,
            signal='v(load)',
        )


def test_fourier_analysis_rejects_n_harmonics_below_two() -> None:
    with pytest.raises(ValidationError):
        FourierAnalysis(
            tran=_tran_for_fundamental(1000.0),
            fundamental_hz=1000.0,
            n_harmonics=1,
            signal='v(load)',
        )


def test_fourier_analysis_rejects_n_harmonics_above_limit() -> None:
    with pytest.raises(ValidationError):
        FourierAnalysis(
            tran=_tran_for_fundamental(1000.0),
            fundamental_hz=1000.0,
            n_harmonics=21,
            signal='v(load)',
        )


def test_fourier_analysis_rejects_empty_signal() -> None:
    with pytest.raises(ValidationError):
        FourierAnalysis(
            tran=_tran_for_fundamental(1000.0),
            fundamental_hz=1000.0,
            n_harmonics=10,
            signal='',
        )


def test_fourier_analysis_is_frozen() -> None:
    four = FourierAnalysis(
        tran=_tran_for_fundamental(1000.0),
        fundamental_hz=1000.0,
        n_harmonics=10,
        signal='v(load)',
    )
    with pytest.raises(ValidationError):
        four.fundamental_hz = 2000.0  # type: ignore[misc]


def test_harmonic_sample_minimum_fields() -> None:
    sample = HarmonicSample(
        n=2,
        frequency_hz=2000.0,
        magnitude=0.05,
        phase_deg=45.0,
        normalized=0.05,
    )
    assert sample.n == 2
    assert sample.frequency_hz == 2000.0


def test_harmonic_sample_rejects_negative_n() -> None:
    with pytest.raises(ValidationError):
        HarmonicSample(
            n=-1,
            frequency_hz=2000.0,
            magnitude=0.05,
            phase_deg=45.0,
            normalized=0.05,
        )


def test_harmonic_sample_rejects_negative_magnitude() -> None:
    with pytest.raises(ValidationError):
        HarmonicSample(
            n=2,
            frequency_hz=2000.0,
            magnitude=-1.0,
            phase_deg=0.0,
            normalized=0.5,
        )


def _make_harmonics(n_harmonics: int, fundamental_hz: float) -> tuple[HarmonicSample, ...]:
    return tuple(
        HarmonicSample(
            n=i,
            frequency_hz=i * fundamental_hz,
            magnitude=1.0 / (i + 1),
            phase_deg=0.0,
            normalized=1.0 / (i + 1),
        )
        for i in range(n_harmonics)
    )


def test_fourier_result_construction() -> None:
    result = FourierResult(
        fundamental_hz=1000.0,
        thd_percent=2.5,
        harmonics=_make_harmonics(10, 1000.0),
    )
    assert result.thd_percent == 2.5
    assert len(result.harmonics) == 10


def test_fourier_result_rejects_negative_thd() -> None:
    with pytest.raises(ValidationError):
        FourierResult(
            fundamental_hz=1000.0,
            thd_percent=-0.5,
            harmonics=_make_harmonics(10, 1000.0),
        )


def test_fourier_result_rejects_empty_harmonics() -> None:
    with pytest.raises(ValidationError):
        FourierResult(
            fundamental_hz=1000.0,
            thd_percent=2.5,
            harmonics=(),
        )


def test_fourier_result_is_frozen() -> None:
    result = FourierResult(
        fundamental_hz=1000.0,
        thd_percent=2.5,
        harmonics=_make_harmonics(10, 1000.0),
    )
    with pytest.raises(ValidationError):
        result.thd_percent = 5.0  # type: ignore[misc]


def test_simulation_result_with_fourier_branch() -> None:
    fourier = FourierResult(
        fundamental_hz=1000.0,
        thd_percent=2.5,
        harmonics=_make_harmonics(10, 1000.0),
    )
    result = SimulationResult(fourier_result=fourier)
    assert result.fourier_result is fourier
    assert result.operating_points is None
    assert result.time_series is None
    assert result.ac_sweep is None


def test_simulation_result_rejects_multiple_branches_with_fourier() -> None:
    fourier = FourierResult(
        fundamental_hz=1000.0,
        thd_percent=2.5,
        harmonics=_make_harmonics(10, 1000.0),
    )
    with pytest.raises(ValidationError):
        SimulationResult(
            operating_points={'V(out)': 1.0},
            fourier_result=fourier,
        )
