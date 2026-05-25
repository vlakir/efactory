"""Unit tests для `FileSystemSimResults` adapter (T016 Phase B)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.sim_results_filesystem.adapter import FileSystemSimResults
from domain.sim_results import AnalysisType, SimResult
from ports.outbound.sim_results import SimResultsWriteFailedError

if TYPE_CHECKING:
    pass


def _make_result(**overrides: object) -> SimResult:
    base = {
        'timestamp': '2026-05-25T14:30:00Z',
        'analysis_type': AnalysisType.TRAN,
        'source_file': 'amp.cir',
        'tool': 'ngspice',
        'duration_seconds': 1.5,
        'summary': 'tran ok',
    }
    base.update(overrides)
    return SimResult(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_write_creates_sim_results_dir(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()

    written = await adapter.write(result=_make_result(), project_root=project_root)

    sim_dir = project_root / '.efactory' / 'sim-results'
    assert sim_dir.is_dir()
    assert written.is_file()
    assert written.parent == sim_dir


@pytest.mark.asyncio
async def test_write_filename_format(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()

    written = await adapter.write(result=_make_result(), project_root=project_root)

    assert written.name == '2026-05-25T14-30-00Z-tran.json'


@pytest.mark.asyncio
async def test_write_content_matches_model(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()
    result = _make_result(metrics={'thd_percent': 9.6}, artefacts=['tran.log'])

    written = await adapter.write(result=result, project_root=project_root)

    data = json.loads(written.read_text(encoding='utf-8'))
    assert data['schema_version'] == 1
    assert data['analysis_type'] == 'tran'
    assert data['metrics'] == {'thd_percent': 9.6}
    assert data['artefacts'] == ['tran.log']
    assert data['summary'] == 'tran ok'


@pytest.mark.asyncio
async def test_write_overwrites_existing_same_timestamp(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()

    await adapter.write(result=_make_result(summary='first'), project_root=project_root)
    second = await adapter.write(
        result=_make_result(summary='second'), project_root=project_root
    )

    data = json.loads(second.read_text(encoding='utf-8'))
    assert data['summary'] == 'second'


@pytest.mark.asyncio
async def test_write_distinct_timestamps_keep_both(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()

    await adapter.write(
        result=_make_result(timestamp='2026-05-25T14:30:00Z', summary='a'),
        project_root=project_root,
    )
    await adapter.write(
        result=_make_result(timestamp='2026-05-25T15:45:30Z', summary='b'),
        project_root=project_root,
    )

    sim_dir = project_root / '.efactory' / 'sim-results'
    files = sorted(p.name for p in sim_dir.iterdir())
    assert files == [
        '2026-05-25T14-30-00Z-tran.json',
        '2026-05-25T15-45-30Z-tran.json',
    ]


@pytest.mark.asyncio
async def test_write_fails_when_project_root_missing(tmp_path: Path) -> None:
    project_root = tmp_path / 'ghost'
    adapter = FileSystemSimResults()

    with pytest.raises(SimResultsWriteFailedError):
        await adapter.write(result=_make_result(), project_root=project_root)


@pytest.mark.asyncio
async def test_write_filename_sanitizes_colon_in_timestamp(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()
    result = _make_result(
        timestamp='2026-05-25T14:30:00Z', analysis_type=AnalysisType.THD
    )

    written = await adapter.write(result=result, project_root=project_root)

    assert ':' not in written.name
    assert written.name == '2026-05-25T14-30-00Z-thd.json'


@pytest.mark.asyncio
async def test_write_no_partial_file_on_success(tmp_path: Path) -> None:
    """После успешной записи `.tmp` не должен остаться в sim-results dir."""
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemSimResults()

    await adapter.write(result=_make_result(), project_root=project_root)

    sim_dir = project_root / '.efactory' / 'sim-results'
    tmp_leftovers = list(sim_dir.glob('*.tmp'))
    assert tmp_leftovers == []
