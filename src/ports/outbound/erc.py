"""
ERC outbound ports (T029).

`ErcRunner` runs `kicad-cli sch erc` (or any equivalent implementation)
and returns an `ErcReport`. `ErcReportWriter` renders the report to
disk (markdown + raw JSON).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.erc import ErcReport


class ErcRunner(Protocol):
    async def run(
        self,
        schematic: Path,
        *,
        timeout_seconds: float,
    ) -> ErcReport: ...


class ErcReportWriter(Protocol):
    async def write(
        self,
        report: ErcReport,
        out_root: Path,
    ) -> Path: ...
