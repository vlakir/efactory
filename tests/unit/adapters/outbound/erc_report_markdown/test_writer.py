"""MarkdownErcReportWriter unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.outbound.erc_report_markdown.writer import (
    MarkdownErcReportWriter,
)
from domain.erc import (
    ErcIgnoredCheck,
    ErcItem,
    ErcReport,
    ErcSeverity,
    ErcViolation,
)


def _ts() -> datetime:
    return datetime(2026, 6, 5, 0, 30, 45, 123456, tzinfo=UTC)


def _report(
    *,
    violations: list[ErcViolation] | None = None,
    ignored_checks: list[ErcIgnoredCheck] | None = None,
) -> ErcReport:
    return ErcReport(
        kicad_version='10.0.3',
        schematic_path=Path('/tmp/lpf.kicad_sch'),
        timestamp=_ts(),
        violations=violations or [],
        ignored_checks=ignored_checks or [],
    )


def _item(uuid: str = 'u1') -> ErcItem:
    return ErcItem(
        description='Symbol U1 Pin 1 [+, Input, Line]',
        pos=(0.8238, 0.7246),
        uuid=uuid,
    )


async def test_writes_report_with_microsecond_timestamp_dir(tmp_path: Path) -> None:
    report = _report()
    writer = MarkdownErcReportWriter()

    out = await writer.write(report, tmp_path)

    assert out.name == 'report.md'
    assert out.parent.name == '2026-06-05T00-30-45.123456'
    assert out.exists()


async def test_renders_summary_counts_in_header(tmp_path: Path) -> None:
    report = _report(
        violations=[
            ErcViolation(
                severity=ErcSeverity.ERROR,
                type='power_pin_not_driven',
                description='Input Power pin not driven.',
                items=[_item('u-err')],
            ),
            ErcViolation(
                severity=ErcSeverity.WARNING,
                type='endpoint_off_grid',
                description='Wire endpoint off grid',
                items=[_item('u-w1'), _item('u-w2')],
            ),
        ],
    )

    writer = MarkdownErcReportWriter()
    out = await writer.write(report, tmp_path)
    text = out.read_text(encoding='utf-8')

    assert '# ERC Report — lpf.kicad_sch' in text
    assert 'errors=1, warnings=2, exclusions=0' in text
    assert '## Violations' in text
    assert 'error: power_pin_not_driven (×1)' in text
    assert 'warning: endpoint_off_grid (×2)' in text
    assert 'Input Power pin not driven.' in text


async def test_renders_ignored_checks_section(tmp_path: Path) -> None:
    report = _report(
        ignored_checks=[
            ErcIgnoredCheck(
                key='single_global_label',
                description='Global label only appears once.',
            ),
        ],
    )

    writer = MarkdownErcReportWriter()
    out = await writer.write(report, tmp_path)
    text = out.read_text(encoding='utf-8')

    assert '## Ignored Checks' in text
    assert '`single_global_label`' in text
    assert 'Global label only appears once.' in text


async def test_clean_report_skips_violations_and_ignored_sections(
    tmp_path: Path,
) -> None:
    report = _report()
    writer = MarkdownErcReportWriter()
    out = await writer.write(report, tmp_path)
    text = out.read_text(encoding='utf-8')

    assert '## Violations' not in text
    assert '## Ignored Checks' not in text


@pytest.mark.parametrize(
    ('items', 'expected_count_marker'),
    [
        ([], '×1'),
        ([_item('a')], '×1'),
        ([_item('a'), _item('b'), _item('c')], '×3'),
    ],
)
async def test_violation_count_marker(
    tmp_path: Path,
    items: list[ErcItem],
    expected_count_marker: str,
) -> None:
    report = _report(
        violations=[
            ErcViolation(
                severity=ErcSeverity.WARNING,
                type='off_grid',
                description='off-grid',
                items=items,
            ),
        ],
    )
    writer = MarkdownErcReportWriter()
    out = await writer.write(report, tmp_path)
    text = out.read_text(encoding='utf-8')
    assert expected_count_marker in text
