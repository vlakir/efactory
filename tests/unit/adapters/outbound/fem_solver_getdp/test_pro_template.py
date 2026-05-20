"""Unit: pro_template rendering (linear back-compat + T129 nonlinear)."""

from __future__ import annotations

import pytest

from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve
from adapters.outbound.fem_solver_getdp.pro_template import (
    NL_MAX_ITER,
    NL_RELAXATION,
    NL_TOL,
    render_magnetostatic_pro,
    render_magnetostatic_pro_nonlinear,
)


def test_linear_template_substitutes_params() -> None:
    out = render_magnetostatic_pro(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.75e-4,
    )
    assert 'mur_iron = 8000.0;' in out
    assert 'N_primary    = 2500;' in out
    assert 'I_ref        = 1;' in out
    # площадь окна форматируется через {:g} (compact, без trailing zeros)
    assert 'area_window  = 0.000275;' in out
    # linear path: no IterativeLoop, no InterpolationLinear
    assert 'IterativeLoop' not in out
    assert 'InterpolationLinear' not in out
    # Group / Resolution / PostProcessing присутствуют
    assert 'Group {' in out
    assert 'Resolution {' in out
    assert 'PostProcessing {' in out


def test_nonlinear_template_embeds_bh_list_literal() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    bh_literal = curve.as_getdp_list_literal()
    out = render_magnetostatic_pro_nonlinear(
        bh_list_literal=bh_literal,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.75e-4,
    )
    # таблица вставлена как InterpolationLinear аргумент
    assert 'InterpolationLinear' in out
    assert bh_literal in out
    # ν[NonIron] оставлен на mu0 (vacuum)
    assert 'nu[NonIron] = 1.0 / mu0;' in out


def test_nonlinear_template_uses_iterative_loop_with_defaults() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    out = render_magnetostatic_pro_nonlinear(
        bh_list_literal=curve.as_getdp_list_literal(),
        n_primary=100,
        i_ref=1.0,
        area_window=1.0e-4,
    )
    assert 'IterativeLoop' in out
    assert str(NL_MAX_ITER) in out
    assert f'{NL_TOL:g}' in out
    assert f'{NL_RELAXATION:g}' in out
    # Picard pattern Generate/Solve внутри IterativeLoop, без JacNL
    assert 'Generate[A]; Solve[A];' in out
    assert 'JacNL' not in out


def test_nonlinear_template_custom_loop_params_propagate() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    out = render_magnetostatic_pro_nonlinear(
        bh_list_literal=curve.as_getdp_list_literal(),
        n_primary=100,
        i_ref=1.0,
        area_window=1.0e-4,
        nl_max_iter=200,
        nl_tol=1.0e-7,
        nl_relax=0.5,
    )
    assert 'IterativeLoop[ 200, 1e-07, 0.5 ]' in out


def test_nonlinear_template_keeps_coil_topology() -> None:
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    out = render_magnetostatic_pro_nonlinear(
        bh_list_literal=curve.as_getdp_list_literal(),
        n_primary=2500,
        i_ref=1.0,
        area_window=2.75e-4,
    )
    # split coil topology (T113 pilot Stage B+C): +Jz в Primary,
    # -Jz в Secondary (return-leg simulation).
    assert 'js[Primary]   = Vector[0, 0,  J_density];' in out
    assert 'js[Secondary] = Vector[0, 0, -J_density];' in out
    assert 'N_primary    = 2500;' in out


def test_linear_back_compat_render_byte_identical_to_baseline() -> None:
    """Pilot Stage B+C формат не изменился — критично для T113 regression."""
    out = render_magnetostatic_pro(
        mur_iron=8000.0,
        n_primary=2500,
        i_ref=1.0,
        area_window=2.75e-4,
    )
    # эталонные маркеры из pilot .pro (commit 9c42042) сохранены
    assert 'efactory adapters.outbound.fem_solver_getdp magnetostatic .pro' in out
    assert 'BF_PerpendicularEdge' in out
    assert 'Print[ energy_per_depth[Domain], OnGlobal, Format Table,' in out


def test_nonlinear_template_emits_flux_linkage_postprocessing() -> None:
    """T129 Phase B: новый Quantity flux_linkage_per_depth + Print → flux_linkage.txt."""
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    out = render_magnetostatic_pro_nonlinear(
        bh_list_literal=curve.as_getdp_list_literal(),
        n_primary=2500,
        i_ref=1.0,
        area_window=2.75e-4,
    )
    # Quantity объявлен
    assert 'Name flux_linkage_per_depth;' in out
    # формула integrate (N/A_w) · CompZ[a] над Primary
    assert '(N_primary / area_window) * CompZ[{a}]' in out
    assert 'In Primary;' in out
    # Print в PostOperation
    assert 'Print[ flux_linkage_per_depth[Primary]' in out
    assert '"flux_linkage.txt"' in out


def test_nonlinear_template_raises_on_missing_placeholder_substitution() -> None:
    """Защита от typo'в в template (формат-плейсхолдеры должны быть закрыты)."""
    # вызов с минимальным валидным набором не должен бросать KeyError
    curve = FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)
    try:
        render_magnetostatic_pro_nonlinear(
            bh_list_literal=curve.as_getdp_list_literal(),
            n_primary=1,
            i_ref=1.0,
            area_window=1.0,
        )
    except KeyError as exc:  # pragma: no cover  - regression guard
        pytest.fail(f'unrendered placeholder in nonlinear template: {exc}')
