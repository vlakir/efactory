"""Domain: GainDelta, BandwidthDelta, ThdDelta (T021)."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from domain.measurement import (
    BandwidthMeasurement,
    GainMeasurement,
    ThdMeasurement,
)
from domain.measurement_delta import (
    BandwidthDelta,
    GainDelta,
    ThdDelta,
)

if TYPE_CHECKING:
    pass


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


# ---------------------------------------------------------------- GainDelta ----


def test_gain_delta_from_measurements_positive_change() -> None:
    before = _make_gain(value_db=20.0)
    after = _make_gain(value_db=23.0)
    delta = GainDelta.from_measurements(before=before, after=after)
    assert delta.before is before
    assert delta.after is after
    assert delta.delta_absolute == pytest.approx(3.0)
    assert delta.delta_relative_percent == pytest.approx(15.0)
    assert delta.failed_reason is None
    assert delta.metric_field == 'value_db'


def test_gain_delta_from_measurements_negative_change() -> None:
    before = _make_gain(value_db=20.0)
    after = _make_gain(value_db=18.5)
    delta = GainDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(-1.5)
    assert delta.delta_relative_percent == pytest.approx(-7.5)


def test_gain_delta_from_measurements_zero_before_yields_none_relative() -> None:
    before = _make_gain(value_db=0.0)
    after = _make_gain(value_db=2.0)
    delta = GainDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(2.0)
    assert delta.delta_relative_percent is None


def test_gain_delta_from_failed_after_sets_failed_reason_and_nones() -> None:
    before = _make_gain()
    delta = GainDelta.from_failed_after(before=before, reason='ngspice timeout')
    assert delta.before is before
    assert delta.after is None
    assert delta.delta_absolute is None
    assert delta.delta_relative_percent is None
    assert delta.failed_reason == 'ngspice timeout'


def test_gain_delta_after_none_with_delta_absolute_set_raises() -> None:
    before = _make_gain()
    with pytest.raises(
        ValidationError,
        match='delta_absolute must be None when after is None',
    ):
        GainDelta(
            before=before,
            after=None,
            delta_absolute=1.0,
            delta_relative_percent=None,
            failed_reason='boom',
        )


def test_gain_delta_after_none_with_failed_reason_empty_raises() -> None:
    before = _make_gain()
    with pytest.raises(ValidationError, match='failed_reason'):
        GainDelta(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=None,
        )


def test_gain_delta_after_set_with_failed_reason_raises() -> None:
    before = _make_gain(value_db=20.0)
    after = _make_gain(value_db=22.0)
    with pytest.raises(ValidationError, match='failed_reason'):
        GainDelta(
            before=before,
            after=after,
            delta_absolute=2.0,
            delta_relative_percent=10.0,
            failed_reason='shouldnt be set',
        )


def test_gain_delta_after_set_with_delta_absolute_none_raises() -> None:
    before = _make_gain()
    after = _make_gain()
    with pytest.raises(
        ValidationError,
        match='delta_absolute must be set when after is set',
    ):
        GainDelta(
            before=before,
            after=after,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=None,
        )


def test_gain_delta_is_frozen() -> None:
    before = _make_gain()
    after = _make_gain(value_db=22.0)
    delta = GainDelta.from_measurements(before=before, after=after)
    with pytest.raises(ValidationError):
        delta.delta_absolute = 99.0  # type: ignore[misc]


def test_gain_delta_json_round_trip() -> None:
    before = _make_gain(value_db=10.0)
    after = _make_gain(value_db=12.0)
    delta = GainDelta.from_measurements(before=before, after=after)
    blob = delta.model_dump_json()
    restored = GainDelta.model_validate_json(blob)
    assert restored == delta


def test_gain_delta_failed_json_round_trip() -> None:
    before = _make_gain()
    delta = GainDelta.from_failed_after(before=before, reason='converge fail')
    blob = delta.model_dump_json()
    restored = GainDelta.model_validate_json(blob)
    assert restored == delta
    assert json.loads(blob)['failed_reason'] == 'converge fail'


# ------------------------------------------------------------ BandwidthDelta ----


def test_bandwidth_delta_from_measurements_widens() -> None:
    before = _make_bandwidth(f_low_hz=20.0, f_high_hz=20000.0, bandwidth_hz=19980.0)
    after = _make_bandwidth(f_low_hz=20.0, f_high_hz=40000.0, bandwidth_hz=39980.0)
    delta = BandwidthDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(20000.0)
    assert delta.delta_relative_percent == pytest.approx(
        (20000.0 / 19980.0) * 100.0,
    )
    assert delta.metric_field == 'bandwidth_hz'


def test_bandwidth_delta_narrows_negative() -> None:
    before = _make_bandwidth(f_low_hz=20.0, f_high_hz=20000.0, bandwidth_hz=19980.0)
    after = _make_bandwidth(f_low_hz=200.0, f_high_hz=10000.0, bandwidth_hz=9800.0)
    delta = BandwidthDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute < 0


def test_bandwidth_delta_from_failed_after() -> None:
    before = _make_bandwidth()
    delta = BandwidthDelta.from_failed_after(
        before=before,
        reason='ngspice ac sweep diverged',
    )
    assert delta.after is None
    assert delta.failed_reason == 'ngspice ac sweep diverged'


# ------------------------------------------------------------------ ThdDelta ----


def test_thd_delta_from_measurements_improves_lower_better() -> None:
    before = _make_thd(thd_percent=2.5)
    after = _make_thd(thd_percent=1.0)
    delta = ThdDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(-1.5)
    assert delta.delta_relative_percent == pytest.approx(-60.0)
    assert delta.metric_field == 'thd_percent'


def test_thd_delta_zero_before_relative_none() -> None:
    before = _make_thd(thd_percent=0.0)
    after = _make_thd(thd_percent=0.5)
    delta = ThdDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(0.5)
    assert delta.delta_relative_percent is None


def test_thd_delta_failed_after() -> None:
    before = _make_thd()
    delta = ThdDelta.from_failed_after(before=before, reason='fourier no peak')
    assert delta.after is None
    assert delta.delta_absolute is None
    assert delta.failed_reason == 'fourier no peak'


# -------------------------------------------------- Type hygiene / forbid extra ----


def test_gain_delta_forbids_extra_fields() -> None:
    before = _make_gain()
    after = _make_gain()
    with pytest.raises(ValidationError):
        GainDelta(
            before=before,
            after=after,
            delta_absolute=0.0,
            delta_relative_percent=0.0,
            failed_reason=None,
            unexpected_field='nope',  # type: ignore[call-arg]
        )


def test_relative_percent_not_nan() -> None:
    """delta_relative_percent — float | None, нельзя положить NaN."""
    before = _make_gain()
    after = _make_gain()
    with pytest.raises(ValidationError, match='delta_relative_percent.*NaN'):
        GainDelta(
            before=before,
            after=after,
            delta_absolute=0.0,
            delta_relative_percent=math.nan,
            failed_reason=None,
        )
