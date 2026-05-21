"""Unit: PyOpenMagnetics adapter helpers (T132 Phase B).

Pure-Python тесты на private helper'ы без PyOM dependency:
- `_translate_pattern_to_indices`: name → tuple-position mapping.
- `_normalize_bobbin_columns`: defensive patch для PyOM bobbin null fields.
- `_parse_leakage_result`: PyOM result dict → LeakageInductanceResult VO.

Integration с реальным PyOM .so — в
`tests/integration/adapters/magnetic_analytics_pyopenmagnetics/`.
"""

from __future__ import annotations

import pytest

from adapters.outbound.magnetic_analytics_pyopenmagnetics.adapter import (
    _normalize_bobbin_columns,
    _parse_leakage_result,
    _translate_pattern_to_indices,
)
from domain.magnetic import (
    Core,
    InterleavingPattern,
    IsolationSide,
    LeakageInductanceResult,
    MagneticComponent,
    OperatingPoint,
    Winding,
    WindingSection,
)


def _two_winding_component() -> MagneticComponent:
    return MagneticComponent(
        name='OPT pilot',
        core=Core(shape_name='E 42/21/15', material_name='Nanoperm 8000'),
        windings=(
            Winding(
                name='primary',
                number_turns=3500,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary',
                number_turns=140,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
        ),
    )


# ---------------------------------------------------------------------------
# _translate_pattern_to_indices
# ---------------------------------------------------------------------------


def test_translate_pattern_2_section_p_s() -> None:
    component = _two_winding_component()
    layout = InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
        ),
    )
    assert _translate_pattern_to_indices(layout, component.windings) == [0, 1]


def test_translate_pattern_5_section_p_s_p_s_p() -> None:
    component = _two_winding_component()
    layout = InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
        ),
    )
    assert _translate_pattern_to_indices(layout, component.windings) == [0, 1, 0, 1, 0]


def test_translate_pattern_unknown_name_raises() -> None:
    """Hardening: helper не должен trust'ить, что MagneticComponent уже отвалидировал."""
    component = _two_winding_component()
    layout = InterleavingPattern.model_construct(
        sections=(WindingSection(winding_name='ghost'),),
        inter_section_thickness_m=25e-6,
        bobbin_margin_m=0.001,
    )
    with pytest.raises(ValueError, match='unknown winding'):
        _translate_pattern_to_indices(layout, component.windings)


# ---------------------------------------------------------------------------
# _normalize_bobbin_columns
# ---------------------------------------------------------------------------


def test_normalize_bobbin_fills_null_columns_from_winding_window() -> None:
    bobbin = {
        'name': 'Bobbin E42/15',
        'processedDescription': {'columnWidth': None, 'columnDepth': 5.45569116e-315},
        'functionalDescription': {'windingWindow': {'width': 0.0074, 'height': 0.0273}},
    }
    core_full = {'processedDescription': {'depth': 0.015}}

    patched = _normalize_bobbin_columns(bobbin, core_full)

    assert patched['processedDescription']['columnWidth'] == pytest.approx(0.0074)
    assert patched['processedDescription']['columnDepth'] == pytest.approx(0.015)


def test_normalize_bobbin_preserves_already_filled_columns() -> None:
    bobbin = {
        'name': 'Bobbin custom',
        'processedDescription': {'columnWidth': 0.005, 'columnDepth': 0.020},
        'functionalDescription': {'windingWindow': {'width': 0.0074, 'height': 0.0273}},
    }
    core_full = {'processedDescription': {'depth': 0.015}}

    patched = _normalize_bobbin_columns(bobbin, core_full)

    assert patched['processedDescription']['columnWidth'] == pytest.approx(0.005)
    assert patched['processedDescription']['columnDepth'] == pytest.approx(0.020)


def test_normalize_bobbin_fallback_when_core_lacks_depth() -> None:
    """Если core_full не содержит depth-like поля, используется E 42/15-class fallback."""
    bobbin = {
        'name': 'Bobbin E42/15',
        'processedDescription': {'columnWidth': None, 'columnDepth': None},
        'functionalDescription': {'windingWindow': {'width': 0.0074, 'height': 0.0273}},
    }
    core_full: dict[str, object] = {'processedDescription': {}}

    patched = _normalize_bobbin_columns(bobbin, core_full)

    # Fallback 0.015 m (E 42/15 stack length), documented в adapter docstring.
    assert patched['processedDescription']['columnDepth'] == pytest.approx(0.015)


def test_normalize_bobbin_returns_new_dict_not_mutation() -> None:
    bobbin = {
        'name': 'Bobbin E42/15',
        'processedDescription': {'columnWidth': None, 'columnDepth': None},
        'functionalDescription': {'windingWindow': {'width': 0.0074, 'height': 0.0273}},
    }
    core_full = {'processedDescription': {'depth': 0.015}}

    _normalize_bobbin_columns(bobbin, core_full)

    assert bobbin['processedDescription']['columnWidth'] is None


# ---------------------------------------------------------------------------
# _parse_leakage_result
# ---------------------------------------------------------------------------


def test_parse_leakage_result_two_winding() -> None:
    component = _two_winding_component()
    pyom_result = {
        'leakageInductancePerWinding': [
            {'nominal': 0.0, 'unit': None},
            {'nominal': 0.0001672, 'unit': None},
        ],
        'methodUsed': 'Energy',
        'origin': 'simulation',
    }
    # L_primary self-inductance из stub'а (consumer бы взял из mag_verify_field).
    l_self_primary_h = 50.0

    result = _parse_leakage_result(
        pyom_result,
        component=component,
        source_index=0,
        l_self_primary_h=l_self_primary_h,
    )

    assert isinstance(result, LeakageInductanceResult)
    assert result.source_winding == 'primary'
    assert result.leakage_to == {'secondary': pytest.approx(0.0001672)}
    # k = sqrt(1 - Lσ / L_self) → почти 1 для small Lσ
    assert result.coupling_factor == pytest.approx(
        (1.0 - 0.0001672 / l_self_primary_h) ** 0.5,
    )


def test_parse_leakage_result_clamps_coupling_factor_to_unit_interval() -> None:
    """Если Lσ почему-то > L_self, k clamp'ится к [0,1] без падения validation."""
    component = _two_winding_component()
    pyom_result = {
        'leakageInductancePerWinding': [
            {'nominal': 0.0},
            {'nominal': 100.0},  # absurd Lσ
        ],
    }
    result = _parse_leakage_result(
        pyom_result,
        component=component,
        source_index=0,
        l_self_primary_h=1.0,
    )
    assert result.coupling_factor == pytest.approx(0.0)


def test_parse_leakage_result_three_winding() -> None:
    """N=3 случай — source + 2 targets."""
    component = MagneticComponent(
        name='3w',
        core=Core(shape_name='E 42/21/15', material_name='Nanoperm 8000'),
        windings=(
            Winding(name='primary', number_turns=2000, isolation_side=IsolationSide.PRIMARY),
            Winding(name='ul_tap', number_turns=1000, isolation_side=IsolationSide.PRIMARY),
            Winding(name='secondary', number_turns=80, isolation_side=IsolationSide.SECONDARY),
        ),
        operating_point=OperatingPoint(frequency_hz=1000.0, primary_peak_voltage_v=250.0),
    )
    pyom_result = {
        'leakageInductancePerWinding': [
            {'nominal': 0.0},
            {'nominal': 0.5e-3},
            {'nominal': 5.0e-3},
        ],
    }
    result = _parse_leakage_result(
        pyom_result,
        component=component,
        source_index=0,
        l_self_primary_h=50.0,
    )
    assert result.source_winding == 'primary'
    assert set(result.leakage_to.keys()) == {'ul_tap', 'secondary'}
    assert result.leakage_to['ul_tap'] == pytest.approx(0.5e-3)
    assert result.leakage_to['secondary'] == pytest.approx(5.0e-3)
