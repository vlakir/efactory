"""Unit: render_magnetostatic_sif_linear (T133 Phase 1 Elmer adapter)."""

from __future__ import annotations

from adapters.outbound.fem_solver_elmer.sif_template import (
    render_magnetostatic_sif_linear,
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
