"""Unit `FileSystemMagneticResults` adapter (T189)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.outbound.magnetic_results_filesystem.adapter import (
    FileSystemMagneticResults,
    find_latest_magnetics_summary,
)
from domain.magnetic_summary import (
    MagneticsSummary,
    MagneticsSummaryCoreSection,
    MagneticsSummaryOperatingSection,
)
from ports.outbound.magnetic_results import MagneticResultsWriteFailedError


def _make(
    *,
    timestamp: str = '2026-06-06T01:30:00Z',
    component: str = 'OPT_6P14P_SE',
) -> MagneticsSummary:
    return MagneticsSummary(
        timestamp=timestamp,
        component_name=component,
        analytical_inductance_h=6.96,
        fem_inductance_h=7.5,
        relative_difference=0.0775,
        fem_method='linear',
        peak_flux_density_t=1.2,
        core=MagneticsSummaryCoreSection(
            shape_name='E42/15',
            material_name='M6X',
            gap_length_m=0.0002,
            gap_type='subtractive',
        ),
        operating_point=MagneticsSummaryOperatingSection(
            frequency_hz=1000.0,
            primary_peak_voltage_v=200.0,
            primary_dc_bias_a=0.05,
        ),
    )


@pytest.mark.asyncio
async def test_write_creates_ts_dir(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemMagneticResults()
    written = await adapter.write(summary=_make(), project_root=project_root)
    assert written.parent.parent == project_root / 'out' / 'fem'
    assert written.name == 'summary.json'
    assert written.is_file()


@pytest.mark.asyncio
async def test_write_content_matches_model(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemMagneticResults()
    written = await adapter.write(summary=_make(), project_root=project_root)
    data = json.loads(written.read_text(encoding='utf-8'))
    assert data['schema_version'] == 1
    assert data['component_name'] == 'OPT_6P14P_SE'
    assert data['analytical_inductance_h'] == 6.96
    assert data['fem_inductance_h'] == 7.5
    assert data['core']['shape_name'] == 'E42/15'
    assert data['operating_point']['frequency_hz'] == 1000.0


@pytest.mark.asyncio
async def test_write_fails_when_project_root_missing(tmp_path: Path) -> None:
    adapter = FileSystemMagneticResults()
    with pytest.raises(MagneticResultsWriteFailedError):
        await adapter.write(summary=_make(), project_root=tmp_path / 'ghost')


@pytest.mark.asyncio
async def test_write_no_partial_file_on_success(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemMagneticResults()
    await adapter.write(summary=_make(), project_root=project_root)
    fem_root = project_root / 'out' / 'fem'
    tmp_leftovers = list(fem_root.rglob('*.tmp'))
    assert tmp_leftovers == []


@pytest.mark.asyncio
async def test_find_latest_returns_none_when_no_files(tmp_path: Path) -> None:
    assert find_latest_magnetics_summary(tmp_path / 'ghost') is None


@pytest.mark.asyncio
async def test_find_latest_picks_newest_by_ts_dir(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemMagneticResults()
    await adapter.write(
        summary=_make(timestamp='2026-06-06T01:00:00Z'),
        project_root=project_root,
    )
    await adapter.write(
        summary=_make(timestamp='2026-06-06T02:00:00Z'),
        project_root=project_root,
    )
    latest = find_latest_magnetics_summary(project_root)
    assert latest is not None
    data = json.loads(latest.read_text(encoding='utf-8'))
    assert data['timestamp'] == '2026-06-06T02:00:00Z'
