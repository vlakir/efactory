"""Unit tests для конвертеров `RawWaveform` → `TimeSeries`/`AcSweep` (T191)."""

from __future__ import annotations

import pytest

from domain.raw_waveform import (
    RawWaveform,
    WaveformAnalysisType,
    waveform_to_ac_sweep,
    waveform_to_dc_sweep,
    waveform_to_time_series,
)
from domain.simulation import AcSweep, DcSweep, TimeSeries


def _tran_waveform() -> RawWaveform:
    return RawWaveform(
        timestamp='2026-06-06T01:30:00Z',
        analysis_type=WaveformAnalysisType.TRAN,
        source_netlist='amp.cir',
        x_axis_name='time',
        x_axis=(0.0, 1e-6, 2e-6),
        traces={'v(out)': (0.0, 0.5, 1.0)},
    )


def _ac_waveform() -> RawWaveform:
    return RawWaveform(
        timestamp='2026-06-06T01:30:00Z',
        analysis_type=WaveformAnalysisType.AC,
        source_netlist='amp.cir',
        x_axis_name='frequency',
        x_axis=(10.0, 100.0, 1000.0),
        traces={'v(out)': (1.0, 0.9, 0.5)},
        traces_imag={'v(out)': (0.0, 0.1, 0.3)},
    )


def test_tran_to_time_series() -> None:
    ts = waveform_to_time_series(_tran_waveform())
    assert isinstance(ts, TimeSeries)
    assert ts.time == (0.0, 1e-6, 2e-6)
    assert ts.traces == {'v(out)': (0.0, 0.5, 1.0)}


def test_dc_to_time_series_rejected() -> None:
    """DC теперь использует свой конвертер (T188)."""
    wf = _tran_waveform().model_copy(
        update={'analysis_type': WaveformAnalysisType.DC, 'x_axis_name': 'V1'}
    )
    with pytest.raises(ValueError, match='expected TRAN'):
        waveform_to_time_series(wf)


def test_ac_to_time_series_rejected() -> None:
    with pytest.raises(ValueError, match='expected TRAN'):
        waveform_to_time_series(_ac_waveform())


def test_dc_to_dc_sweep() -> None:
    wf = _tran_waveform().model_copy(
        update={'analysis_type': WaveformAnalysisType.DC, 'x_axis_name': 'V1'}
    )
    dc = waveform_to_dc_sweep(wf)
    assert isinstance(dc, DcSweep)
    assert dc.sweep_variable == 'V1'
    assert dc.sweep_values == (0.0, 1e-6, 2e-6)


def test_tran_to_dc_sweep_rejected() -> None:
    with pytest.raises(ValueError, match='expected DC waveform'):
        waveform_to_dc_sweep(_tran_waveform())


def test_ac_to_ac_sweep() -> None:
    ac = waveform_to_ac_sweep(_ac_waveform())
    assert isinstance(ac, AcSweep)
    assert ac.frequency == (10.0, 100.0, 1000.0)
    assert ac.traces_real == {'v(out)': (1.0, 0.9, 0.5)}
    assert ac.traces_imag == {'v(out)': (0.0, 0.1, 0.3)}


def test_tran_to_ac_sweep_rejected() -> None:
    with pytest.raises(ValueError, match='expected AC waveform'):
        waveform_to_ac_sweep(_tran_waveform())
