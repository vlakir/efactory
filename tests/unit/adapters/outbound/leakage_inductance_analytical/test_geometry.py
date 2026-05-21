"""
Unit: PyOM-catalog geometry resolution (T132 Phase C).

Tests с FakePyOM stub, без зависимости от реального .so binding.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from adapters.outbound.leakage_inductance_analytical.geometry import (
    CoreGeometry,
    GeometryResolutionError,
    estimate_winding_thickness_m,
    resolve_core_geometry,
    resolve_wire_outer_diameter_m,
)
from domain.magnetic import (
    Core,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)


# ---------------------------------------------------------------------------
# FakePyOM — minimal stub для unit tests без real .so
# ---------------------------------------------------------------------------


class FakePyOM:
    """Stub PyOM module для controllable геометрии в тестах."""

    def __init__(
        self,
        *,
        core_full: dict[str, Any] | None = None,
        wires: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._core_full = core_full or _default_e42_15_core_full()
        self._wires = wires or _default_wires()
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def calculate_core_data(self, _core: Any, _process: bool) -> dict[str, Any]:  # noqa: FBT001
        self.calls.append(('calculate_core_data', ()))
        return self._core_full

    def find_wire_by_name(self, name: str) -> dict[str, Any]:
        self.calls.append(('find_wire_by_name', (name,)))
        if name not in self._wires:
            msg = f'fake-pyom: wire {name!r} not in catalog'
            raise KeyError(msg)
        return self._wires[name]


def _default_e42_15_core_full() -> dict[str, Any]:
    return {
        'functionalDescription': {
            'shape': {
                'name': 'E 42/21/15',
                'dimensions': {
                    'A': {'minimum': 0.0413, 'maximum': 0.043, 'nominal': None},
                    'C': {'minimum': 0.0147, 'maximum': 0.0152, 'nominal': None},
                    'F': {'minimum': 0.0117, 'maximum': 0.0122, 'nominal': None},
                },
            },
        },
        'processedDescription': {
            'depth': 0.01495,
            'width': 0.04215,
            'height': 0.042,
            'windingWindows': [
                {'height': 0.0273, 'width': 0.0074, 'area': 0.00020202},
            ],
        },
    }


def _default_wires() -> dict[str, dict[str, Any]]:
    return {
        'Round 0.224 - Grade 1': {
            'name': 'Round 0.224 - Grade 1',
            'outerDiameter': {
                'minimum': 0.000239,
                'maximum': 0.000252,
                'nominal': None,
            },
            'conductingDiameter': {'nominal': 0.000224},
        },
        'Round 0.5 - Grade 1': {
            'name': 'Round 0.5 - Grade 1',
            'outerDiameter': {'nominal': 0.000548},
            'conductingDiameter': {'nominal': 0.0005},
        },
    }


def _pilot_component() -> MagneticComponent:
    return MagneticComponent(
        name='OPT pilot',
        core=Core(
            shape_name='E 42/21/15',
            material_name='3C95',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
        ),
        windings=(
            Winding(
                name='primary', number_turns=200,
                isolation_side=IsolationSide.PRIMARY,
                wire_name='Round 0.224 - Grade 1',
            ),
            Winding(
                name='secondary', number_turns=20,
                isolation_side=IsolationSide.SECONDARY,
                wire_name='Round 0.5 - Grade 1',
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0, primary_peak_voltage_v=250.0,
        ),
    )


# ---------------------------------------------------------------------------
# resolve_wire_outer_diameter_m
# ---------------------------------------------------------------------------


def test_wire_outer_diameter_uses_nominal_when_present() -> None:
    pyom = FakePyOM()
    od = resolve_wire_outer_diameter_m(pyom, 'Round 0.5 - Grade 1')
    assert od == pytest.approx(0.000548)


def test_wire_outer_diameter_averages_min_max_when_no_nominal() -> None:
    pyom = FakePyOM()
    od = resolve_wire_outer_diameter_m(pyom, 'Round 0.224 - Grade 1')
    # avg(0.000239, 0.000252) = 0.0002455
    assert od == pytest.approx(0.0002455, rel=1e-6)


def test_wire_lookup_unknown_raises() -> None:
    pyom = FakePyOM()
    with pytest.raises(GeometryResolutionError, match='wire'):
        resolve_wire_outer_diameter_m(pyom, 'NONEXISTENT WIRE')


# ---------------------------------------------------------------------------
# resolve_core_geometry
# ---------------------------------------------------------------------------


def test_resolve_geometry_extracts_e42_15_dims() -> None:
    pyom = FakePyOM()
    component = _pilot_component()
    geom = resolve_core_geometry(pyom, component)

    assert isinstance(geom, CoreGeometry)
    # Column width F: avg(0.0117, 0.0122) = 0.01195
    assert geom.column_width_m == pytest.approx(0.01195, rel=1e-6)
    # Column depth: pd.depth = 0.01495 (stack length)
    assert geom.column_depth_m == pytest.approx(0.01495)
    # Window axial height (b_w) = 0.0273
    assert geom.window_height_m == pytest.approx(0.0273)
    # Window radial width = 0.0074
    assert geom.window_width_m == pytest.approx(0.0074)


def test_resolve_geometry_computes_mean_turn_length() -> None:
    """MLT ≈ 2*(column_w + column_d) (basic Hurley approximation)."""
    pyom = FakePyOM()
    component = _pilot_component()
    geom = resolve_core_geometry(pyom, component)

    # MLT_base = 2 * (0.01195 + 0.01495) = 0.0538 m
    expected_min = 2 * (0.01195 + 0.01495)
    # Allow extra π·winding-extent correction (formula may add it).
    assert geom.mean_turn_length_m >= expected_min
    # Sanity upper bound: < 0.10 m (10 cm) для compact E 42/15.
    assert geom.mean_turn_length_m < 0.10


def test_resolve_geometry_missing_winding_windows_raises() -> None:
    bad_core = _default_e42_15_core_full()
    bad_core['processedDescription']['windingWindows'] = []
    pyom = FakePyOM(core_full=bad_core)
    component = _pilot_component()
    with pytest.raises(GeometryResolutionError, match='windingWindows'):
        resolve_core_geometry(pyom, component)


def test_resolve_geometry_missing_shape_dimension_f_raises() -> None:
    bad_core = _default_e42_15_core_full()
    del bad_core['functionalDescription']['shape']['dimensions']['F']
    pyom = FakePyOM(core_full=bad_core)
    component = _pilot_component()
    with pytest.raises(GeometryResolutionError, match='F'):
        resolve_core_geometry(pyom, component)


# ---------------------------------------------------------------------------
# estimate_winding_thickness_m
# ---------------------------------------------------------------------------


def test_estimate_thickness_single_layer_fits() -> None:
    """100 turns × 0.25 mm wire в b_w=27.3 mm → 1 layer fits."""
    t = estimate_winding_thickness_m(
        total_turns=100,
        wire_outer_diameter_m=0.00025,
        window_height_m=0.0273,
    )
    # 100 turns @ 0.25 mm = 25 mm — fits в 27.3 mm single layer
    # thickness = 1 layer × 0.25 mm = 0.00025
    assert t == pytest.approx(0.00025, rel=1e-6)


def test_estimate_thickness_two_layers_needed() -> None:
    """200 turns × 0.25 mm → 2 layers (200 > 109 turns/layer)."""
    t = estimate_winding_thickness_m(
        total_turns=200,
        wire_outer_diameter_m=0.00025,
        window_height_m=0.0273,
    )
    # 27.3 / 0.25 = 109.2 → 109 turns/layer; ceil(200/109) = 2 layers
    # thickness = 2 × 0.00025 = 0.00050
    assert t == pytest.approx(0.00050, rel=1e-6)


def test_estimate_thickness_zero_turns_returns_zero() -> None:
    t = estimate_winding_thickness_m(
        total_turns=0,
        wire_outer_diameter_m=0.00025,
        window_height_m=0.0273,
    )
    assert t == 0.0


def test_estimate_thickness_wire_wider_than_window_raises() -> None:
    """Defensive: wire не помещается в окно даже на одной turn."""
    with pytest.raises(GeometryResolutionError, match='wire'):
        estimate_winding_thickness_m(
            total_turns=10,
            wire_outer_diameter_m=0.10,  # 10 cm wire в 27 mm window
            window_height_m=0.0273,
        )
