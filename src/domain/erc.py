"""
ERC quality gate domain layer (T029).

`kicad-cli sch erc --format json` violations parsed into frozen VO
aggregates. ERC errors block downstream `design_to_sim` via
`ErcErrorsFoundError`; warnings render to markdown but don't block.

Severities mirror KiCad's reporting (error / warning / exclusion).
Counts are computed over per-violation items so that downstream stdout
matches operator intuition (`0 errors, 25 warnings` reflects 25 actual
schematic locations, not 25 distinct violation types).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, computed_field

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class ErcSeverity(StrEnum):
    ERROR = 'error'
    WARNING = 'warning'
    EXCLUSION = 'exclusion'


class ErcItem(BaseModel):
    model_config = _FROZEN

    description: str
    pos: tuple[float, float]
    uuid: str


class ErcViolation(BaseModel):
    model_config = _FROZEN

    severity: ErcSeverity
    type: str
    description: str
    items: list[ErcItem]


class ErcIgnoredCheck(BaseModel):
    model_config = _FROZEN

    key: str
    description: str


class ErcReport(BaseModel):
    model_config = _FROZEN

    kicad_version: str
    schematic_path: Path
    timestamp: datetime
    violations: list[ErcViolation]
    ignored_checks: list[ErcIgnoredCheck]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_count(self) -> int:
        return self._count(ErcSeverity.ERROR)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warning_count(self) -> int:
        return self._count(ErcSeverity.WARNING)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def exclusion_count(self) -> int:
        return self._count(ErcSeverity.EXCLUSION)

    def _count(self, severity: ErcSeverity) -> int:
        return sum(len(v.items) or 1 for v in self.violations if v.severity is severity)


class ErcErrorsFoundError(Exception):
    """
    Raised when ERC reports at least one `severity=error` violation.

    Carries the full `ErcReport` so callers can render the markdown report
    or surface counts in stdout without re-running ERC.
    """

    def __init__(self, report: ErcReport) -> None:
        self.report = report
        super().__init__(
            f'ERC errors: {report.error_count} (schematic={report.schematic_path})'
        )


class KiCadCliUnavailableError(Exception):
    """`kicad-cli` binary not found in PATH."""


class ErcParseError(Exception):
    """Malformed JSON or missing/unsupported `$schema` key in ERC output."""


class ErcTimeoutError(Exception):
    """`kicad-cli sch erc` subprocess exceeded the configured timeout."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f'kicad-cli sch erc timed out after {timeout_seconds:g}s')


class SchematicParseError(Exception):
    """`kicad-cli` could not parse the schematic file (no JSON output)."""

    def __init__(self, *, stderr: str) -> None:
        self.stderr = stderr
        super().__init__(f'kicad-cli failed to parse schematic: {stderr}')
