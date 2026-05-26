"""Domain: GainMeasurement, BandwidthMeasurement, ThdMeasurement (T023)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.measurement import (
    BandwidthMeasurement,
    GainMeasurement,
    ThdMeasurement,
)
from domain.sim_results import AnalysisType


def _make_gain(**overrides: object) -> GainMeasurement:
    defaults: dict[str, object] = {
        'value_db': 20.0,
        'value_linear': 10.0,
        'frequency_hz': 1000.0,
        'mode': 'small',
        'input_signal': 'v(in)',
        'output_signal': 'v(load)',
    }
    defaults.update(overrides)
    return GainMeasurement(**defaults)  # type: ignore[arg-type]


def _make_bandwidth(**overrides: object) -> BandwidthMeasurement:
    defaults: dict[str, object] = {
        'f_low_hz': 20.0,
        'f_high_hz': 25000.0,
        'bandwidth_hz': 25000.0 - 20.0,
        'ref_db': -3.0,
        'midpoint_db': 20.0,
        'midpoint_source': 'auto',
        'passband_signal': 'v(load)',
        'input_signal': 'v(in)',
    }
    defaults.update(overrides)
    return BandwidthMeasurement(**defaults)  # type: ignore[arg-type]


def _make_thd(**overrides: object) -> ThdMeasurement:
    defaults: dict[str, object] = {
        'thd_percent': 2.5,
        'fundamental_hz': 1000.0,
        'v_in_peak': 0.1,
        'measured_power_w': 0.8,
        'dominant_harmonic_n': 2,
        'dominant_harmonic_percent': 2.0,
        'signal': 'v(load)',
        'n_harmonics': 10,
    }
    defaults.update(overrides)
    return ThdMeasurement(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------- Gain ----


def test_gain_minimum_fields_small_mode() -> None:
    g = _make_gain()
    assert g.value_db == 20.0
    assert g.value_linear == 10.0
    assert g.frequency_hz == 1000.0
    assert g.mode == 'small'
    assert g.input_signal == 'v(in)'
    assert g.output_signal == 'v(load)'
    assert g.v_in_peak is None


def test_gain_large_mode_with_v_in_peak() -> None:
    g = _make_gain(mode='large', v_in_peak=0.1)
    assert g.mode == 'large'
    assert g.v_in_peak == 0.1


def test_gain_large_mode_requires_v_in_peak() -> None:
    with pytest.raises(ValidationError, match='v_in_peak required'):
        _make_gain(mode='large')


def test_gain_small_mode_allows_v_in_peak_omitted() -> None:
    g = _make_gain(mode='small', v_in_peak=None)
    assert g.v_in_peak is None


def test_gain_value_db_can_be_negative() -> None:
    """Attenuator: gain < 1 → value_db < 0."""
    g = _make_gain(value_db=-6.0, value_linear=0.5)
    assert g.value_db == -6.0
    assert g.value_linear == 0.5


def test_gain_frequency_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_gain(frequency_hz=0.0)
    with pytest.raises(ValidationError):
        _make_gain(frequency_hz=-100.0)


def test_gain_value_linear_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_gain(value_linear=0.0)
    with pytest.raises(ValidationError):
        _make_gain(value_linear=-1.0)


def test_gain_input_signal_non_empty() -> None:
    with pytest.raises(ValidationError):
        _make_gain(input_signal='')


def test_gain_output_signal_non_empty() -> None:
    with pytest.raises(ValidationError):
        _make_gain(output_signal='')


def test_gain_mode_validates() -> None:
    with pytest.raises(ValidationError):
        _make_gain(mode='medium')


def test_gain_is_frozen() -> None:
    g = _make_gain()
    with pytest.raises(ValidationError):
        g.value_db = 30.0  # type: ignore[misc]


def test_gain_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        _make_gain(extra_unknown_field=1.0)


# --------------------------------------------------------- Bandwidth ----


def test_bandwidth_minimum_fields() -> None:
    bw = _make_bandwidth()
    assert bw.f_low_hz == 20.0
    assert bw.f_high_hz == 25000.0
    assert bw.bandwidth_hz == 25000.0 - 20.0
    assert bw.ref_db == -3.0
    assert bw.midpoint_db == 20.0
    assert bw.midpoint_source == 'auto'
    assert bw.ref_freq_hz is None
    assert bw.passband_signal == 'v(load)'
    assert bw.input_signal == 'v(in)'


def test_bandwidth_ref_freq_mode() -> None:
    bw = _make_bandwidth(midpoint_source='ref_freq', ref_freq_hz=1000.0)
    assert bw.midpoint_source == 'ref_freq'
    assert bw.ref_freq_hz == 1000.0


def test_bandwidth_ref_freq_required_when_source_is_ref_freq() -> None:
    with pytest.raises(ValidationError, match='ref_freq_hz'):
        _make_bandwidth(midpoint_source='ref_freq')


def test_bandwidth_f_high_must_exceed_f_low() -> None:
    """model_validator ловит f_high < f_low (bandwidth_hz сам по себе
    положителен — иначе ловит Field(gt=0), не наш cross-field validator).
    """
    with pytest.raises(ValidationError, match='f_high_hz'):
        _make_bandwidth(f_low_hz=1000.0, f_high_hz=500.0, bandwidth_hz=1.0)


def test_bandwidth_hz_must_be_positive() -> None:
    """Field(gt=0) — атомарная защита (например, f_high == f_low → 0)."""
    with pytest.raises(ValidationError):
        _make_bandwidth(bandwidth_hz=0.0)
    with pytest.raises(ValidationError):
        _make_bandwidth(bandwidth_hz=-100.0)


def test_bandwidth_hz_must_match_endpoints() -> None:
    with pytest.raises(ValidationError, match='bandwidth_hz'):
        _make_bandwidth(f_low_hz=20.0, f_high_hz=25000.0, bandwidth_hz=99999.0)


def test_bandwidth_frequencies_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_bandwidth(f_low_hz=0.0)
    with pytest.raises(ValidationError):
        _make_bandwidth(f_low_hz=-10.0)


def test_bandwidth_midpoint_source_validates() -> None:
    with pytest.raises(ValidationError):
        _make_bandwidth(midpoint_source='midpoint')


def test_bandwidth_passband_signal_non_empty() -> None:
    with pytest.raises(ValidationError):
        _make_bandwidth(passband_signal='')


def test_bandwidth_is_frozen() -> None:
    bw = _make_bandwidth()
    with pytest.raises(ValidationError):
        bw.f_low_hz = 30.0  # type: ignore[misc]


def test_bandwidth_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        _make_bandwidth(extra_unknown_field=1.0)


# --------------------------------------------------------------- THD ----


def test_thd_minimum_fields() -> None:
    t = _make_thd()
    assert t.thd_percent == 2.5
    assert t.fundamental_hz == 1000.0
    assert t.v_in_peak == 0.1
    assert t.measured_power_w == 0.8
    assert t.dominant_harmonic_n == 2
    assert t.dominant_harmonic_percent == 2.0
    assert t.signal == 'v(load)'
    assert t.n_harmonics == 10


def test_thd_percent_can_be_zero() -> None:
    """Pure linear circuit → THD = 0%."""
    t = _make_thd(thd_percent=0.0, dominant_harmonic_percent=0.0)
    assert t.thd_percent == 0.0


def test_thd_percent_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        _make_thd(thd_percent=-0.5)


def test_thd_fundamental_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_thd(fundamental_hz=0.0)
    with pytest.raises(ValidationError):
        _make_thd(fundamental_hz=-1000.0)


def test_thd_v_in_peak_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_thd(v_in_peak=0.0)
    with pytest.raises(ValidationError):
        _make_thd(v_in_peak=-0.1)


def test_thd_measured_power_can_be_zero() -> None:
    """Open-load или disconnected output: 0 W в нагрузке — допустимо."""
    t = _make_thd(measured_power_w=0.0)
    assert t.measured_power_w == 0.0


def test_thd_measured_power_non_negative() -> None:
    with pytest.raises(ValidationError):
        _make_thd(measured_power_w=-0.1)


def test_thd_dominant_harmonic_at_least_2() -> None:
    """DC=0, fundamental=1 — оба исключены; first real harmonic = 2."""
    with pytest.raises(ValidationError):
        _make_thd(dominant_harmonic_n=1)
    with pytest.raises(ValidationError):
        _make_thd(dominant_harmonic_n=0)


def test_thd_n_harmonics_range() -> None:
    with pytest.raises(ValidationError):
        _make_thd(n_harmonics=2)
    with pytest.raises(ValidationError):
        _make_thd(n_harmonics=21)
    # Boundary values OK:
    assert _make_thd(n_harmonics=3).n_harmonics == 3
    assert _make_thd(n_harmonics=20).n_harmonics == 20


def test_thd_signal_non_empty() -> None:
    with pytest.raises(ValidationError):
        _make_thd(signal='')


def test_thd_is_frozen() -> None:
    t = _make_thd()
    with pytest.raises(ValidationError):
        t.thd_percent = 5.0  # type: ignore[misc]


def test_thd_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        _make_thd(extra_unknown_field=1.0)


# ----------------------------------------------- AnalysisType extension ----


def test_analysis_type_includes_gain_bandwidth() -> None:
    """T023 extension: GAIN + BANDWIDTH добавлены к существующему enum'у."""
    assert AnalysisType.GAIN == 'gain'
    assert AnalysisType.BANDWIDTH == 'bandwidth'


def test_analysis_type_thd_unchanged() -> None:
    """THD уже было в T016 — extension не сломала."""
    assert AnalysisType.THD == 'thd'
