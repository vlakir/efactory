"""Renderer для bridge edit-and-resim (T021 Phase B)."""

from __future__ import annotations

import json

import pytest

from adapters.inbound.cli.edit_and_resim_renderer import (
    render_edit_and_resim_json,
    render_edit_and_resim_text,
)
from application.edit_and_resim_with_delta import EditAndResimReport
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


def _gain(value_db: float = 20.0) -> GainMeasurement:
    return GainMeasurement(
        value_db=value_db,
        value_linear=10 ** (value_db / 20),
        frequency_hz=1000.0,
        mode='small',
        input_signal='v(in)',
        output_signal='v(load)',
        v_in_peak=None,
    )


def _bandwidth(bandwidth_hz: float = 19980.0) -> BandwidthMeasurement:
    return BandwidthMeasurement(
        f_low_hz=20.0,
        f_high_hz=20.0 + bandwidth_hz,
        bandwidth_hz=bandwidth_hz,
        ref_db=-3.0,
        midpoint_db=20.0,
        midpoint_source='auto',
        passband_signal='v(load)',
        input_signal='v(in)',
    )


def _thd(thd_percent: float = 2.5) -> ThdMeasurement:
    return ThdMeasurement(
        thd_percent=thd_percent,
        fundamental_hz=1000.0,
        v_in_peak=0.1,
        measured_power_w=0.8,
        dominant_harmonic_n=2,
        dominant_harmonic_percent=thd_percent * 0.9,
        signal='v(load)',
        n_harmonics=10,
    )


# -------------------------------------------------------------------- Text renderer ----


def test_text_renderer_includes_metric_name_and_columns() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[
            GainDelta.from_measurements(before=_gain(20.0), after=_gain(23.0)),
        ],
        project='demo',
    )
    out = render_edit_and_resim_text(report)
    assert 'gain' in out
    assert 'value_db' in out
    assert '20' in out
    assert '23' in out
    assert '+3' in out or '3.00' in out
    assert '%' in out


def test_text_renderer_multiple_deltas_each_present() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R5', '2k')],
        deltas=[
            GainDelta.from_measurements(before=_gain(20.0), after=_gain(21.0)),
            BandwidthDelta.from_measurements(
                before=_bandwidth(19980.0),
                after=_bandwidth(39980.0),
            ),
            ThdDelta.from_measurements(before=_thd(2.5), after=_thd(1.0)),
        ],
    )
    out = render_edit_and_resim_text(report)
    assert 'gain' in out
    assert 'bandwidth' in out
    assert 'thd' in out
    assert 'value_db' in out
    assert 'bandwidth_hz' in out
    assert 'thd_percent' in out


def test_text_renderer_zero_before_shows_dash_for_relative() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[GainDelta.from_measurements(before=_gain(0.0), after=_gain(2.0))],
    )
    out = render_edit_and_resim_text(report)
    # delta_relative_percent — None при before=0; renderer показывает «—»
    assert '—' in out


def test_text_renderer_failed_after_shows_failed_marker_and_reason() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[
            GainDelta.from_failed_after(
                before=_gain(20.0),
                reason='ngspice ac sweep diverged',
            ),
        ],
    )
    out = render_edit_and_resim_text(report)
    assert 'FAILED' in out or 'failed' in out
    assert 'ngspice ac sweep diverged' in out


def test_text_renderer_lists_edits_at_top() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k'), ('C3', '470n')],
        deltas=[GainDelta.from_measurements(before=_gain(), after=_gain(22.0))],
    )
    out = render_edit_and_resim_text(report)
    assert 'R1' in out
    assert '10k' in out
    assert 'C3' in out
    assert '470n' in out


def test_text_renderer_includes_project_and_schematic_when_present() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[GainDelta.from_measurements(before=_gain(), after=_gain(22.0))],
        project='my-amp',
    )
    out = render_edit_and_resim_text(report)
    assert 'my-amp' in out
    assert 'demo.kicad_sch' in out


# -------------------------------------------------------------------- JSON renderer ----


def test_json_renderer_round_trip_through_pydantic() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[GainDelta.from_measurements(before=_gain(20.0), after=_gain(22.0))],
        project='demo',
    )
    blob = render_edit_and_resim_json(report)
    restored = EditAndResimReport.model_validate_json(blob)
    assert restored == report


def test_json_renderer_includes_full_before_after_measurements() -> None:
    """Q-H → b: JSON содержит полные before/after measurement-объекты."""
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[GainDelta.from_measurements(before=_gain(20.0), after=_gain(22.0))],
    )
    blob = render_edit_and_resim_json(report)
    data = json.loads(blob)
    delta_json = data['deltas'][0]
    assert delta_json['before']['value_db'] == pytest.approx(20.0)
    assert delta_json['before']['frequency_hz'] == pytest.approx(1000.0)
    assert delta_json['after']['value_db'] == pytest.approx(22.0)
    assert delta_json['delta_absolute'] == pytest.approx(2.0)
    assert delta_json['delta_relative_percent'] == pytest.approx(10.0)


def test_json_renderer_failed_after_serializes_null() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[
            GainDelta.from_failed_after(before=_gain(), reason='boom'),
        ],
    )
    blob = render_edit_and_resim_json(report)
    data = json.loads(blob)
    delta_json = data['deltas'][0]
    assert delta_json['after'] is None
    assert delta_json['delta_absolute'] is None
    assert delta_json['failed_reason'] == 'boom'


def test_json_renderer_pretty_printed() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R1', '10k')],
        deltas=[GainDelta.from_measurements(before=_gain(), after=_gain(22.0))],
    )
    blob = render_edit_and_resim_json(report)
    # indent=2 → каждая нетривиальная пара ключ/значение на своей строке
    assert blob.count('\n') > 5
