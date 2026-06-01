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
from domain.phase_margin import (
    PhaseMarginDelta,
    PhaseMarginMeasurement,
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


def _phase_margin(
    margin_deg: float = 65.0,
    crossover_hz: float = 12_000.0,
) -> PhaseMarginMeasurement:
    # stability class derived из margin_deg (high > 60°, adequate > 45°, …).
    if margin_deg > 60.0:
        cls = 'high'
    elif margin_deg > 45.0:
        cls = 'adequate'
    elif margin_deg > 30.0:
        cls = 'marginal'
    else:
        cls = 'risky'
    return PhaseMarginMeasurement(
        margin_deg=margin_deg,
        crossover_hz=crossover_hz,
        measured_at_node='in_neg',
        injection_method='middlebrook_voltage',
        stability_class=cls,  # type: ignore[arg-type]
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


# ---------------------------------------------- PhaseMarginDelta (T153 B.7) ----


def test_text_renderer_phase_margin_includes_margin_and_crossover() -> None:
    """Основная строка — margin_deg; sub-row — crossover before → after."""
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R_fb', '47k')],
        deltas=[
            PhaseMarginDelta.from_measurements(
                before=_phase_margin(margin_deg=65.0, crossover_hz=12_000.0),
                after=_phase_margin(margin_deg=48.0, crossover_hz=10_500.0),
            ),
        ],
    )
    out = render_edit_and_resim_text(report)
    assert 'phase-margin' in out
    assert 'margin_deg' in out
    assert '65' in out
    assert '48' in out
    assert 'crossover' in out
    assert '12' in out  # crossover before
    assert '10' in out  # crossover after
    # Δ = -17 (degradation), Δ% ≈ -26.15%
    assert '-17' in out
    assert '-26' in out


def test_text_renderer_phase_margin_failed_after_shows_reason() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R_fb', '47k')],
        deltas=[
            PhaseMarginDelta.from_failed_after(
                before=_phase_margin(),
                reason='AutoDetectRejectedError: confidence too low',
            ),
        ],
    )
    out = render_edit_and_resim_text(report)
    assert 'phase-margin' in out
    assert 'FAILED' in out
    assert 'AutoDetectRejectedError' in out


def test_json_renderer_phase_margin_full_round_trip() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R_fb', '47k')],
        deltas=[
            PhaseMarginDelta.from_measurements(
                before=_phase_margin(margin_deg=65.0, crossover_hz=12_000.0),
                after=_phase_margin(margin_deg=48.0, crossover_hz=10_500.0),
            ),
        ],
        project='demo',
    )
    blob = render_edit_and_resim_json(report)
    restored = EditAndResimReport.model_validate_json(blob)
    assert restored == report


def test_json_renderer_phase_margin_includes_full_measurement() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R_fb', '47k')],
        deltas=[
            PhaseMarginDelta.from_measurements(
                before=_phase_margin(margin_deg=65.0, crossover_hz=12_000.0),
                after=_phase_margin(margin_deg=48.0, crossover_hz=10_500.0),
            ),
        ],
    )
    blob = render_edit_and_resim_json(report)
    data = json.loads(blob)
    delta_json = data['deltas'][0]
    assert delta_json['metric_field'] == 'margin_deg'
    assert delta_json['before']['margin_deg'] == pytest.approx(65.0)
    assert delta_json['before']['crossover_hz'] == pytest.approx(12_000.0)
    assert delta_json['before']['injection_method'] == 'middlebrook_voltage'
    assert delta_json['after']['margin_deg'] == pytest.approx(48.0)
    assert delta_json['delta_absolute'] == pytest.approx(-17.0)


def test_text_renderer_phase_margin_combined_with_gain() -> None:
    report = EditAndResimReport(
        schematic='/p/demo.kicad_sch',
        edits=[('R_fb', '47k')],
        deltas=[
            GainDelta.from_measurements(before=_gain(20.0), after=_gain(22.0)),
            PhaseMarginDelta.from_measurements(
                before=_phase_margin(margin_deg=65.0),
                after=_phase_margin(margin_deg=55.0),
            ),
        ],
    )
    out = render_edit_and_resim_text(report)
    assert 'gain' in out
    assert 'phase-margin' in out
    assert 'value_db' in out
    assert 'margin_deg' in out
