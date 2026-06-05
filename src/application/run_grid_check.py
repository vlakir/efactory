"""
run_grid_check use case (T187) — off-grid endpoint diagnostic.

Reuses the T029 ``ErcRunner`` to fetch all ERC violations via ``kicad-cli
sch erc``, then filters to ``type == "endpoint_off_grid"`` and rebuilds
them as ``OffGridEndpoint``-s with nearest-grid + delta metadata.

**Not a gate.** Off-grid endpoints don't block downstream simulation
(T029 ERC quality gate covers hard-errors). This use case ships a
read-only diagnostic report and a non-zero exit-code for CLI usage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from domain.grid import (
    DEFAULT_CONNECTION_GRID_MM,
    GridStepMm,
    OffGridEndpoint,
    OffGridReport,
    snap_to_grid,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.erc import ErcItem
    from domain.grid import EndpointKind
    from ports.outbound.erc import ErcRunner
    from ports.outbound.grid import GridReportWriter


_OFF_GRID_TYPE: Final[str] = 'endpoint_off_grid'
_DEFAULT_GRID_STEP: Final[GridStepMm] = GridStepMm(DEFAULT_CONNECTION_GRID_MM)


def _classify_kind(description: str) -> EndpointKind:
    """
    Infer endpoint kind from KiCad's localised description prefix.

    KiCad localises descriptions to the active locale, but the leading
    structural tokens stay stable enough to discriminate ``Symbol …`` vs
    wire (``Horizontal/Vertical wire …``) vs label / no-connect markers.
    Falls back to ``wire`` for unknown shapes — safe default for ERC
    output that always carries either symbol-prefixed pin or wire stub.
    """
    head = description.strip()
    if head.startswith('Symbol '):
        # PWR / FLG references are pin-derived but live on a dedicated
        # power-port symbol — bucket them separately so the report can
        # group similar visual artefacts.
        if '#PWR' in head or '#FLG' in head:
            return 'pwr-flag'
        return 'pin'
    head_lower = head.lower()
    if 'label' in head_lower:
        return 'label'
    if 'no_connect' in head_lower or 'no-connect' in head_lower:
        return 'no-connect'
    return 'wire'


def _to_endpoint(item: ErcItem, grid_mm: float) -> OffGridEndpoint:
    x, y = item.pos
    nearest = (snap_to_grid(x, grid_mm=grid_mm), snap_to_grid(y, grid_mm=grid_mm))
    delta = (x - nearest[0], y - nearest[1])
    return OffGridEndpoint(
        kind=_classify_kind(item.description),
        description=item.description,
        pos=(x, y),
        nearest_grid=nearest,
        delta_mm=delta,
        uuid=item.uuid,
    )


async def run_grid_check(
    *,
    schematic: Path,
    project_root: Path | None,
    erc_runner: ErcRunner,
    report_writer: GridReportWriter | None = None,
    timeout_seconds: float = 30.0,
    grid_step_mm: GridStepMm = _DEFAULT_GRID_STEP,
) -> OffGridReport:
    erc_report = await erc_runner.run(schematic, timeout_seconds=timeout_seconds)

    endpoints: list[OffGridEndpoint] = [
        _to_endpoint(item, float(grid_step_mm))
        for violation in erc_report.violations
        if violation.type == _OFF_GRID_TYPE
        for item in violation.items
    ]

    report = OffGridReport(
        kicad_version=erc_report.kicad_version,
        schematic_path=erc_report.schematic_path,
        timestamp=erc_report.timestamp,
        grid_step_mm=grid_step_mm,
        endpoints=endpoints,
    )

    if report_writer is not None and report.count > 0:
        out_root = (project_root or schematic.parent) / 'out' / 'grid-check'
        await report_writer.write(report, out_root)

    return report


__all__ = ['run_grid_check']
