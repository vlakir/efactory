"""Use case `run_grid_check` (T187) — фильтрация ERC violations → OffGridReport."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from application.run_grid_check import run_grid_check
from domain.erc import ErcItem, ErcReport, ErcSeverity, ErcViolation
from domain.grid import GridStepMm, OffGridReport


class _StubErcRunner:
    def __init__(self, report: ErcReport) -> None:
        self._report = report
        self.calls: list[tuple[Path, float]] = []

    async def run(
        self,
        schematic: Path,
        *,
        timeout_seconds: float,
    ) -> ErcReport:
        self.calls.append((schematic, timeout_seconds))
        return self._report


class _RecordingWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[OffGridReport, Path]] = []

    async def write(self, report: OffGridReport, out_root: Path) -> Path:
        self.writes.append((report, out_root))
        return out_root / 'fake' / 'report.md'


def _erc_report(violations: list[ErcViolation]) -> ErcReport:
    return ErcReport(
        kicad_version='10.0.3',
        schematic_path=Path('/tmp/test.kicad_sch'),
        timestamp=datetime(2026, 6, 5, 3, 30, 0, tzinfo=UTC),
        violations=violations,
        ignored_checks=[],
    )


def _off_grid_violation(
    *,
    items: list[ErcItem] | None = None,
) -> ErcViolation:
    if items is None:
        items = [
            ErcItem(
                description='Symbol R3 Pin 1 [Passive, Line]',
                pos=(99.06, 103.81),
                uuid='aaa',
            ),
        ]
    return ErcViolation(
        severity=ErcSeverity.WARNING,
        type='endpoint_off_grid',
        description='Symbol pin or wire end off connection grid',
        items=items,
    )


def _other_violation() -> ErcViolation:
    return ErcViolation(
        severity=ErcSeverity.WARNING,
        type='unconnected_wire_endpoint',
        description='Wire endpoint unconnected',
        items=[ErcItem(description='wire X', pos=(0.0, 0.0), uuid='bbb')],
    )


async def test_run_grid_check_returns_off_grid_report() -> None:
    runner = _StubErcRunner(_erc_report([_off_grid_violation()]))
    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=None,
        erc_runner=runner,
    )
    assert isinstance(report, OffGridReport)
    assert report.count == 1
    assert report.kicad_version == '10.0.3'
    assert report.grid_step_mm == GridStepMm(1.27)


async def test_run_grid_check_filters_other_violation_types() -> None:
    runner = _StubErcRunner(
        _erc_report([_off_grid_violation(), _other_violation()]),
    )
    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=None,
        erc_runner=runner,
    )
    # Только off-grid endpoint счёл, не wire-dangling и не другие.
    assert report.count == 1
    assert report.endpoints[0].uuid == 'aaa'


async def test_run_grid_check_returns_zero_count_when_clean() -> None:
    runner = _StubErcRunner(_erc_report([]))
    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=None,
        erc_runner=runner,
    )
    assert report.count == 0


async def test_run_grid_check_computes_nearest_grid_and_delta() -> None:
    runner = _StubErcRunner(_erc_report([_off_grid_violation()]))
    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=None,
        erc_runner=runner,
    )
    ep = report.endpoints[0]
    # 99.06 / 1.27 = 78.0 → nearest 99.06 (on-grid X).
    # 103.81 / 1.27 = 81.74 → nearest 82*1.27 = 104.14 (off-grid Y, Δ=-0.33).
    assert ep.pos == (99.06, 103.81)
    assert ep.nearest_grid[0] == pytest.approx(99.06, abs=1e-9)
    assert ep.nearest_grid[1] == pytest.approx(104.14, abs=1e-9)
    assert ep.delta_mm[0] == pytest.approx(0.0, abs=1e-9)
    assert ep.delta_mm[1] == pytest.approx(-0.33, abs=1e-9)


async def test_run_grid_check_classifies_endpoint_kind() -> None:
    """Kind inferred from description prefix (Symbol → pin, wire → wire, ...)."""
    items = [
        ErcItem(description='Symbol R3 Pin 1 [Passive, Line]', pos=(0.5, 0.5), uuid='a'),
        ErcItem(description='Horizontal wire, length 0.1016 mm', pos=(0.5, 0.5), uuid='b'),
        ErcItem(description='Symbol #PWR01 Pin 1 [Power input]', pos=(0.5, 0.5), uuid='c'),
        ErcItem(description='Symbol #FLG01 Pin 1 [Power output]', pos=(0.5, 0.5), uuid='d'),
    ]
    violation = _off_grid_violation(items=items)
    runner = _StubErcRunner(_erc_report([violation]))
    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=None,
        erc_runner=runner,
    )
    kinds = [ep.kind for ep in report.endpoints]
    assert kinds == ['pin', 'wire', 'pwr-flag', 'pwr-flag']


async def test_run_grid_check_passes_schematic_and_timeout_to_runner() -> None:
    runner = _StubErcRunner(_erc_report([]))
    await run_grid_check(
        schematic=Path('/x.kicad_sch'),
        project_root=None,
        erc_runner=runner,
        timeout_seconds=42.0,
    )
    assert runner.calls == [(Path('/x.kicad_sch'), 42.0)]


async def test_run_grid_check_uses_custom_grid_step() -> None:
    runner = _StubErcRunner(_erc_report([_off_grid_violation()]))
    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=None,
        erc_runner=runner,
        grid_step_mm=GridStepMm(2.54),
    )
    assert report.grid_step_mm == GridStepMm(2.54)
    ep = report.endpoints[0]
    # 99.06 / 2.54 = 39.0 → nearest 99.06 ✓.
    # 103.81 / 2.54 = 40.87 → nearest 41*2.54 = 104.14.
    assert ep.nearest_grid[1] == pytest.approx(104.14, abs=1e-9)


async def test_run_grid_check_writes_report_when_writer_provided(
    tmp_path: Path,
) -> None:
    runner = _StubErcRunner(_erc_report([_off_grid_violation()]))
    writer = _RecordingWriter()
    project_root = tmp_path / 'project'
    project_root.mkdir()

    report = await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=project_root,
        erc_runner=runner,
        report_writer=writer,
    )

    assert len(writer.writes) == 1
    written_report, out_root = writer.writes[0]
    assert written_report is report
    assert out_root == project_root / 'out' / 'grid-check'


async def test_run_grid_check_writer_falls_back_to_schematic_parent(
    tmp_path: Path,
) -> None:
    runner = _StubErcRunner(_erc_report([_off_grid_violation()]))
    writer = _RecordingWriter()
    schematic = tmp_path / 'standalone.kicad_sch'
    schematic.write_text('stub', encoding='utf-8')

    await run_grid_check(
        schematic=schematic,
        project_root=None,
        erc_runner=runner,
        report_writer=writer,
    )

    _, out_root = writer.writes[0]
    assert out_root == tmp_path / 'out' / 'grid-check'


async def test_run_grid_check_does_not_write_when_clean(
    tmp_path: Path,
) -> None:
    """Optimisation: clean report → no report file."""
    runner = _StubErcRunner(_erc_report([]))
    writer = _RecordingWriter()
    project_root = tmp_path / 'p'
    project_root.mkdir()

    await run_grid_check(
        schematic=Path('/tmp/test.kicad_sch'),
        project_root=project_root,
        erc_runner=runner,
        report_writer=writer,
    )

    # Clean = 0 endpoints. No writer.write() call (it'd be noise).
    assert writer.writes == []
