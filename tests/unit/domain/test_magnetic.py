"""Domain: MagneticComponent / MagneticVerificationResult (T113 Phase 2).

T132 расширения: WindingSection / InterleavingPattern /
LeakageInductanceResult + MagneticComponent.section_layout.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.magnetic import (
    DEFAULT_DISCREPANCY_THRESHOLD,
    Core,
    GapType,
    InterleavingPattern,
    IsolationSide,
    LeakageInductanceResult,
    MagneticComponent,
    MagneticVerificationResult,
    OperatingPoint,
    Winding,
    WindingSection,
)


def _opt_6p14p_se() -> MagneticComponent:
    """Pilot fixture-style spec для OPT 6П14П SE (см. T113 Phase 1)."""
    return MagneticComponent(
        name='OPT 6П14П SE',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            gap_length_m=0.0001,  # 0.1 mm
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary',
                number_turns=100,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            name='1 kHz mid-band',
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
            primary_dc_bias_a=0.05,
            primary_ac_peak_a=0.01,
        ),
    )


def test_magnetic_component_pilot_fixture_constructs() -> None:
    c = _opt_6p14p_se()
    assert c.name == 'OPT 6П14П SE'
    assert c.core.gap_type is GapType.SUBTRACTIVE
    assert c.core.gap_length_m == pytest.approx(0.0001)
    assert len(c.windings) == 2


def test_primary_winding_accessor_returns_first_primary() -> None:
    c = _opt_6p14p_se()
    p = c.primary_winding
    assert p.name == 'primary'
    assert p.number_turns == 2500


def test_primary_winding_raises_when_no_primary() -> None:
    c = MagneticComponent(
        name='secondary-only weird',
        core=Core(shape_name='E 42/21/15', material_name='Nanoperm 8000'),
        windings=(
            Winding(
                name='lonely',
                number_turns=10,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=50.0,
            primary_peak_voltage_v=220.0,
        ),
    )
    with pytest.raises(ValueError, match='no primary winding'):
        _ = c.primary_winding


def test_zero_turns_winding_rejected() -> None:
    with pytest.raises(ValidationError):
        Winding(name='zero', number_turns=0, isolation_side=IsolationSide.PRIMARY)


def test_empty_windings_tuple_rejected() -> None:
    with pytest.raises(ValidationError):
        MagneticComponent(
            name='no-coils',
            core=Core(shape_name='E 42/21/15', material_name='Nanoperm 8000'),
            windings=(),
            operating_point=OperatingPoint(
                frequency_hz=1000.0,
                primary_peak_voltage_v=10.0,
            ),
        )


def test_component_is_frozen_immutable() -> None:
    c = _opt_6p14p_se()
    with pytest.raises(ValidationError):
        c.name = 'mutated'  # type: ignore[misc]


def test_extra_field_in_core_rejected() -> None:
    with pytest.raises(ValidationError):
        Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            unknown_field=42,
        )


def test_verification_result_minimal_analytical_only() -> None:
    r = MagneticVerificationResult(
        component_name='opt-test',
        analytical_inductance_h=6.96,
    )
    assert r.analytical_inductance_h == pytest.approx(6.96)
    assert r.fem_inductance_h is None
    assert r.relative_difference is None
    assert r.discrepancy_flagged is False
    assert r.discrepancy_threshold == pytest.approx(DEFAULT_DISCREPANCY_THRESHOLD)


def test_verification_result_with_fem_within_threshold() -> None:
    r = MagneticVerificationResult(
        component_name='opt-test',
        analytical_inductance_h=6.96,
        fem_inductance_h=7.2,
        relative_difference=0.0345,
        discrepancy_flagged=False,
    )
    assert r.fem_inductance_h == pytest.approx(7.2)
    assert r.discrepancy_flagged is False


def test_verification_result_flagged_when_above_threshold() -> None:
    r = MagneticVerificationResult(
        component_name='opt-test',
        analytical_inductance_h=6.96,
        fem_inductance_h=23.78,
        relative_difference=2.42,
        discrepancy_flagged=True,
    )
    assert r.discrepancy_flagged is True


# ----------------------------------------------------------------------
# T132: WindingSection / InterleavingPattern / LeakageInductanceResult
# ----------------------------------------------------------------------


def _sandwich_5_section() -> InterleavingPattern:
    """5-section P-S-P-S-P sandwich (типовой hi-end audio OPT)."""
    return InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
            WindingSection(winding_name='primary'),
        ),
    )


def test_winding_section_minimal_constructs() -> None:
    s = WindingSection(winding_name='primary')
    assert s.winding_name == 'primary'
    assert s.layer_count is None


def test_winding_section_layer_count_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        WindingSection(winding_name='primary', layer_count=0)


def test_winding_section_empty_name_rejected() -> None:
    with pytest.raises(ValidationError):
        WindingSection(winding_name='')


def test_winding_section_is_frozen() -> None:
    s = WindingSection(winding_name='primary')
    with pytest.raises(ValidationError):
        s.winding_name = 'mutated'  # type: ignore[misc]


def test_interleaving_pattern_constructs_with_defaults() -> None:
    p = _sandwich_5_section()
    assert len(p.sections) == 5
    assert p.inter_section_thickness_m == pytest.approx(25e-6)
    assert p.bobbin_margin_m == pytest.approx(0.001)


def test_interleaving_pattern_exposes_pattern_as_names() -> None:
    p = _sandwich_5_section()
    assert p.pattern == ('primary', 'secondary', 'primary', 'secondary', 'primary')


def test_interleaving_pattern_empty_sections_rejected() -> None:
    with pytest.raises(ValidationError):
        InterleavingPattern(sections=())


def test_interleaving_pattern_negative_margin_rejected() -> None:
    with pytest.raises(ValidationError):
        InterleavingPattern(
            sections=(WindingSection(winding_name='primary'),),
            bobbin_margin_m=-0.001,
        )


def test_interleaving_pattern_is_frozen() -> None:
    p = _sandwich_5_section()
    with pytest.raises(ValidationError):
        p.bobbin_margin_m = 0.002  # type: ignore[misc]


def test_leakage_result_minimal_constructs() -> None:
    r = LeakageInductanceResult(
        source_winding='primary',
        leakage_to={'secondary': 5e-3},
        coupling_factor=0.998,
    )
    assert r.source_winding == 'primary'
    assert r.leakage_to == {'secondary': pytest.approx(5e-3)}
    assert r.coupling_factor == pytest.approx(0.998)


def test_leakage_result_coupling_factor_above_one_rejected() -> None:
    with pytest.raises(ValidationError):
        LeakageInductanceResult(
            source_winding='primary',
            leakage_to={'secondary': 1e-3},
            coupling_factor=1.5,
        )


def test_leakage_result_empty_leakage_to_rejected() -> None:
    with pytest.raises(ValidationError):
        LeakageInductanceResult(
            source_winding='primary',
            leakage_to={},
            coupling_factor=0.99,
        )


def test_leakage_result_is_frozen() -> None:
    r = LeakageInductanceResult(
        source_winding='primary',
        leakage_to={'secondary': 5e-3},
        coupling_factor=0.998,
    )
    with pytest.raises(ValidationError):
        r.coupling_factor = 0.5  # type: ignore[misc]


def test_magnetic_component_default_layout_is_none() -> None:
    c = _opt_6p14p_se()
    assert c.section_layout is None


def test_magnetic_component_accepts_valid_section_layout() -> None:
    layout = _sandwich_5_section()
    c = MagneticComponent(
        name='OPT 6П14П interleaved',
        core=Core(shape_name='E 42/21/15', material_name='Nanoperm 8000'),
        windings=(
            Winding(
                name='primary',
                number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary',
                number_turns=100,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
        ),
        section_layout=layout,
    )
    assert c.section_layout is not None
    assert c.section_layout.pattern == (
        'primary',
        'secondary',
        'primary',
        'secondary',
        'primary',
    )


def test_magnetic_component_rejects_layout_with_unknown_winding_name() -> None:
    with pytest.raises(ValidationError, match='unknown winding'):
        MagneticComponent(
            name='OPT mismatched layout',
            core=Core(shape_name='E 42/21/15', material_name='Nanoperm 8000'),
            windings=(
                Winding(
                    name='primary',
                    number_turns=2500,
                    isolation_side=IsolationSide.PRIMARY,
                ),
                Winding(
                    name='secondary',
                    number_turns=100,
                    isolation_side=IsolationSide.SECONDARY,
                ),
            ),
            operating_point=OperatingPoint(
                frequency_hz=1000.0,
                primary_peak_voltage_v=250.0,
            ),
            section_layout=InterleavingPattern(
                sections=(
                    WindingSection(winding_name='primary'),
                    WindingSection(winding_name='tertiary_typo'),
                ),
            ),
        )
