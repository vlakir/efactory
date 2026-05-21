"""Unit: fem_common helpers — ECoreDimensions factory + PyOM material readers."""

from __future__ import annotations

import math
from typing import Any

import pytest

from adapters.outbound.fem_common import (
    ECoreDimensions,
    emit_e_core_geo,
    emit_e_core_geo_3d,
    extract_frohlich_params,
    read_initial_permeability,
    read_saturation_flux_density,
)


def _opt_6p14p_dims() -> ECoreDimensions:
    """Hardcoded dims из PyOM calculate_core_data на OPT 6П14П SE (known-good fixture)."""
    return ECoreDimensions(
        core_w=0.04215,
        core_h=0.042,
        core_depth=0.01495,
        center_w=0.01195,
        center_h=0.0303,
        lateral_w=0.009075,
        lateral_x=0.018088,
        window_w=0.009075,
        window_h=0.0303,
        gap_len=0.0001,
    )


def test_emit_e_core_geo_contains_all_physical_groups() -> None:
    geo = emit_e_core_geo(_opt_6p14p_dims())
    for name in (
        'core', 'primary', 'secondary',
        'gap_center', 'gap_left', 'gap_right', 'air',
    ):
        assert f'Physical Surface("{name}")' in geo
    assert 'Physical Curve("infinity")' in geo


def test_emit_e_core_geo_sets_mesh_quadratic_frontal_delaunay() -> None:
    geo = emit_e_core_geo(_opt_6p14p_dims())
    assert 'Mesh.ElementOrder = 2;' in geo
    assert 'Mesh.Algorithm = 6;' in geo


def test_emit_e_core_geo_header_mentions_core_depth_scaling() -> None:
    dims = _opt_6p14p_dims()
    geo = emit_e_core_geo(dims)
    # Header comment должен содержать depth (для проверки 2D→3D scaling)
    assert f'{dims.core_depth:.5g}' in geo


# === emit_e_core_geo_3d (T133 Phase 3b) ===


def test_emit_e_core_geo_3d_uses_opencascade_kernel() -> None:
    """3D E-core requires OCC kernel for boolean operations (BooleanDifference)."""
    geo = emit_e_core_geo_3d(_opt_6p14p_dims())
    assert 'SetFactory("OpenCASCADE")' in geo


def test_emit_e_core_geo_3d_contains_4_physical_volumes() -> None:
    """Phase 3b ungapped E-core — 4 volumes: core, primary, secondary, air."""
    geo = emit_e_core_geo_3d(_opt_6p14p_dims())
    for name in ('core', 'primary', 'secondary', 'air'):
        assert f'Physical Volume("{name}"' in geo


def test_emit_e_core_geo_3d_contains_outer_physical_surface() -> None:
    """Outer surfaces для Infinity BC / Dirichlet (BC type — в .sif)."""
    geo = emit_e_core_geo_3d(_opt_6p14p_dims())
    assert 'Physical Surface("outer"' in geo


def test_emit_e_core_geo_3d_uses_boolean_difference() -> None:
    """OCC BooleanDifference вырезает windings из core и iron+windings из air."""
    geo = emit_e_core_geo_3d(_opt_6p14p_dims())
    # 2 actual operations + 1 comment mention = 3 total.
    assert 'iron_with_holes[] = BooleanDifference' in geo
    assert 'air_volume[] = BooleanDifference' in geo


def test_emit_e_core_geo_3d_omits_gaps_phase3b() -> None:
    """Phase 3b упрощение — gaps опущены (lateral coords extend за core)."""
    geo = emit_e_core_geo_3d(_opt_6p14p_dims())
    assert 'gap_center' not in geo
    assert 'gap_left' not in geo
    assert 'gap_right' not in geo


def test_emit_e_core_geo_3d_z_extent_includes_air_padding() -> None:
    """Outer air box extends in z by air_extent_factor_z × core_depth before/after."""
    dims = _opt_6p14p_dims()
    geo = emit_e_core_geo_3d(dims, air_extent_factor_z=2.0)
    # z_pad = 2 × 0.01495 = 0.0299; z_min = -0.0299, z_max = 0.04485
    assert '-0.0299' in geo
    assert '0.04485' in geo


def test_e_core_dimensions_from_pyom_processed_core() -> None:
    """`from_pyom_core` корректно извлекает поля из PyOM dict."""
    processed_core = {
        'processedDescription': {
            'width': 0.04215,
            'height': 0.042,
            'depth': 0.01495,
            'columns': [
                {  # column 0 — center
                    'width': 0.01195,
                    'height': 0.0303,
                    'coordinates': [0.0, 0.0, 0.0],
                },
                {  # column 1 — lateral
                    'width': 0.009075,
                    'height': 0.0303,
                    'coordinates': [-0.018088, 0.0, 0.0],
                },
            ],
            'windingWindows': [
                {'width': 0.009075, 'height': 0.0303},
            ],
        },
        'functionalDescription': {
            'gapping': [{'length': 0.0001}],
        },
    }
    dims = ECoreDimensions.from_pyom_core(processed_core)
    assert dims.core_w == 0.04215
    assert dims.lateral_x == 0.018088
    assert dims.gap_len == 0.0001


def test_read_initial_permeability_from_list_form() -> None:
    """PyOM list-form permeability.initial — берём первое entry."""
    mat = {'permeability': {'initial': [{'value': 8000.0, 'frequency': 1000}]}}
    assert math.isclose(read_initial_permeability(mat, 'Nanoperm'), 8000.0)


def test_read_initial_permeability_from_dict_form() -> None:
    """PyOM scalar-dict form (older catalogues) — supported as fallback."""
    mat = {'permeability': {'initial': {'value': 5000.0}}}
    assert math.isclose(read_initial_permeability(mat, 'Nanoperm'), 5000.0)


def test_read_initial_permeability_missing_field_raises_lookup() -> None:
    mat: dict[str, Any] = {'permeability': {}}
    with pytest.raises(LookupError, match='permeability.initial отсутствует'):
        read_initial_permeability(mat, 'BogusMaterial')


def test_read_initial_permeability_null_value_raises_lookup() -> None:
    mat = {'permeability': {'initial': [{'value': None}]}}
    with pytest.raises(LookupError, match='is null'):
        read_initial_permeability(mat, 'BogusMaterial')


def test_read_saturation_flux_density_from_list_form() -> None:
    mat = {'saturation': [{'magneticFluxDensity': 1.8, 'temperature': 25}]}
    assert math.isclose(read_saturation_flux_density(mat, 'Nanoperm'), 1.8)


def test_read_saturation_flux_density_missing_raises_lookup() -> None:
    with pytest.raises(LookupError, match='saturation отсутствует'):
        read_saturation_flux_density({}, 'BogusMaterial')


def test_extract_frohlich_params_finds_material_by_name() -> None:
    """End-to-end PyOM-like dict — extract_frohlich_params собирает оба параметра."""

    class FakePyOM:
        @staticmethod
        def get_core_materials() -> list[dict[str, Any]]:
            return [
                {'name': 'Other', 'permeability': {'initial': [{'value': 2000}]},
                 'saturation': [{'magneticFluxDensity': 1.2}]},
                {'name': 'Nanoperm', 'permeability': {'initial': [{'value': 8000}]},
                 'saturation': [{'magneticFluxDensity': 1.8}]},
            ]

    mu, b_sat = extract_frohlich_params(FakePyOM, 'Nanoperm')
    assert math.isclose(mu, 8000.0)
    assert math.isclose(b_sat, 1.8)


def test_extract_frohlich_params_missing_material_raises_lookup() -> None:
    class EmptyPyOM:
        @staticmethod
        def get_core_materials() -> list[dict[str, Any]]:
            return []

    with pytest.raises(LookupError, match='не найден в PyOM catalog'):
        extract_frohlich_params(EmptyPyOM, 'Nanoperm')
