"""detect_feedback_break_node use case (T153 Phase B.5)."""

from __future__ import annotations

import pytest

from application.detect_feedback_break_node import detect_feedback_break_node
from domain.phase_margin import (
    AutoDetectConfidenceTooLowError,
    AutoDetectInfo,
    NoFeedbackLoopDetectedError,
)


_OPAMP_INV_FEEDBACK_NETLIST = (
    '* op-amp inverting amp с output RC pole\n'
    'V_in vin 0 DC 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp v_open 0 0 in_neg 1e5\n'
    'R_amp v_open vout 1k\n'
    'C_amp vout 0 10u\n'
    'R_load vout 0 1Meg\n'
    '.end\n'
)


def test_returns_auto_detect_info() -> None:
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
        confidence_threshold=0.3,
    )
    assert isinstance(info, AutoDetectInfo)


def test_chosen_edge_is_passive_in_feedback() -> None:
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
        confidence_threshold=0.3,
    )
    # Должен выбрать passive element из feedback path
    assert info.chosen_element_ref in {'R_fb', 'R_amp', 'C_amp', 'R_load'}


def test_alternatives_present_for_multi_cycle_fixture() -> None:
    """opamp_inv с pairwise expansion → несколько cycles → alternatives."""
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
        confidence_threshold=0.3,
    )
    assert len(info.alternatives) >= 1


def test_no_feedback_loop_raises_domain_error() -> None:
    """Pure passive RC ladder без active element — не feedback."""
    netlist = (
        'V_in a 0 DC 1\n'
        'R1 a b 1k\n'
        'C1 b 0 1u\n'
    )
    with pytest.raises(NoFeedbackLoopDetectedError, match='no feedback'):
        detect_feedback_break_node(netlist_text=netlist, confidence_threshold=0.5)


def test_open_loop_amp_no_real_feedback() -> None:
    """Open-loop amplifier: signal path не возвращается на gate.

    Phase C.1.5 (MIN_CYCLE_LENGTH=2): graph analyzer ловит parasitic
    MOSFET body-drain cycle (M1 + R_d, 2-net через vdd→0), но его
    confidence low (ground penalty + non-signal-path topology). С
    threshold=0.5 raises `AutoDetectConfidenceTooLowError` — caller
    видит, что auto-detect не нашёл «настоящий» feedback и должен
    указать break point вручную (либо признать схему open-loop).

    Pre-C.1.5 (MIN=3) поведение — `NoFeedbackLoopDetectedError` —
    было artefact того, что 2-net parasitic не считался cycle.
    """
    netlist = (
        'V_in vin 0 AC 1\n'
        'R_in vin gate 1k\n'
        'M1 vdd gate src 0 NMOS\n'
        'R_d vdd 0 10k\n'  # no path from drain back to gate (signal-wise)
    )
    with pytest.raises(AutoDetectConfidenceTooLowError):
        detect_feedback_break_node(netlist_text=netlist, confidence_threshold=0.5)


def test_confidence_too_low_raises_domain_error() -> None:
    info_with_low_thresh = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
        confidence_threshold=0.3,
    )
    # Опираемся на тот же fixture с высоким threshold
    with pytest.raises(AutoDetectConfidenceTooLowError, match='confidence'):
        detect_feedback_break_node(
            netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
            confidence_threshold=info_with_low_thresh.confidence + 0.1,
        )


def test_default_threshold_is_zero_point_eight() -> None:
    """Spec §3: default confidence_threshold = 0.8."""
    # На fixture с confidence < 0.8 default vызывает AutoDetectConfidenceTooLowError
    with pytest.raises(AutoDetectConfidenceTooLowError):
        detect_feedback_break_node(netlist_text=_OPAMP_INV_FEEDBACK_NETLIST)


def test_chosen_node_present_in_netlist() -> None:
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
        confidence_threshold=0.3,
    )
    # break_node должен быть legitimate net из netlist'а
    assert info.chosen_node in {'vin', '0', 'in_neg', 'vout', 'v_open'}


def test_confidence_in_unit_range() -> None:
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
        confidence_threshold=0.0,
    )
    assert 0.0 <= info.confidence <= 1.0


def test_empty_netlist_raises_no_feedback_loop() -> None:
    with pytest.raises(NoFeedbackLoopDetectedError):
        detect_feedback_break_node(netlist_text='', confidence_threshold=0.5)


def test_invalid_confidence_threshold_rejected() -> None:
    with pytest.raises(ValueError, match='confidence_threshold'):
        detect_feedback_break_node(
            netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
            confidence_threshold=1.5,
        )
    with pytest.raises(ValueError, match='confidence_threshold'):
        detect_feedback_break_node(
            netlist_text=_OPAMP_INV_FEEDBACK_NETLIST,
            confidence_threshold=-0.1,
        )
