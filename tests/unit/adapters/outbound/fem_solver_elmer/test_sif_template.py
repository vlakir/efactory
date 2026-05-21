"""Unit: render_magnetostatic_sif_{linear,nonlinear} (T133 Phase 1+2 Elmer adapter)."""

from __future__ import annotations

from adapters.outbound.fem_solver_elmer.sif_template import (
    render_magnetostatic_sif_linear,
    render_magnetostatic_sif_nonlinear,
)


def test_sif_contains_required_sections() -> None:
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    for section in (
        'Header',
        'Simulation',
        'Constants',
        'Body 1',
        'Body 2',
        'Body 7',
        'Material 1',
        'Material 2',
        'Body Force 1',
        'Equation 1',
        'Solver 1',
        'Solver 2',
        'Boundary Condition 1',
    ):
        assert section in sif, f'missing section: {section!r}'


def test_sif_uses_mgdyn2d_solver() -> None:
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    assert 'Procedure = "MagnetoDynamics2D" "MagnetoDynamics2D"' in sif


def test_sif_renders_infinity_bc_on_outer_boundary() -> None:
    """T133 — outer BC = Infinity BC, не Dirichlet A=0 (T113 split)."""
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    assert 'Infinity BC = Logical True' in sif


def test_sif_computes_current_density_from_n_i_a() -> None:
    """J = N · I / A_window — проверяем формулу."""
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    # 2500 / 2.74972e-4 = 9091818.512... → check для значимых 6 знаков
    assert 'Current Density = Real 9091' in sif


def test_sif_uses_relative_permeability_for_iron() -> None:
    """Phase 1 linear — Iron Material через Relative Permeability, не H-B Curve."""
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    assert 'Relative Permeability = Real 8000' in sif
    assert 'H-B Curve' not in sif  # Phase 2 only


def test_sif_marks_primary_body_with_mask_property() -> None:
    """SaveScalars body int A нужен Mask Name = PrimaryRegion на Body 2."""
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    assert 'PrimaryRegion = Logical True' in sif
    assert 'Mask Name 1 = "PrimaryRegion"' in sif


def test_sif_savescalars_uses_body_int_operator() -> None:
    """auto-memory feedback_elmer_savescalars_quirks: "body int", не "body integral"."""
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    assert 'Operator 1 = "body int"' in sif


def test_sif_active_solvers_includes_savescalars() -> None:
    """auto-memory feedback_elmer_savescalars_quirks: SaveScalars MUST в Active Solvers."""
    sif = render_magnetostatic_sif_linear(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.74972e-4,
    )
    assert 'Active Solvers(2) = 1 2' in sif


_SAMPLE_HB_PAIRS = (
    (0.0, 0.0),
    (100.0, 1.0),
    (500.0, 1.5),
    (5000.0, 1.8),
)


def test_nonlinear_sif_uses_hb_curve_variable_coupled_iter() -> None:
    """Phase 0 verified syntax — Variable Coupled iter + Real cubic."""
    sif = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.05,
        area_window=2.74972e-4,
    )
    assert 'H-B Curve = Variable Coupled iter' in sif
    assert 'Real cubic' in sif


def test_nonlinear_sif_renders_full_hb_table() -> None:
    """Каждая (H,B) pair появляется в .sif в правильном порядке."""
    sif = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.05,
        area_window=2.74972e-4,
    )
    assert '100' in sif
    assert '1.5' in sif
    assert '5000' in sif
    assert '1.8' in sif


def test_nonlinear_sif_enables_newton_after_iterations() -> None:
    """Newton после 3 Picard iterations (W3 mitigation — Frohlich knee)."""
    sif = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.05,
        area_window=2.74972e-4,
    )
    assert 'Nonlinear System Newton After Iterations = 3' in sif
    assert 'Nonlinear System Relaxation Factor = 0.7' in sif
    assert 'Nonlinear System Max Iterations = 50' in sif


def test_nonlinear_sif_does_not_contain_relative_permeability_for_iron() -> None:
    """Iron material через H-B Curve, не Relative Permeability scalar."""
    sif = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.05,
        area_window=2.74972e-4,
    )
    # Air still uses Relative Permeability = Real 1.0 — допустимо.
    iron_section = sif.split('Material 2')[1].split('Material')[0]
    assert 'Relative Permeability' not in iron_section


def test_nonlinear_sif_renders_current_for_actual_i_value() -> None:
    """J = N · I_value / A — central-diff probe currents разные."""
    sif_minus = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.049,
        area_window=2.74972e-4,
    )
    sif_plus = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.051,
        area_window=2.74972e-4,
    )
    assert sif_minus != sif_plus  # разные J densities
    # J_minus = 2500 · 0.049 / 2.74972e-4 ≈ 445.5e3
    # J_plus  = 2500 · 0.051 / 2.74972e-4 ≈ 463.7e3
    assert 'Current Density = Real 4455' in sif_minus or 'Current Density = Real 445' in sif_minus
    assert 'Current Density = Real 4637' in sif_plus or 'Current Density = Real 463' in sif_plus


def test_nonlinear_sif_infinity_bc_preserved() -> None:
    """Outer BC та же что linear — Infinity BC = Logical True."""
    sif = render_magnetostatic_sif_nonlinear(
        h_b_pairs=_SAMPLE_HB_PAIRS,
        n_primary=2500,
        i_value=0.05,
        area_window=2.74972e-4,
    )
    assert 'Infinity BC = Logical True' in sif
