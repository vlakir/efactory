"""Domain: MagneticComponent / MagneticVerificationResult (T113 Phase 2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.magnetic import (
    DEFAULT_DISCREPANCY_THRESHOLD,
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    MagneticVerificationResult,
    OperatingPoint,
    Winding,
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
