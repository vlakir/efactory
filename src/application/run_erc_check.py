"""
run_erc_check use case (T029).

Hard-gate: when `report.error_count > 0`, raises `ErcErrorsFoundError`
carrying the full report. The markdown report (if a writer is provided)
is rendered to disk **before** the exception is raised, so callers can
surface a path to the report alongside the error message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.erc import ErcErrorsFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.erc import ErcReport
    from ports.outbound.erc import ErcReportWriter, ErcRunner


async def run_erc_check(
    *,
    schematic: Path,
    project_root: Path | None,
    erc_runner: ErcRunner,
    report_writer: ErcReportWriter | None = None,
    timeout_seconds: float = 30.0,
) -> ErcReport:
    report = await erc_runner.run(schematic, timeout_seconds=timeout_seconds)

    if report_writer is not None:
        out_root = (project_root or schematic.parent) / 'out' / 'erc'
        await report_writer.write(report, out_root)

    if report.error_count > 0:
        raise ErcErrorsFoundError(report)

    return report


__all__ = ['run_erc_check']
