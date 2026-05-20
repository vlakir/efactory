"""Unit: emit_e_core_geo + ECoreDimensions (T113 Phase 2C, pure Python)."""

from __future__ import annotations

from adapters.outbound.fem_solver_getdp.geometry import (
    ECoreDimensions,
    emit_e_core_geo,
)


def _opt_6p14p_dims() -> ECoreDimensions:
    """Hardcoded dims из PyOM calculate_core_data на OPT 6П14П SE.

    Эти числа извлечены ранее (pilot Stage A geometry.json processed core)
    — используем как known-good input для unit-уровня без PyOM dependency.
    """
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


def test_e_core_dimensions_from_pyom_processed_core() -> None:
    """Конструктор `from_pyom_core` корректно извлекает поля."""
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
