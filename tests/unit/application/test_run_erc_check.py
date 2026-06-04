"""run_erc_check use case — fake runner / writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from application.run_erc_check import run_erc_check
from domain.erc import (
    ErcErrorsFoundError,
    ErcItem,
    ErcReport,
    ErcSeverity,
    ErcViolation,
)


def _item() -> ErcItem:
    return ErcItem(description='d', pos=(0.0, 0.0), uuid='u')


def _report(*, with_error: bool = False) -> ErcReport:
    violations: list[ErcViolation] = []
    if with_error:
        violations.append(
            ErcViolation(
                severity=ErcSeverity.ERROR,
                type='power_pin_not_driven',
                description='d',
                items=[_item()],
            ),
        )
    return ErcReport(
        kicad_version='10.0.3',
        schematic_path=Path('/tmp/sch.kicad_sch'),
        timestamp=datetime(2026, 6, 5, tzinfo=UTC),
        violations=violations,
        ignored_checks=[],
    )


@dataclass
class _FakeRunner:
    report: ErcReport
    last_schematic: Path | None = None
    last_timeout: float | None = None

    async def run(
        self,
        schematic: Path,
        *,
        timeout_seconds: float,
    ) -> ErcReport:
        self.last_schematic = schematic
        self.last_timeout = timeout_seconds
        return self.report


@dataclass
class _FakeWriter:
    target: Path = Path('/tmp/report.md')
    captured: list[tuple[ErcReport, Path]] = field(default_factory=list)

    async def write(self, report: ErcReport, out_root: Path) -> Path:
        self.captured.append((report, out_root))
        return self.target


async def test_returns_report_when_no_errors() -> None:
    runner = _FakeRunner(report=_report())

    result = await run_erc_check(
        schematic=Path('/tmp/sch.kicad_sch'),
        project_root=None,
        erc_runner=runner,
    )

    assert result.error_count == 0
    assert runner.last_schematic == Path('/tmp/sch.kicad_sch')
    assert runner.last_timeout == pytest.approx(30.0)


async def test_raises_when_errors_found_and_attaches_report() -> None:
    runner = _FakeRunner(report=_report(with_error=True))

    with pytest.raises(ErcErrorsFoundError) as excinfo:
        await run_erc_check(
            schematic=Path('/tmp/sch.kicad_sch'),
            project_root=None,
            erc_runner=runner,
        )
    assert excinfo.value.report.error_count == 1


async def test_writes_report_under_project_root_when_writer_provided() -> None:
    runner = _FakeRunner(report=_report())
    writer = _FakeWriter()

    await run_erc_check(
        schematic=Path('/proj/sub/sch.kicad_sch'),
        project_root=Path('/proj'),
        erc_runner=runner,
        report_writer=writer,
    )

    assert len(writer.captured) == 1
    _, out_root = writer.captured[0]
    assert out_root == Path('/proj/out/erc')


async def test_writer_falls_back_to_schematic_parent_when_no_root() -> None:
    runner = _FakeRunner(report=_report())
    writer = _FakeWriter()

    await run_erc_check(
        schematic=Path('/some/dir/sch.kicad_sch'),
        project_root=None,
        erc_runner=runner,
        report_writer=writer,
    )

    _, out_root = writer.captured[0]
    assert out_root == Path('/some/dir/out/erc')


async def test_writer_runs_before_error_is_raised() -> None:
    """The markdown report must be on disk even when errors are present."""
    runner = _FakeRunner(report=_report(with_error=True))
    writer = _FakeWriter()

    with pytest.raises(ErcErrorsFoundError):
        await run_erc_check(
            schematic=Path('/proj/sub/sch.kicad_sch'),
            project_root=Path('/proj'),
            erc_runner=runner,
            report_writer=writer,
        )

    assert len(writer.captured) == 1


async def test_timeout_passed_to_runner() -> None:
    runner = _FakeRunner(report=_report())

    await run_erc_check(
        schematic=Path('/tmp/sch.kicad_sch'),
        project_root=None,
        erc_runner=runner,
        timeout_seconds=15.0,
    )

    assert runner.last_timeout == pytest.approx(15.0)
