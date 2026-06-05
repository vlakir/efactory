"""Unit tests для domain VO `RawWaveform` (T190)."""

from __future__ import annotations

import pytest

from domain.raw_waveform import (
    RAW_WAVEFORM_SCHEMA_VERSION,
    RawWaveform,
    WaveformAnalysisType,
)


def _tran_kwargs() -> dict[str, object]:
    return {
        'timestamp': '2026-06-06T01:30:00Z',
        'analysis_type': WaveformAnalysisType.TRAN,
        'source_netlist': 'amp.cir',
        'x_axis_name': 'time',
        'x_axis': (0.0, 1e-6, 2e-6),
        'traces': {'v(out)': (0.0, 0.1, 0.2)},
    }


def _ac_kwargs() -> dict[str, object]:
    return {
        'timestamp': '2026-06-06T01:30:00Z',
        'analysis_type': WaveformAnalysisType.AC,
        'source_netlist': 'amp.cir',
        'x_axis_name': 'frequency',
        'x_axis': (10.0, 100.0, 1000.0),
        'traces': {'v(out)': (1.0, 0.9, 0.5)},
        'traces_imag': {'v(out)': (0.0, 0.1, 0.3)},
    }


def test_schema_version_constant() -> None:
    waveform = RawWaveform(**_tran_kwargs())  # type: ignore[arg-type]
    assert waveform.schema_version == RAW_WAVEFORM_SCHEMA_VERSION == 1


def test_tran_minimal_ok() -> None:
    waveform = RawWaveform(**_tran_kwargs())  # type: ignore[arg-type]
    assert waveform.analysis_type == WaveformAnalysisType.TRAN
    assert waveform.traces_imag is None


def test_ac_requires_traces_imag() -> None:
    kwargs = _ac_kwargs()
    kwargs.pop('traces_imag')
    with pytest.raises(ValueError, match='AC analysis requires traces_imag'):
        RawWaveform(**kwargs)  # type: ignore[arg-type]


def test_ac_traces_imag_keys_must_match() -> None:
    kwargs = _ac_kwargs()
    kwargs['traces_imag'] = {'v(in)': (0.0, 0.0, 0.0)}
    with pytest.raises(ValueError, match='AC traces_imag keys'):
        RawWaveform(**kwargs)  # type: ignore[arg-type]


def test_tran_rejects_traces_imag() -> None:
    kwargs = _tran_kwargs()
    kwargs['traces_imag'] = {'v(out)': (0.0, 0.0, 0.0)}
    with pytest.raises(ValueError, match='traces_imag must be None'):
        RawWaveform(**kwargs)  # type: ignore[arg-type]


def test_trace_length_mismatch_rejected() -> None:
    kwargs = _tran_kwargs()
    kwargs['traces'] = {'v(out)': (0.0, 0.1)}  # 2 samples, x_axis has 3
    with pytest.raises(ValueError, match='samples but x_axis has 3'):
        RawWaveform(**kwargs)  # type: ignore[arg-type]


def test_ac_traces_imag_length_mismatch_rejected() -> None:
    kwargs = _ac_kwargs()
    kwargs['traces_imag'] = {'v(out)': (0.0, 0.0)}  # 2 vs 3
    with pytest.raises(ValueError, match='traces_imag'):
        RawWaveform(**kwargs)  # type: ignore[arg-type]


def test_dc_real_mode_ok() -> None:
    kwargs = _tran_kwargs()
    kwargs['analysis_type'] = WaveformAnalysisType.DC
    kwargs['x_axis_name'] = 'V1'
    waveform = RawWaveform(**kwargs)  # type: ignore[arg-type]
    assert waveform.analysis_type == WaveformAnalysisType.DC
    assert waveform.traces_imag is None


def test_empty_x_axis_rejected() -> None:
    kwargs = _tran_kwargs()
    kwargs['x_axis'] = ()
    kwargs['traces'] = {'v(out)': ()}
    with pytest.raises(ValueError):
        RawWaveform(**kwargs)  # type: ignore[arg-type]


def test_frozen_immutable() -> None:
    waveform = RawWaveform(**_tran_kwargs())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match='[Ff]rozen|immutable'):
        waveform.timestamp = '2026-01-01T00:00:00Z'  # type: ignore[misc]


def test_roundtrip_model_dump_validate() -> None:
    original = RawWaveform(**_ac_kwargs())  # type: ignore[arg-type]
    restored = RawWaveform.model_validate(original.model_dump(mode='json'))
    assert restored == original
