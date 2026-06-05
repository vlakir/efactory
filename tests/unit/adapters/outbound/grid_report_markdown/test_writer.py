"""MarkdownGridReportWriter (T187) — rendering off-grid reports to markdown."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from adapters.outbound.grid_report_markdown.writer import MarkdownGridReportWriter
from domain.grid import GridStepMm, OffGridEndpoint, OffGridReport


def _report(
    endpoints: list[OffGridEndpoint] | None = None,
    *,
    schematic_name: str = 'sample.kicad_sch',
) -> OffGridReport:
    return OffGridReport(
        kicad_version='10.0.3',
        schematic_path=Path('/tmp') / schematic_name,
        timestamp=datetime(2026, 6, 5, 3, 30, 45, 123456, tzinfo=UTC),
        grid_step_mm=GridStepMm(1.27),
        endpoints=endpoints or [],
    )


def _endpoint(
    *,
    kind: str = 'pin',
    description: str = 'Symbol R3 Pin 1 [Passive, Line]',
    pos: tuple[float, float] = (99.06, 103.81),
    nearest_grid: tuple[float, float] = (99.06, 104.14),
    delta_mm: tuple[float, float] = (0.0, -0.33),
    uuid: str = 'aaa',
) -> OffGridEndpoint:
    return OffGridEndpoint(
        kind=kind,  # type: ignore[arg-type]
        description=description,
        pos=pos,
        nearest_grid=nearest_grid,
        delta_mm=delta_mm,
        uuid=uuid,
    )


async def test_writes_report_to_timestamped_directory(tmp_path: Path) -> None:
    writer = MarkdownGridReportWriter()
    report = _report([_endpoint()])
    out_path = await writer.write(report, tmp_path)
    assert out_path.exists()
    assert out_path.name == 'report.md'
    # Timestamp directory uses microseconds (T029 N2 collision-safety).
    assert '2026-06-05T03-30-45.123456' in str(out_path)


async def test_writes_header_with_metadata(tmp_path: Path) -> None:
    writer = MarkdownGridReportWriter()
    report = _report([_endpoint()])
    out_path = await writer.write(report, tmp_path)
    text = out_path.read_text(encoding='utf-8')
    assert '# Off-Grid Report — sample.kicad_sch' in text
    assert '- **Schematic:** /tmp/sample.kicad_sch' in text
    assert '- **KiCad version:** 10.0.3' in text
    assert '- **Connection grid:** 1.270 mm' in text
    assert '- **Off-grid endpoints:** 1' in text


async def test_clean_report_renders_celebratory_marker(tmp_path: Path) -> None:
    writer = MarkdownGridReportWriter()
    report = _report([])
    out_path = await writer.write(report, tmp_path)
    text = out_path.read_text(encoding='utf-8')
    assert '- **Off-grid endpoints:** 0' in text
    assert 'All pin / wire endpoints on connection grid.' in text
    assert '## Endpoints' not in text


async def test_endpoints_table_sorted_by_max_abs_delta_descending(
    tmp_path: Path,
) -> None:
    small = _endpoint(uuid='small', delta_mm=(0.0, 0.1))
    big = _endpoint(uuid='big', delta_mm=(-0.5, 0.0))
    mid = _endpoint(uuid='mid', delta_mm=(0.0, -0.33))

    writer = MarkdownGridReportWriter()
    out = await writer.write(_report([small, big, mid]), tmp_path)
    text = out.read_text(encoding='utf-8')

    # UUIDs should appear in order: big (0.5) → mid (0.33) → small (0.1)
    idx_big = text.find('big')
    idx_mid = text.find('mid')
    idx_small = text.find('small')
    assert 0 < idx_big < idx_mid < idx_small


async def test_endpoints_table_contains_expected_columns(tmp_path: Path) -> None:
    writer = MarkdownGridReportWriter()
    out = await writer.write(_report([_endpoint()]), tmp_path)
    text = out.read_text(encoding='utf-8')
    assert '| # | Kind | Description | Pos (mm) | Nearest grid (mm) | Δ (mm) | UUID |' in text
    # Row content for our single endpoint.
    assert '| 1 | pin |' in text
    assert '99.0600, 103.8100' in text
    assert '99.0600, 104.1400' in text
    assert '+0.0000, -0.3300' in text
    assert 'aaa' in text


async def test_writer_creates_directory_tree_if_missing(tmp_path: Path) -> None:
    writer = MarkdownGridReportWriter()
    target = tmp_path / 'does' / 'not' / 'exist'
    out = await writer.write(_report([_endpoint()]), target)
    assert out.exists()
    assert out.parent.parent == target
