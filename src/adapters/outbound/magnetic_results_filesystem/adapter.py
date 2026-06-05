"""
FileSystemMagneticResults — atomic-write `MagneticsSummary` JSON (T189).

Layout: `<project>/out/fem/<TIMESTAMP-safe>/summary.json`. Каждый запуск
получает свой `<ts>`-подкаталог, чтобы исторические summary'и не
перетирались. Latest определяется через `iter_summary_files` reader
(сортировка по имени каталога — `YYYYMMDDTHHMMSSZ` natural-sortable).

Атомарность: пишем сначала в `summary.json.tmp`, потом `Path.replace`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING

from ports.outbound.magnetic_results import MagneticResultsWriteFailedError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.magnetic_summary import MagneticsSummary


_FEM_SUBDIR = 'out/fem'
_SUMMARY_FILENAME = 'summary.json'


def _ts_dirname(timestamp: str) -> str:
    """Нормализовать `2026-06-06T01:30:00Z` → `20260606T013000Z` (POSIX-safe)."""
    return timestamp.replace(':', '').replace('-', '').replace('Z', 'Z')


def _write_sync(
    *,
    project_root: Path,
    ts_dir: Path,
    tmp_path: Path,
    final_path: Path,
    payload_text: str,
) -> None:
    if not project_root.is_dir():
        msg = f'project_root does not exist or is not a directory: {project_root}'
        raise MagneticResultsWriteFailedError(msg)
    try:
        ts_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f'cannot create fem ts-dir: {ts_dir}'
        raise MagneticResultsWriteFailedError(msg) from exc
    try:
        tmp_path.write_text(payload_text, encoding='utf-8')
        tmp_path.replace(final_path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        msg = f'failed to write magnetics summary: {final_path}'
        raise MagneticResultsWriteFailedError(msg) from exc


class FileSystemMagneticResults:
    """Persist `MagneticsSummary` в `<project>/out/fem/<ts>/summary.json`."""

    async def write(
        self,
        *,
        summary: MagneticsSummary,
        project_root: Path,
    ) -> Path:
        ts_dir = project_root / _FEM_SUBDIR / _ts_dirname(summary.timestamp)
        final_path = ts_dir / _SUMMARY_FILENAME
        tmp_path = ts_dir / f'{_SUMMARY_FILENAME}.tmp'
        payload_text = json.dumps(
            summary.model_dump(mode='json'),
            indent=2,
            sort_keys=True,
        )

        await asyncio.to_thread(
            _write_sync,
            project_root=project_root,
            ts_dir=ts_dir,
            tmp_path=tmp_path,
            final_path=final_path,
            payload_text=payload_text,
        )
        return final_path

    def find_latest(self, *, project_root: Path) -> Path | None:
        return find_latest_magnetics_summary(project_root)


def find_latest_magnetics_summary(project_root: Path) -> Path | None:
    """
    Найти latest `<project>/out/fem/<ts>/summary.json` (T189).

    Helper для `/export-sim-report` (без --rerun): сортировка по имени
    `<ts>`-каталога (формат `YYYYMMDDTHHMMSSZ` natural-sortable). Возвращает
    None если каталог отсутствует или пуст.
    """
    fem_root = project_root / _FEM_SUBDIR
    if not fem_root.is_dir():
        return None
    candidates = sorted(p for p in fem_root.iterdir() if p.is_dir())
    for ts_dir in reversed(candidates):
        summary_path = ts_dir / _SUMMARY_FILENAME
        if summary_path.is_file():
            return summary_path
    return None


__all__ = ['FileSystemMagneticResults', 'find_latest_magnetics_summary']
