"""
Off-grid endpoint diagnostics + snap-to-grid domain layer (T187).

`snap_to_grid(value, grid_mm)` — pure function used both by the
`Schematic` facade (snap-on-write of component / wire / label
positions) and by the off-grid detector (compute `nearest_grid` for
each ERC `endpoint_off_grid` violation).

`OffGridEndpoint` / `OffGridReport` mirror the shape of the T029 ERC
report but specialise on a single violation type and add per-endpoint
`nearest_grid` + `delta_mm` for human-readable diagnostics.

`OffGridPositionError` is raised when `EFACTORY_STRICT_GRID=1` is
active and a builder tries to place a component off the connection
grid — diagnostic for builder authors, never raised in production.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, NewType

from pydantic import BaseModel, ConfigDict, computed_field

_FROZEN = ConfigDict(frozen=True, extra='forbid')

DEFAULT_CONNECTION_GRID_MM: float = 1.27
"""KiCad ≥ 8 connection-grid step (50 mil). ERC `endpoint_off_grid`
fires for any pin / wire endpoint not on this lattice."""

GridStepMm = NewType('GridStepMm', float)
"""Semantic alias for «mm distance between connection-grid nodes»."""

EndpointKind = Literal['pin', 'wire', 'label', 'pwr-flag', 'no-connect']


def snap_to_grid(value: float, grid_mm: float = DEFAULT_CONNECTION_GRID_MM) -> float:
    """
    Round `value` to the nearest multiple of `grid_mm`.

    Idempotent: ``snap_to_grid(snap_to_grid(x)) == snap_to_grid(x)``.
    Stable against float jitter: ``snap_to_grid(1.27 ± 1e-12) == 1.27``.
    Pipeline order in facade: rotation → ``_round_grid`` (FP-jitter
    clean to 0.01 mm) → ``snap_to_grid`` (force to connection grid).

    Raises ``ValueError`` for non-positive ``grid_mm``.
    """
    if grid_mm <= 0:
        msg = f'grid_mm must be > 0, got {grid_mm}'
        raise ValueError(msg)
    return round(value / grid_mm) * grid_mm


class OffGridEndpoint(BaseModel):
    model_config = _FROZEN

    kind: EndpointKind
    description: str
    pos: tuple[float, float]
    nearest_grid: tuple[float, float]
    delta_mm: tuple[float, float]
    uuid: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_abs_delta_mm(self) -> float:
        """Larger of |Δx|, |Δy| — used to sort priority of manual fix."""
        return max(abs(self.delta_mm[0]), abs(self.delta_mm[1]))


class OffGridReport(BaseModel):
    model_config = _FROZEN

    kicad_version: str
    schematic_path: Path
    timestamp: datetime
    grid_step_mm: GridStepMm
    endpoints: list[OffGridEndpoint]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.endpoints)


class OffGridPositionError(Exception):
    """
    Builder tried to place a component / wire / label off connection grid.

    Raised only when ``EFACTORY_STRICT_GRID=1`` is active. Default mode
    silently snaps the position. Diagnostic for builder authors, never
    surfaces in production runtime.
    """

    def __init__(
        self,
        *,
        component_name: str,
        requested: tuple[float, float],
        snapped: tuple[float, float],
        delta_mm: tuple[float, float],
    ) -> None:
        self.component_name = component_name
        self.requested = requested
        self.snapped = snapped
        self.delta_mm = delta_mm
        super().__init__(
            f'{component_name} placed off connection grid: '
            f'requested ({requested[0]}, {requested[1]}), '
            f'nearest ({snapped[0]}, {snapped[1]}), '
            f'Δ ({delta_mm[0]:+.4f}, {delta_mm[1]:+.4f}) mm'
        )
