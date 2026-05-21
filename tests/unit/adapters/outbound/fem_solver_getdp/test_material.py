"""Unit: FrohlichBHCurve nonlinear material model (T129 Phase A)."""

from __future__ import annotations

import math

import pytest

from adapters.outbound.fem_solver_getdp.material import (
    MU_0,
    FrohlichBHCurve,
)


def test_curve_passes_through_origin() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    assert curve.b_values[0] == pytest.approx(0.0, abs=1e-12)
    assert curve.h_values[0] == pytest.approx(0.0, abs=1e-12)


def test_curve_has_at_least_ten_points() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    assert len(curve.b_values) == len(curve.h_values)
    assert len(curve.b_values) >= 10


def test_b_axis_spans_zero_to_just_below_saturation() -> None:
    b_sat = 1.2
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=b_sat)
    assert curve.b_values[-1] == pytest.approx(0.99 * b_sat, rel=1e-9)
    # monotonic
    for prev, nxt in zip(curve.b_values[:-1], curve.b_values[1:], strict=True):
        assert nxt > prev


def test_h_axis_strictly_monotonic_and_positive() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    for h in curve.h_values[1:]:
        assert h > 0.0
    for prev, nxt in zip(curve.h_values[:-1], curve.h_values[1:], strict=True):
        assert nxt > prev


def test_initial_slope_matches_mu_initial_in_low_field_limit() -> None:
    """B/H → μ₀·μ_init для B → 0 (slope касательной в нуле)."""
    mu_initial = 8000.0
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=mu_initial, b_sat=1.2)
    # первая ненулевая точка должна быть в линейном режиме
    b1, h1 = curve.b_values[1], curve.h_values[1]
    mu_observed = b1 / h1
    expected = MU_0 * mu_initial
    # допускаем небольшую кривизну от Frohlich (B/B_sat ≈ 0.1)
    assert mu_observed == pytest.approx(expected, rel=0.15)


def test_frohlich_equation_satisfied_on_each_point() -> None:
    """Точки лежат на кривой B(H) = μ₀·μ_init·H / (1 + μ₀·μ_init·H / B_sat)."""
    mu_initial = 8000.0
    b_sat = 1.2
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=mu_initial, b_sat=b_sat)
    for b, h in zip(curve.b_values, curve.h_values, strict=True):
        b_expected = MU_0 * mu_initial * h / (1.0 + MU_0 * mu_initial * h / b_sat)
        assert b == pytest.approx(b_expected, rel=1e-9, abs=1e-12)


def test_invalid_mu_initial_raises() -> None:
    with pytest.raises(ValueError, match='mu_initial'):
        FrohlichBHCurve.from_pyom_material(mu_initial=0.0, b_sat=1.2)
    with pytest.raises(ValueError, match='mu_initial'):
        FrohlichBHCurve.from_pyom_material(mu_initial=-1.0, b_sat=1.2)


def test_invalid_b_sat_raises() -> None:
    with pytest.raises(ValueError, match='b_sat'):
        FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=0.0)
    with pytest.raises(ValueError, match='b_sat'):
        FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=-0.5)


def test_invalid_num_points_raises() -> None:
    with pytest.raises(ValueError, match='num_points'):
        FrohlichBHCurve.from_pyom_material(
            mu_initial=8000.0,
            b_sat=1.2,
            num_points=1,
        )


def test_explicit_num_points_respected() -> None:
    curve = FrohlichBHCurve.from_pyom_material(
        mu_initial=8000.0,
        b_sat=1.2,
        num_points=21,
    )
    assert len(curve.b_values) == 21


def test_nu_b_table_yields_reciprocal_chord_slope() -> None:
    """ν-таблица ν(B) = H/B (chord) на ненулевых точках; ν(0) = 1/(μ₀·μ_init).

    GetDP InterpolationLinear для nu[Iron] ожидает (B, ν) пары где
    ν — magnetic reluctivity 1/μ_chord для текущего B.
    """
    mu_initial = 8000.0
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=mu_initial, b_sat=1.2)
    nu_table = curve.nu_of_b_table()
    # одинаковая длина
    assert len(nu_table) == len(curve.b_values)
    # первый элемент — (0, 1/(μ₀·μ_init))
    b0, nu0 = nu_table[0]
    assert b0 == 0.0
    assert nu0 == pytest.approx(1.0 / (MU_0 * mu_initial), rel=1e-9)
    # остальные — H/B
    for (b, nu), b_val, h_val in zip(
        nu_table[1:],
        curve.b_values[1:],
        curve.h_values[1:],
        strict=True,
    ):
        assert b == b_val
        assert nu == pytest.approx(h_val / b_val, rel=1e-12)


def test_getdp_list_literal_format_pairs_interleaved() -> None:
    """`as_getdp_list_literal()` рендерит {B0, nu0, B1, nu1, ...} с разделителем."""
    curve = FrohlichBHCurve.from_pyom_material(
        mu_initial=8000.0,
        b_sat=1.2,
        num_points=10,
    )
    literal = curve.as_getdp_list_literal()
    # начинается с {, заканчивается на }
    assert literal.startswith('{')
    assert literal.endswith('}')
    # ровно 2N чисел через запятую
    inner = literal.strip('{}')
    tokens = [tok.strip() for tok in inner.split(',')]
    assert len(tokens) == 2 * 10
    # все валидные float
    floats = [float(t) for t in tokens]
    # первая пара = (0, 1/(μ₀·μ_init))
    assert floats[0] == pytest.approx(0.0, abs=1e-12)
    assert floats[1] == pytest.approx(1.0 / (MU_0 * 8000.0), rel=1e-9)
    # остальные нечётные индексы — ν(B) = H/B
    for i in range(1, 10):
        b = floats[2 * i]
        nu = floats[2 * i + 1]
        assert b > 0.0
        # ν растёт с приближением к saturation (μ_chord падает)
        assert nu > floats[1] * (1.0 - 1e-9) or math.isclose(nu, floats[1])
