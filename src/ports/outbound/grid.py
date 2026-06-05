"""
Off-grid report writer outbound port (T187).

`GridReportWriter` renders an ``OffGridReport`` to disk (markdown +
sidecar raw artefacts if needed). Symmetric с ``ErcReportWriter`` из
T029 — separate types для clean separation between ERC и grid
diagnostics (Plan B: «one tool one job»).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.grid import OffGridReport


class GridReportWriter(Protocol):
    async def write(
        self,
        report: OffGridReport,
        out_root: Path,
    ) -> Path: ...
