"""
Pure-Python leakage inductance formula (sandwich transformer, T132 Phase C).

Reference: Erickson & Maksimović "Fundamentals of Power Electronics"
§15.5 (low-frequency transformer model with sandwich windings);
Hurley & Wölfle "Transformers and Inductors for Power Electronics"
§4.6 (interleaving reduction).

Formula:

    L_σ = (μ₀ · n_p² · MLT) / b_w · h_eff
    h_eff = [(b_p + b_s) / 3 + a · (n_sections - 1)] / N²
    N = число inter-winding interfaces в pattern

Точность ~20-30% (типично для analytical sandwich) — Erickson §15
формула idealizes uniform current distribution (no skin/proximity);
для audio frequencies (1-30 kHz) на толстых OPT-обмотках это
приемлемо. Сравнение с FEM cross-check — T133 / BACKLOG.
"""

from __future__ import annotations

import math

MU_0 = 4 * math.pi * 1e-7  # vacuum permeability [H/m]


def count_inter_winding_interfaces(pattern: tuple[str, ...]) -> int:
    """
    Число section-to-section boundaries, где меняется обмотка.

    Для P-S → 1, P-S-P → 2, P-S-P-S-P → 4. Это `N` в interleaving
    reduction factor `1/N²`.
    """
    return sum(1 for i in range(len(pattern) - 1) if pattern[i] != pattern[i + 1])


def compute_leakage_inductance_h(
    *,
    primary_turns: int,
    mean_turn_length_m: float,
    window_height_m: float,
    primary_thickness_m: float,
    secondary_thickness_m: float,
    inter_section_insulation_m: float,
    pattern: tuple[str, ...],
) -> float:
    """
    Leakage inductance Lσ referred to primary side [H].

    Args:
        primary_turns: общее число витков primary обмотки (n_p).
        mean_turn_length_m: MLT в метрах (одна turn perimeter).
        window_height_m: высота winding window в axial направлении (b_w).
        primary_thickness_m: суммарная радиальная толщина primary стека (b_p).
        secondary_thickness_m: суммарная радиальная толщина secondary стека (b_s).
        inter_section_insulation_m: толщина изоляции между секциями (a),
            применяется ко всем `n_sections - 1` границам.
        pattern: tuple имён обмоток по секциям (см.
            `domain.magnetic.InterleavingPattern.pattern`).

    Returns:
        Lσ в Henries. 0.0 для degenerate cases:
        - `primary_turns == 0`;
        - pattern без inter-winding interfaces (всё одна обмотка).

    Raises:
        ValueError для невалидной геометрии (window_height_m <= 0,
        отрицательные thickness'ы).

    """
    if window_height_m <= 0:
        msg = f'window_height_m must be > 0 (got {window_height_m})'
        raise ValueError(msg)
    if primary_thickness_m < 0 or secondary_thickness_m < 0:
        msg = (
            f'thickness must be >= 0 '
            f'(primary={primary_thickness_m}, secondary={secondary_thickness_m})'
        )
        raise ValueError(msg)

    if primary_turns == 0:
        return 0.0

    n_interfaces = count_inter_winding_interfaces(pattern)
    if n_interfaces == 0:
        return 0.0

    n_gaps = len(pattern) - 1
    h_eff_base = (primary_thickness_m + secondary_thickness_m) / 3.0 + (
        inter_section_insulation_m * n_gaps
    )
    h_eff = h_eff_base / (n_interfaces**2)

    return (MU_0 * primary_turns**2 * mean_turn_length_m / window_height_m) * h_eff
