"""Unit tests для `FileSystemRawWaveforms` adapter (T190)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.outbound.raw_waveforms_filesystem.adapter import (
    FileSystemRawWaveforms,
)
from domain.raw_waveform import RawWaveform, WaveformAnalysisType
from ports.outbound.raw_waveforms import (
    RawWaveformReadFailedError,
    RawWaveformWriteFailedError,
)


def _make_tran(
    *,
    timestamp: str = '2026-06-06T01:30:00Z',
    source_netlist: str = 'amp.cir',
) -> RawWaveform:
    return RawWaveform(
        timestamp=timestamp,
        analysis_type=WaveformAnalysisType.TRAN,
        source_netlist=source_netlist,
        x_axis_name='time',
        x_axis=(0.0, 1e-6, 2e-6),
        traces={'v(out)': (0.0, 0.1, 0.2)},
    )


def _make_ac(timestamp: str = '2026-06-06T01:30:00Z') -> RawWaveform:
    return RawWaveform(
        timestamp=timestamp,
        analysis_type=WaveformAnalysisType.AC,
        source_netlist='amp.cir',
        x_axis_name='frequency',
        x_axis=(10.0, 100.0, 1000.0),
        traces={'v(out)': (1.0, 0.9, 0.5)},
        traces_imag={'v(out)': (0.0, 0.1, 0.3)},
    )


@pytest.mark.asyncio
async def test_write_creates_sim_results_dir(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()

    written = await adapter.write(waveform=_make_tran(), project_root=project_root)

    sim_dir = project_root / '.efactory' / 'sim-results'
    assert sim_dir.is_dir()
    assert written.is_file()
    assert written.parent == sim_dir


@pytest.mark.asyncio
async def test_write_filename_format(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()

    written = await adapter.write(waveform=_make_tran(), project_root=project_root)

    assert written.name == '2026-06-06T01-30-00Z-tran.waveform.json'


@pytest.mark.asyncio
async def test_write_content_matches_model(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()
    waveform = _make_ac()

    written = await adapter.write(waveform=waveform, project_root=project_root)

    data = json.loads(written.read_text(encoding='utf-8'))
    assert data['schema_version'] == 1
    assert data['analysis_type'] == 'ac'
    assert data['x_axis'] == [10.0, 100.0, 1000.0]
    assert data['traces'] == {'v(out)': [1.0, 0.9, 0.5]}
    assert data['traces_imag'] == {'v(out)': [0.0, 0.1, 0.3]}


@pytest.mark.asyncio
async def test_write_fails_when_project_root_missing(tmp_path: Path) -> None:
    adapter = FileSystemRawWaveforms()
    with pytest.raises(RawWaveformWriteFailedError):
        await adapter.write(waveform=_make_tran(), project_root=tmp_path / 'ghost')


@pytest.mark.asyncio
async def test_write_no_partial_file_on_success(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()

    await adapter.write(waveform=_make_tran(), project_root=project_root)

    sim_dir = project_root / '.efactory' / 'sim-results'
    assert list(sim_dir.glob('*.tmp')) == []


@pytest.mark.asyncio
async def test_load_latest_returns_none_when_no_files(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()

    loaded = await adapter.load_latest(
        project_root=project_root,
        analysis_type=WaveformAnalysisType.TRAN,
    )
    assert loaded is None


@pytest.mark.asyncio
async def test_load_latest_roundtrip(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()
    original = _make_tran()
    await adapter.write(waveform=original, project_root=project_root)

    loaded = await adapter.load_latest(
        project_root=project_root,
        analysis_type=WaveformAnalysisType.TRAN,
    )
    assert loaded == original


@pytest.mark.asyncio
async def test_load_latest_picks_newest_by_timestamp(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()
    old = _make_tran(timestamp='2026-06-06T01:00:00Z', source_netlist='old.cir')
    new = _make_tran(timestamp='2026-06-06T02:00:00Z', source_netlist='new.cir')
    await adapter.write(waveform=old, project_root=project_root)
    await adapter.write(waveform=new, project_root=project_root)

    loaded = await adapter.load_latest(
        project_root=project_root,
        analysis_type=WaveformAnalysisType.TRAN,
    )
    assert loaded == new


@pytest.mark.asyncio
async def test_load_latest_filters_by_analysis_type(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()
    await adapter.write(waveform=_make_tran(), project_root=project_root)
    await adapter.write(waveform=_make_ac(), project_root=project_root)

    tran_loaded = await adapter.load_latest(
        project_root=project_root,
        analysis_type=WaveformAnalysisType.TRAN,
    )
    ac_loaded = await adapter.load_latest(
        project_root=project_root,
        analysis_type=WaveformAnalysisType.AC,
    )
    assert tran_loaded is not None
    assert tran_loaded.analysis_type == WaveformAnalysisType.TRAN
    assert ac_loaded is not None
    assert ac_loaded.analysis_type == WaveformAnalysisType.AC


@pytest.mark.asyncio
async def test_load_corrupted_raises(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    sim_dir = project_root / '.efactory' / 'sim-results'
    sim_dir.mkdir(parents=True)
    (sim_dir / '2026-06-06T01-00-00Z-tran.waveform.json').write_text(
        '{not valid json',
        encoding='utf-8',
    )
    adapter = FileSystemRawWaveforms()
    with pytest.raises(RawWaveformReadFailedError):
        await adapter.load_latest(
            project_root=project_root,
            analysis_type=WaveformAnalysisType.TRAN,
        )


@pytest.mark.asyncio
async def test_load_schema_mismatch_raises(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    sim_dir = project_root / '.efactory' / 'sim-results'
    sim_dir.mkdir(parents=True)
    (sim_dir / '2026-06-06T01-00-00Z-tran.waveform.json').write_text(
        json.dumps({'schema_version': 1, 'timestamp': 'x'}),
        encoding='utf-8',
    )
    adapter = FileSystemRawWaveforms()
    with pytest.raises(RawWaveformReadFailedError):
        await adapter.load_latest(
            project_root=project_root,
            analysis_type=WaveformAnalysisType.TRAN,
        )


@pytest.mark.asyncio
async def test_write_overwrites_same_timestamp(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    adapter = FileSystemRawWaveforms()
    first = _make_tran(source_netlist='first.cir')
    second = _make_tran(source_netlist='second.cir')

    await adapter.write(waveform=first, project_root=project_root)
    written = await adapter.write(waveform=second, project_root=project_root)

    data = json.loads(written.read_text(encoding='utf-8'))
    assert data['source_netlist'] == 'second.cir'
