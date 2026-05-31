"""Domain: PhaseMarginMeasurement, PhaseMarginDelta, AutoDetectInfo,
FeedbackCycle (T153 Phase B.1)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from domain.phase_margin import (
    AutoDetectInfo,
    FeedbackCycle,
    PhaseMarginDelta,
    PhaseMarginMeasurement,
)


def _make_measurement(**overrides: object) -> PhaseMarginMeasurement:
    defaults: dict[str, object] = {
        'margin_deg': 55.0,
        'crossover_hz': 12_500.0,
        'measured_at_node': '/fb_node',
        'injection_method': 'middlebrook_voltage',
        'stability_class': 'adequate',
    }
    defaults.update(overrides)
    return PhaseMarginMeasurement(**defaults)  # type: ignore[arg-type]


# -------------------------------------------- PhaseMarginMeasurement happy ----


def test_measurement_minimal_happy_path() -> None:
    m = _make_measurement()
    assert m.margin_deg == pytest.approx(55.0)
    assert m.crossover_hz == pytest.approx(12_500.0)
    assert m.measured_at_node == '/fb_node'
    assert m.injection_method == 'middlebrook_voltage'
    assert m.stability_class == 'adequate'
    # дефолты optional полей
    assert m.gain_margin_db is None
    assert m.phase_crossover_hz is None
    assert m.extra_crossovers_hz == ()
    assert m.sweep_dataset is None
    assert m.auto_detect_info is None


def test_measurement_full_payload_happy() -> None:
    auto = AutoDetectInfo(
        chosen_node='/fb_node',
        chosen_element_ref='C_fb_block',
        confidence=0.85,
        alternatives=(('/out', 'R_load', 0.6), ('/cathode', 'C_k', 0.4)),
        algorithm_notes='single dominant cycle; passive feedback path',
    )
    m = _make_measurement(
        gain_margin_db=12.0,
        phase_crossover_hz=85_000.0,
        extra_crossovers_hz=(8_000.0, 120_000.0),
        auto_detect_info=auto,
    )
    assert m.gain_margin_db == pytest.approx(12.0)
    assert m.phase_crossover_hz == pytest.approx(85_000.0)
    assert m.extra_crossovers_hz == (8_000.0, 120_000.0)
    assert m.auto_detect_info is auto


def test_measurement_is_frozen() -> None:
    m = _make_measurement()
    with pytest.raises(ValidationError):
        m.margin_deg = 30.0  # type: ignore[misc]


# -------------------------------------- PhaseMarginMeasurement validators ----


@pytest.mark.parametrize('bad', [-181.0, 361.0])
def test_measurement_margin_deg_out_of_sanity_range_rejected(bad: float) -> None:
    with pytest.raises(ValidationError, match='margin_deg'):
        _make_measurement(margin_deg=bad, stability_class='risky')


@pytest.mark.parametrize('bad', [0.0, -1.0])
def test_measurement_crossover_hz_must_be_positive(bad: float) -> None:
    with pytest.raises(ValidationError, match='crossover_hz'):
        _make_measurement(crossover_hz=bad)


def test_measurement_measured_at_node_must_be_non_empty() -> None:
    with pytest.raises(ValidationError, match='measured_at_node'):
        _make_measurement(measured_at_node='')


def test_measurement_injection_method_must_be_one_of_four() -> None:
    with pytest.raises(ValidationError, match='injection_method'):
        _make_measurement(injection_method='handwave')


@pytest.mark.parametrize(
    'method',
    [
        'middlebrook_voltage',
        'middlebrook_current',
        'tian',
        'rosenstark_return_ratio',
    ],
)
def test_measurement_accepts_all_four_injection_methods(method: str) -> None:
    m = _make_measurement(injection_method=method)
    assert m.injection_method == method


@pytest.mark.parametrize(
    ('margin_deg', 'expected_class'),
    [
        (75.0, 'high'),
        (60.0001, 'high'),
        (60.0, 'adequate'),
        (45.0001, 'adequate'),
        (45.0, 'marginal'),
        (30.0001, 'marginal'),
        (30.0, 'risky'),
        (-15.0, 'risky'),
    ],
)
def test_measurement_stability_class_consistent_with_margin(
    margin_deg: float, expected_class: str
) -> None:
    m = _make_measurement(margin_deg=margin_deg, stability_class=expected_class)
    assert m.stability_class == expected_class


def test_measurement_stability_class_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match='stability_class'):
        _make_measurement(margin_deg=55.0, stability_class='high')


def test_measurement_nan_margin_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_measurement(margin_deg=math.nan, stability_class='risky')


def test_measurement_nan_crossover_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_measurement(crossover_hz=math.nan)


def test_measurement_nan_gain_margin_rejected() -> None:
    with pytest.raises(ValidationError, match='gain_margin_db'):
        _make_measurement(gain_margin_db=math.nan)


def test_measurement_negative_phase_crossover_rejected() -> None:
    with pytest.raises(ValidationError, match='phase_crossover_hz'):
        _make_measurement(phase_crossover_hz=-1.0)


def test_measurement_extra_crossovers_must_be_positive() -> None:
    with pytest.raises(ValidationError, match='extra_crossovers_hz'):
        _make_measurement(extra_crossovers_hz=(1_000.0, -2.0))


def test_measurement_extra_crossovers_nan_rejected() -> None:
    with pytest.raises(ValidationError, match='extra_crossovers_hz'):
        _make_measurement(extra_crossovers_hz=(1_000.0, math.nan))


# ----------------------------------------------------- AutoDetectInfo ----


def test_auto_detect_info_happy() -> None:
    info = AutoDetectInfo(
        chosen_node='/fb_node',
        chosen_element_ref='C_fb_block',
        confidence=0.92,
        alternatives=(('/cathode', 'C_k_bypass', 0.55),),
        algorithm_notes='passive feedback path detected',
    )
    assert info.chosen_node == '/fb_node'
    assert info.chosen_element_ref == 'C_fb_block'
    assert info.confidence == pytest.approx(0.92)
    assert info.alternatives == (('/cathode', 'C_k_bypass', 0.55),)


def test_auto_detect_info_empty_alternatives_allowed() -> None:
    info = AutoDetectInfo(
        chosen_node='/fb',
        chosen_element_ref='R_fb',
        confidence=1.0,
        alternatives=(),
        algorithm_notes='only one cycle',
    )
    assert info.alternatives == ()


@pytest.mark.parametrize('bad', [-0.01, 1.01, math.nan])
def test_auto_detect_info_confidence_range(bad: float) -> None:
    with pytest.raises(ValidationError, match='confidence'):
        AutoDetectInfo(
            chosen_node='/fb',
            chosen_element_ref='R_fb',
            confidence=bad,
            alternatives=(),
            algorithm_notes='',
        )


def test_auto_detect_info_chosen_node_non_empty() -> None:
    with pytest.raises(ValidationError, match='chosen_node'):
        AutoDetectInfo(
            chosen_node='',
            chosen_element_ref='R_fb',
            confidence=0.5,
            alternatives=(),
            algorithm_notes='x',
        )


def test_auto_detect_info_chosen_element_ref_non_empty() -> None:
    with pytest.raises(ValidationError, match='chosen_element_ref'):
        AutoDetectInfo(
            chosen_node='/fb',
            chosen_element_ref='',
            confidence=0.5,
            alternatives=(),
            algorithm_notes='x',
        )


def test_auto_detect_info_alternative_confidence_in_range() -> None:
    with pytest.raises(ValidationError, match='alternatives'):
        AutoDetectInfo(
            chosen_node='/fb',
            chosen_element_ref='R_fb',
            confidence=0.5,
            alternatives=(('/out', 'R_load', 1.5),),
            algorithm_notes='',
        )


def test_auto_detect_info_alternative_node_non_empty() -> None:
    with pytest.raises(ValidationError, match='alternatives'):
        AutoDetectInfo(
            chosen_node='/fb',
            chosen_element_ref='R_fb',
            confidence=0.5,
            alternatives=(('', 'R_load', 0.4),),
            algorithm_notes='',
        )


def test_auto_detect_info_alternative_element_ref_non_empty() -> None:
    with pytest.raises(ValidationError, match='alternatives'):
        AutoDetectInfo(
            chosen_node='/fb',
            chosen_element_ref='R_fb',
            confidence=0.5,
            alternatives=(('/out', '', 0.4),),
            algorithm_notes='',
        )


def test_auto_detect_info_alternative_nan_confidence_rejected() -> None:
    with pytest.raises(ValidationError, match='alternatives'):
        AutoDetectInfo(
            chosen_node='/fb',
            chosen_element_ref='R_fb',
            confidence=0.5,
            alternatives=(('/out', 'R_load', math.nan),),
            algorithm_notes='',
        )


def test_auto_detect_info_is_frozen() -> None:
    info = AutoDetectInfo(
        chosen_node='/fb',
        chosen_element_ref='R_fb',
        confidence=0.5,
        alternatives=(),
        algorithm_notes='',
    )
    with pytest.raises(ValidationError):
        info.confidence = 0.9  # type: ignore[misc]


# ------------------------------------------------------- FeedbackCycle ----


def test_feedback_cycle_happy() -> None:
    cycle = FeedbackCycle(
        nodes=('/in', '/g1', '/p1', '/out', '/fb'),
        elements=('V1', 'R_g1', 'C_in', 'R_fb', 'C_fb'),
        forward_path_score=0.9,
        feedback_path_score=0.85,
        suggested_break_node='/fb',
        suggested_break_element_ref='R_fb',
        confidence=0.78,
    )
    assert cycle.suggested_break_node == '/fb'
    assert cycle.suggested_break_element_ref == 'R_fb'
    assert cycle.confidence == pytest.approx(0.78)


@pytest.mark.parametrize(
    'field',
    ['forward_path_score', 'feedback_path_score', 'confidence'],
)
@pytest.mark.parametrize('bad', [-0.01, 1.01])
def test_feedback_cycle_scores_in_unit_range(field: str, bad: float) -> None:
    base: dict[str, object] = {
        'nodes': ('/a', '/b'),
        'elements': ('R1',),
        'forward_path_score': 0.5,
        'feedback_path_score': 0.5,
        'suggested_break_node': '/a',
        'suggested_break_element_ref': 'R1',
        'confidence': 0.5,
    }
    base[field] = bad
    with pytest.raises(ValidationError, match=field):
        FeedbackCycle(**base)  # type: ignore[arg-type]


def test_feedback_cycle_suggested_break_must_be_in_nodes() -> None:
    with pytest.raises(ValidationError, match='suggested_break_node'):
        FeedbackCycle(
            nodes=('/a', '/b'),
            elements=('R1',),
            forward_path_score=0.5,
            feedback_path_score=0.5,
            suggested_break_node='/nonexistent',
            suggested_break_element_ref='R1',
            confidence=0.5,
        )


def test_feedback_cycle_suggested_break_element_must_be_in_elements() -> None:
    with pytest.raises(ValidationError, match='suggested_break_element_ref'):
        FeedbackCycle(
            nodes=('/a',),
            elements=('R1',),
            forward_path_score=0.5,
            feedback_path_score=0.5,
            suggested_break_node='/a',
            suggested_break_element_ref='NONEXISTENT',
            confidence=0.5,
        )


def test_feedback_cycle_suggested_break_element_ref_non_empty() -> None:
    with pytest.raises(ValidationError, match='suggested_break_element_ref'):
        FeedbackCycle(
            nodes=('/a',),
            elements=('R1',),
            forward_path_score=0.5,
            feedback_path_score=0.5,
            suggested_break_node='/a',
            suggested_break_element_ref='',
            confidence=0.5,
        )


def test_feedback_cycle_nodes_non_empty() -> None:
    with pytest.raises(ValidationError, match='nodes'):
        FeedbackCycle(
            nodes=(),
            elements=('R1',),
            forward_path_score=0.5,
            feedback_path_score=0.5,
            suggested_break_node='/a',
            suggested_break_element_ref='R1',
            confidence=0.5,
        )


def test_feedback_cycle_elements_non_empty() -> None:
    with pytest.raises(ValidationError, match='elements'):
        FeedbackCycle(
            nodes=('/a',),
            elements=(),
            forward_path_score=0.5,
            feedback_path_score=0.5,
            suggested_break_node='/a',
            suggested_break_element_ref='R1',
            confidence=0.5,
        )


def test_feedback_cycle_is_frozen() -> None:
    cycle = FeedbackCycle(
        nodes=('/a',),
        elements=('R1',),
        forward_path_score=0.5,
        feedback_path_score=0.5,
        suggested_break_node='/a',
        suggested_break_element_ref='R1',
        confidence=0.5,
    )
    with pytest.raises(ValidationError):
        cycle.confidence = 0.9  # type: ignore[misc]


# ----------------------------------------------- PhaseMarginDelta ----


def test_phase_margin_delta_from_measurements_positive_change() -> None:
    before = _make_measurement(margin_deg=35.0, stability_class='marginal')
    after = _make_measurement(margin_deg=55.0, stability_class='adequate')
    delta = PhaseMarginDelta.from_measurements(before=before, after=after)
    assert delta.before is before
    assert delta.after is after
    assert delta.delta_absolute == pytest.approx(20.0)
    assert delta.delta_relative_percent == pytest.approx(
        (55.0 - 35.0) / 35.0 * 100.0
    )
    assert delta.failed_reason is None
    assert delta.metric_field == 'margin_deg'


def test_phase_margin_delta_from_measurements_negative_change() -> None:
    before = _make_measurement(margin_deg=55.0, stability_class='adequate')
    after = _make_measurement(margin_deg=20.0, stability_class='risky')
    delta = PhaseMarginDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(-35.0)
    assert delta.delta_relative_percent == pytest.approx(
        (20.0 - 55.0) / 55.0 * 100.0
    )


def test_phase_margin_delta_from_measurements_zero_before_no_relative() -> None:
    before = _make_measurement(margin_deg=0.0, stability_class='risky')
    after = _make_measurement(margin_deg=10.0, stability_class='risky')
    delta = PhaseMarginDelta.from_measurements(before=before, after=after)
    assert delta.delta_absolute == pytest.approx(10.0)
    assert delta.delta_relative_percent is None


def test_phase_margin_delta_from_failed_after_happy() -> None:
    before = _make_measurement()
    delta = PhaseMarginDelta.from_failed_after(
        before=before, reason='no unity-gain crossover after edits'
    )
    assert delta.after is None
    assert delta.delta_absolute is None
    assert delta.delta_relative_percent is None
    assert delta.failed_reason == 'no unity-gain crossover after edits'


def test_phase_margin_delta_after_none_requires_failed_reason() -> None:
    before = _make_measurement()
    with pytest.raises(ValidationError, match='failed_reason'):
        PhaseMarginDelta(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=None,
        )


def test_phase_margin_delta_after_set_forbids_failed_reason() -> None:
    before = _make_measurement(margin_deg=40.0, stability_class='marginal')
    after = _make_measurement(margin_deg=55.0, stability_class='adequate')
    with pytest.raises(ValidationError, match='failed_reason'):
        PhaseMarginDelta(
            before=before,
            after=after,
            delta_absolute=15.0,
            delta_relative_percent=37.5,
            failed_reason='whoops',
        )


def test_phase_margin_delta_after_set_requires_delta_absolute() -> None:
    before = _make_measurement(margin_deg=40.0, stability_class='marginal')
    after = _make_measurement(margin_deg=55.0, stability_class='adequate')
    with pytest.raises(ValidationError, match='delta_absolute'):
        PhaseMarginDelta(
            before=before,
            after=after,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=None,
        )


def test_phase_margin_delta_after_none_forbids_delta_absolute() -> None:
    before = _make_measurement()
    with pytest.raises(ValidationError, match='delta_absolute'):
        PhaseMarginDelta(
            before=before,
            after=None,
            delta_absolute=5.0,
            delta_relative_percent=None,
            failed_reason='failure',
        )


def test_phase_margin_delta_after_none_forbids_delta_relative_percent() -> None:
    before = _make_measurement()
    with pytest.raises(ValidationError, match='delta_relative_percent'):
        PhaseMarginDelta(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=15.0,
            failed_reason='failure',
        )


def test_phase_margin_delta_nan_delta_absolute_rejected() -> None:
    before = _make_measurement(margin_deg=40.0, stability_class='marginal')
    after = _make_measurement(margin_deg=55.0, stability_class='adequate')
    with pytest.raises(ValidationError, match='delta_absolute'):
        PhaseMarginDelta(
            before=before,
            after=after,
            delta_absolute=math.nan,
            delta_relative_percent=37.5,
            failed_reason=None,
        )


def test_phase_margin_delta_nan_delta_relative_rejected() -> None:
    before = _make_measurement(margin_deg=40.0, stability_class='marginal')
    after = _make_measurement(margin_deg=55.0, stability_class='adequate')
    with pytest.raises(ValidationError, match='delta_relative_percent'):
        PhaseMarginDelta(
            before=before,
            after=after,
            delta_absolute=15.0,
            delta_relative_percent=math.nan,
            failed_reason=None,
        )


def test_phase_margin_delta_is_frozen() -> None:
    before = _make_measurement(margin_deg=40.0, stability_class='marginal')
    after = _make_measurement(margin_deg=55.0, stability_class='adequate')
    delta = PhaseMarginDelta.from_measurements(before=before, after=after)
    with pytest.raises(ValidationError):
        delta.delta_absolute = 0.0  # type: ignore[misc]


def test_phase_margin_delta_failed_reason_non_empty() -> None:
    before = _make_measurement()
    with pytest.raises(ValidationError, match='failed_reason'):
        PhaseMarginDelta(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason='',
        )
