"""Unit `MagneticsSummary` VO (T189)."""

from __future__ import annotations

import pytest

from domain.magnetic_summary import (
    MAGNETICS_SUMMARY_SCHEMA_VERSION,
    MagneticsSummary,
    MagneticsSummaryCoreSection,
    MagneticsSummaryOperatingSection,
)


def _minimal() -> MagneticsSummary:
    return MagneticsSummary(
        timestamp='2026-06-06T01:30:00Z',
        component_name='OPT_6P14P_SE',
        analytical_inductance_h=6.96,
        core=MagneticsSummaryCoreSection(
            shape_name='E42/15',
            material_name='M6X',
            gap_length_m=0.0002,
            gap_type='subtractive',
        ),
        operating_point=MagneticsSummaryOperatingSection(
            frequency_hz=1000.0,
            primary_peak_voltage_v=200.0,
            primary_dc_bias_a=0.05,
        ),
    )


def test_schema_version() -> None:
    s = _minimal()
    assert s.schema_version == MAGNETICS_SUMMARY_SCHEMA_VERSION == 1


def test_optional_fem_fields() -> None:
    s = _minimal()
    assert s.fem_inductance_h is None
    assert s.relative_difference is None
    assert s.fem_method is None
    assert s.peak_flux_density_t is None


def test_with_fem_fields() -> None:
    s = _minimal().model_copy(
        update={
            'fem_inductance_h': 23.78,
            'relative_difference': 2.42,
            'fem_method': 'linear',
            'peak_flux_density_t': 1.2,
        }
    )
    assert s.fem_inductance_h == 23.78


def test_frozen_immutable() -> None:
    s = _minimal()
    with pytest.raises(ValueError, match='[Ff]rozen|immutable'):
        s.timestamp = '2026-01-01T00:00:00Z'  # type: ignore[misc]


def test_negative_analytical_inductance_rejected() -> None:
    base = _minimal().model_dump(mode='json')
    base['analytical_inductance_h'] = -1.0
    with pytest.raises(ValueError):
        MagneticsSummary.model_validate(base)


def test_roundtrip_model_dump_validate() -> None:
    original = _minimal()
    restored = MagneticsSummary.model_validate(original.model_dump(mode='json'))
    assert restored == original
