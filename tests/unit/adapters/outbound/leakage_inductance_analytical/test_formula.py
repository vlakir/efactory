"""
Unit: pure-Python leakage formula (T132 Phase C — analytical backend).

Reference: Erickson & Maksimović "Fundamentals of Power Electronics"
§15.5 / Hurley & Wölfle "Transformers and Inductors for Power
Electronics" §4.6 — sandwich transformer leakage с interleaving
reduction 1/N².
"""

from __future__ import annotations

import math

import pytest

from adapters.outbound.leakage_inductance_analytical.formula import (
    MU_0,
    compute_leakage_inductance_h,
    count_inter_winding_interfaces,
)


# ---------------------------------------------------------------------------
# count_inter_winding_interfaces
# ---------------------------------------------------------------------------


def test_interfaces_p_s_2_section() -> None:
    assert count_inter_winding_interfaces(('primary', 'secondary')) == 1


def test_interfaces_p_s_p_3_section() -> None:
    assert count_inter_winding_interfaces(('primary', 'secondary', 'primary')) == 2


def test_interfaces_p_s_p_s_p_5_section() -> None:
    pattern = ('primary', 'secondary', 'primary', 'secondary', 'primary')
    assert count_inter_winding_interfaces(pattern) == 4


def test_interfaces_single_section_no_p_s_boundary() -> None:
    """Pattern с одной обмоткой — нет inter-winding interfaces."""
    assert count_inter_winding_interfaces(('primary',)) == 0


def test_interfaces_all_primary_no_boundary() -> None:
    """Несколько секций одной обмотки — нет P-S границ."""
    assert count_inter_winding_interfaces(('primary', 'primary', 'primary')) == 0


# ---------------------------------------------------------------------------
# compute_leakage_inductance_h
# ---------------------------------------------------------------------------


# Reference values: small toy fixture (для проверки sanity)
PRIMARY_TURNS = 200
MLT = 0.070  # 70 mm — typical E 42/15 OPT
B_W = 0.0273  # winding window height — E 42/15
B_P = 0.0005  # 0.5 mm primary stack (2 layers × 0.25 mm)
B_S = 0.0001  # 0.1 mm secondary
A = 25e-6  # 25 µm kapton inter-section
P_S = ('primary', 'secondary')
P_S_P = ('primary', 'secondary', 'primary')
P_S_P_S_P = ('primary', 'secondary', 'primary', 'secondary', 'primary')


def _expected_l_sigma(n_p: int, mlt: float, b_w: float,
                     b_p: float, b_s: float, a: float,
                     n_interfaces: int, n_sections: int) -> float:
    """Reference computation for test verification."""
    if n_interfaces == 0:
        return 0.0
    n_gaps = n_sections - 1
    h_eff_base = (b_p + b_s) / 3.0 + a * n_gaps
    h_eff = h_eff_base / (n_interfaces ** 2)
    return MU_0 * n_p ** 2 * mlt / b_w * h_eff


def test_leakage_p_s_2_section_matches_hand_calc() -> None:
    """P-S sandwich (N=1) — baseline Lσ value."""
    expected = _expected_l_sigma(
        PRIMARY_TURNS, MLT, B_W, B_P, B_S, A, n_interfaces=1, n_sections=2,
    )
    result = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS,
        mean_turn_length_m=MLT,
        window_height_m=B_W,
        primary_thickness_m=B_P,
        secondary_thickness_m=B_S,
        inter_section_insulation_m=A,
        pattern=P_S,
    )
    assert result == pytest.approx(expected, rel=1e-9)
    # Sanity: для 200 turns / E 42/15 / толстый sandwich, Lσ porядок 1-10 µH
    assert 1e-8 < result < 1e-4


def test_leakage_p_s_p_3_section_smaller_than_p_s() -> None:
    """P-S-P (N=2) даёт меньше leakage чем P-S (N=1) — Hurley §4.6 monotonicity."""
    l_p_s = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S,
    )
    l_p_s_p = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S_P,
    )
    assert l_p_s_p < l_p_s


def test_leakage_p_s_p_s_p_5_section_smallest() -> None:
    """5-section (N=4) — наименьшее leakage из трёх вариантов."""
    l_p_s_p = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S_P,
    )
    l_p_s_p_s_p = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S_P_S_P,
    )
    assert l_p_s_p_s_p < l_p_s_p


def test_leakage_monotonic_decrease_across_three_patterns() -> None:
    """Full monotonicity gate: Lσ(P-S) > Lσ(P-S-P) > Lσ(P-S-P-S-P)."""
    values = [
        compute_leakage_inductance_h(
            primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
            primary_thickness_m=B_P, secondary_thickness_m=B_S,
            inter_section_insulation_m=A, pattern=p,
        )
        for p in (P_S, P_S_P, P_S_P_S_P)
    ]
    assert values[0] > values[1] > values[2]


def test_leakage_n_squared_reduction_dominant() -> None:
    """Для нулевой изоляции (a=0) reduction строго 1/N²."""
    l_n1 = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=0.0, pattern=P_S,  # N=1
    )
    l_n2 = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=0.0, pattern=P_S_P,  # N=2
    )
    l_n4 = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=0.0, pattern=P_S_P_S_P,  # N=4
    )
    # Без insulation: ratio precisely 1/N²
    assert l_n2 == pytest.approx(l_n1 / 4.0, rel=1e-9)
    assert l_n4 == pytest.approx(l_n1 / 16.0, rel=1e-9)


def test_leakage_zero_interfaces_returns_zero() -> None:
    """Pattern без P-S границ → Lσ = 0 (нет transformer coupling)."""
    result = compute_leakage_inductance_h(
        primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=('primary',),
    )
    assert result == 0.0


def test_leakage_scales_n_p_squared() -> None:
    """Lσ ∝ n_p² (turn-ratio coupling)."""
    l_200 = compute_leakage_inductance_h(
        primary_turns=200, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S,
    )
    l_400 = compute_leakage_inductance_h(
        primary_turns=400, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S,
    )
    assert l_400 == pytest.approx(l_200 * 4.0, rel=1e-9)


def test_leakage_window_height_zero_raises() -> None:
    """b_w=0 — degenerate geometry; raise instead of div-by-zero."""
    with pytest.raises(ValueError, match='window_height_m'):
        compute_leakage_inductance_h(
            primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=0.0,
            primary_thickness_m=B_P, secondary_thickness_m=B_S,
            inter_section_insulation_m=A, pattern=P_S,
        )


def test_leakage_negative_thickness_raises() -> None:
    """Bad input: negative geometry."""
    with pytest.raises(ValueError, match='thickness'):
        compute_leakage_inductance_h(
            primary_turns=PRIMARY_TURNS, mean_turn_length_m=MLT, window_height_m=B_W,
            primary_thickness_m=-1e-3, secondary_thickness_m=B_S,
            inter_section_insulation_m=A, pattern=P_S,
        )


def test_leakage_zero_primary_turns_returns_zero() -> None:
    result = compute_leakage_inductance_h(
        primary_turns=0, mean_turn_length_m=MLT, window_height_m=B_W,
        primary_thickness_m=B_P, secondary_thickness_m=B_S,
        inter_section_insulation_m=A, pattern=P_S,
    )
    assert result == 0.0


def test_mu_0_value_correct() -> None:
    assert MU_0 == pytest.approx(4 * math.pi * 1e-7)
