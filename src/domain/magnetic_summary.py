"""
MagneticsSummary — persistent JSON snapshot mag_verify_field результата (T189).

Sidecar для `/export-sim-report` M-thin режима. Layout:
`<project>/out/fem/<ts>/summary.json`, schema_version=1.

Schema v1 определена явно (без расширения существующего
`MagneticVerificationResult`), чтобы downstream `MarkdownSimReportWriter`
читал из стабильного контракта (а не in-memory domain VO, который может
эволюционировать).

Domain-уровень — без знания о FS layout / JSON serialization (живут в
adapter).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MAGNETICS_SUMMARY_SCHEMA_VERSION: Literal[1] = 1

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class MagneticsSummaryCoreSection(BaseModel):
    """Core-под-секция в `MagneticsSummary` (snapshot для отчёта)."""

    model_config = _FROZEN

    shape_name: str = Field(min_length=1)
    material_name: str = Field(min_length=1)
    gap_length_m: Annotated[float, Field(ge=0.0)]
    gap_type: str = Field(min_length=1)


class MagneticsSummaryOperatingSection(BaseModel):
    """Operating-point под-секция (frequency + bias)."""

    model_config = _FROZEN

    frequency_hz: Annotated[float, Field(gt=0.0)]
    primary_peak_voltage_v: float
    primary_dc_bias_a: float


class MagneticsSummary(BaseModel):
    """JSON snapshot одного `mag_verify_field` запуска для T189 persistence."""

    model_config = _FROZEN

    schema_version: Literal[1] = MAGNETICS_SUMMARY_SCHEMA_VERSION
    timestamp: str = Field(min_length=1)
    component_name: str = Field(min_length=1)
    analytical_inductance_h: Annotated[float, Field(ge=0.0)]
    fem_inductance_h: float | None = None
    relative_difference: float | None = None
    fem_method: str | None = None
    peak_flux_density_t: float | None = None
    core: MagneticsSummaryCoreSection
    operating_point: MagneticsSummaryOperatingSection


__all__ = [
    'MAGNETICS_SUMMARY_SCHEMA_VERSION',
    'MagneticsSummary',
    'MagneticsSummaryCoreSection',
    'MagneticsSummaryOperatingSection',
]
