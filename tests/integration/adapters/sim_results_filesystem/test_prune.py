"""Integration tests для `FileSystemSimResults.prune` (T142).

Real filesystem операции — создаём sim-results файлы с известными
timestamps, прогоняем prune, проверяем что осталось.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adapters.outbound.sim_results_filesystem.adapter import FileSystemSimResults

_SIM_DIR = '.efactory/sim-results'


def _create_sim_result(
    project_root: Path,
    timestamp: str,
    analysis: str = 'op',
) -> Path:
    """Create a fake sim-result JSON file with given filename timestamp.

    Filename follows T016 convention: `<TIMESTAMP-safe>-<analysis>.json`
    где `:` заменён на `-` для POSIX-safe sortable.
    """
    sim_dir = project_root / _SIM_DIR
    sim_dir.mkdir(parents=True, exist_ok=True)
    ts_safe = timestamp.replace(':', '-')
    path = sim_dir / f'{ts_safe}-{analysis}.json'
    path.write_text(
        json.dumps({'timestamp': timestamp, 'analysis_type': analysis}),
        encoding='utf-8',
    )
    return path


# ────────── keep_last policy ──────────


async def test_prune_keep_last_deletes_older_files(tmp_path: Path) -> None:
    """20 файлов, keep_last=5 → удаляем 15."""
    for i in range(20):
        ts = f'2026-01-{i + 1:02d}T12:00:00Z'
        _create_sim_result(tmp_path, ts)

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_last=5)

    assert deleted == 15
    remaining = sorted((tmp_path / _SIM_DIR).iterdir())
    assert len(remaining) == 5
    # Newest 5 (Jan 16-20) preserved.
    names = [p.name for p in remaining]
    assert all('2026-01-2' in n or '2026-01-16' in n or '2026-01-17' in n
               or '2026-01-18' in n or '2026-01-19' in n
               for n in names)


async def test_prune_keep_last_zero_deletes_all(tmp_path: Path) -> None:
    """keep_last=0 → all files removed."""
    for i in range(3):
        _create_sim_result(tmp_path, f'2026-01-{i + 1:02d}T12:00:00Z')

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_last=0)

    assert deleted == 3
    assert not list((tmp_path / _SIM_DIR).iterdir())


async def test_prune_keep_last_more_than_existing(tmp_path: Path) -> None:
    """keep_last > N existing → no deletions."""
    for i in range(3):
        _create_sim_result(tmp_path, f'2026-01-{i + 1:02d}T12:00:00Z')

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_last=100)

    assert deleted == 0
    assert len(list((tmp_path / _SIM_DIR).iterdir())) == 3


# ────────── keep_days policy ──────────


async def test_prune_keep_days_uses_filename_timestamp(tmp_path: Path) -> None:
    """keep_days=7 → удаляем файлы старше 7 дней (по filename-timestamp)."""
    now_dt = datetime.now(UTC)
    old_dt = now_dt - timedelta(days=10)
    young_dt = now_dt - timedelta(days=3)

    _create_sim_result(tmp_path, old_dt.strftime('%Y-%m-%dT%H:%M:%SZ'))
    young = _create_sim_result(
        tmp_path, young_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
    )

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_days=7)

    assert deleted == 1
    remaining = list((tmp_path / _SIM_DIR).iterdir())
    assert len(remaining) == 1
    assert remaining[0].name == young.name


async def test_prune_keep_days_mtime_fallback_for_non_standard_name(
    tmp_path: Path,
) -> None:
    """Файл без parsable filename-timestamp → fallback на mtime."""
    sim_dir = tmp_path / _SIM_DIR
    sim_dir.mkdir(parents=True)
    legacy = sim_dir / 'legacy-no-timestamp.json'
    legacy.write_text('{}')

    # mtime = 10 days ago.
    now = time.time()
    os.utime(legacy, (now - 10 * 86400, now - 10 * 86400))

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_days=7)

    assert deleted == 1
    assert not list(sim_dir.iterdir())


async def test_prune_keep_days_filename_timestamp_fallback(
    tmp_path: Path,
) -> None:
    """Если timestamp в filename parsable — использовать его (вместо mtime).

    Это полезно когда файлы copied/moved (mtime изменился, но timestamp
    в имени отражает реальное время симуляции).
    """
    # Old by name: 100 days ago.
    now_dt = datetime.now(UTC)
    old_dt = now_dt - timedelta(days=100)
    old_ts = old_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    young_dt = now_dt - timedelta(days=2)
    young_ts = young_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    _create_sim_result(tmp_path, old_ts)
    _create_sim_result(tmp_path, young_ts)

    # Set mtime'ы к "сейчас" — БД должна полагаться на filename timestamp.
    for f in (tmp_path / _SIM_DIR).iterdir():
        os.utime(f, (time.time(), time.time()))

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_days=30)

    # 100-дневный файл удалён по filename-timestamp (~old < 30 days threshold).
    assert deleted == 1
    remaining = list((tmp_path / _SIM_DIR).iterdir())
    assert len(remaining) == 1
    assert young_ts.replace(':', '-') in remaining[0].name


# ────────── edge cases ──────────


async def test_prune_no_sim_results_dir(tmp_path: Path) -> None:
    """Если `.efactory/sim-results/` не существует → no-op."""
    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_last=10)
    assert deleted == 0


async def test_prune_skips_non_json_files(tmp_path: Path) -> None:
    """Сторонние файлы (`.txt`, `.bak`) — не удаляем."""
    sim_dir = tmp_path / _SIM_DIR
    sim_dir.mkdir(parents=True)
    for i in range(5):
        ts = f'2026-01-{i + 1:02d}T12:00:00Z'
        _create_sim_result(tmp_path, ts)
    (sim_dir / 'README.txt').write_text('keep me')
    (sim_dir / 'something.bak').write_text('backup')

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path, keep_last=2)

    assert deleted == 3  # 5 jsons - 2 kept = 3 deleted
    remaining_names = {p.name for p in sim_dir.iterdir()}
    assert 'README.txt' in remaining_names
    assert 'something.bak' in remaining_names


async def test_prune_no_options_uses_default(tmp_path: Path) -> None:
    """prune() без keep_last/keep_days → ничего не удаляет (no-op)."""
    for i in range(3):
        _create_sim_result(tmp_path, f'2026-01-{i + 1:02d}T12:00:00Z')

    repo = FileSystemSimResults()
    deleted = await repo.prune(project_root=tmp_path)

    assert deleted == 0
    assert len(list((tmp_path / _SIM_DIR).iterdir())) == 3


async def test_prune_validation_both_options_passed(tmp_path: Path) -> None:
    repo = FileSystemSimResults()
    with pytest.raises(ValueError, match='mutually exclusive'):
        await repo.prune(project_root=tmp_path, keep_last=10, keep_days=30)
