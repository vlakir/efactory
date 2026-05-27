"""
FileSystemSimResults — записывает SimResult в `.efactory/sim-results/`.

Атомарность: пишем сначала в `*.json.tmp`, потом `Path.replace` на
финальное имя. Имя файла — `<TIMESTAMP-safe>-<analysis>.json`, где
`:` из ISO-8601 заменяется на `-`, чтобы получить sortable-by-filename
и POSIX-safe имя.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ports.outbound.sim_results import SimResultsWriteFailedError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.sim_results import SimResult


_SIM_RESULTS_SUBDIR = '.efactory/sim-results'

# Filename timestamp pattern: `YYYY-MM-DDTHH-MM-SSZ-<analysis>.json`
# (`:` уже заменён на `-` в `_filename_for`).
_FILENAME_TIMESTAMP_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)',
)
_SECONDS_PER_DAY = 86400


def _filename_for(result: SimResult) -> str:
    ts_safe = result.timestamp.replace(':', '-')
    return f'{ts_safe}-{result.analysis_type.value}.json'


def _write_sync(
    *,
    project_root: Path,
    sim_dir: Path,
    tmp_path: Path,
    final_path: Path,
    payload_text: str,
) -> None:
    if not project_root.is_dir():
        msg = f'project_root does not exist or is not a directory: {project_root}'
        raise SimResultsWriteFailedError(msg)
    try:
        sim_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f'cannot create sim-results dir: {sim_dir}'
        raise SimResultsWriteFailedError(msg) from exc
    try:
        tmp_path.write_text(payload_text, encoding='utf-8')
        tmp_path.replace(final_path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        msg = f'failed to write sim-result: {final_path}'
        raise SimResultsWriteFailedError(msg) from exc


class FileSystemSimResults:
    """Persist SimResult в `<project_root>/.efactory/sim-results/`."""

    async def write(
        self,
        *,
        result: SimResult,
        project_root: Path,
    ) -> Path:
        sim_dir = project_root / _SIM_RESULTS_SUBDIR
        filename = _filename_for(result)
        final_path = sim_dir / filename
        tmp_path = sim_dir / f'{filename}.tmp'
        payload_text = json.dumps(
            result.model_dump(mode='json'),
            indent=2,
            sort_keys=True,
        )

        await asyncio.to_thread(
            _write_sync,
            project_root=project_root,
            sim_dir=sim_dir,
            tmp_path=tmp_path,
            final_path=final_path,
            payload_text=payload_text,
        )
        return final_path

    async def prune(
        self,
        *,
        project_root: Path,
        keep_last: int | None = None,
        keep_days: int | None = None,
    ) -> int:
        """Apply retention policy (T142). Mutually exclusive keep_last/days."""
        if keep_last is not None and keep_days is not None:
            msg = 'keep_last and keep_days mutually exclusive'
            raise ValueError(msg)
        if keep_last is None and keep_days is None:
            return 0
        return await asyncio.to_thread(
            _prune_sync,
            sim_dir=project_root / _SIM_RESULTS_SUBDIR,
            keep_last=keep_last,
            keep_days=keep_days,
        )


def _file_age_seconds(path: Path, now: float) -> float:
    """Use filename timestamp если parsable, иначе fallback на mtime."""
    match = _FILENAME_TIMESTAMP_RE.match(path.name)
    if match is not None:
        ts_str = match.group(1).replace('-', ':', 2)  # restore yyyy-mm-dd separators
        # `YYYY-MM-DDTHH-MM-SSZ` → restore `:` в time part:
        # `YYYY-MM-DDTHH:MM-SSZ` after 2 replacements → wrong; чиним вручную.
        raw = match.group(1)  # YYYY-MM-DDTHH-MM-SSZ
        # Date part YYYY-MM-DD (keep `-`); time part HH-MM-SSZ (restore `:`).
        date_part = raw[:10]
        time_part = raw[11:].replace('-', ':')  # HH-MM-SSZ → HH:MM:SSZ
        ts_str = f'{date_part}T{time_part}'
        try:
            dt = datetime.strptime(ts_str, '%Y-%m-%dT%H:%M:%SZ').replace(
                tzinfo=UTC,
            )
        except ValueError:
            pass
        else:
            return now - dt.timestamp()
    return now - path.stat().st_mtime


def _prune_sync(
    *,
    sim_dir: Path,
    keep_last: int | None,
    keep_days: int | None,
) -> int:
    if not sim_dir.is_dir():
        return 0
    # Only JSON sim-results — skip README.txt, *.bak, *.tmp.
    json_files = sorted(
        p for p in sim_dir.iterdir() if p.is_file() and p.suffix == '.json'
    )
    to_delete: list[Path] = []
    if keep_last is not None:
        # Sorted ascending → newest at end. Keep last N.
        if len(json_files) > keep_last:
            to_delete = (
                json_files[: len(json_files) - keep_last]
                if keep_last > 0
                else list(json_files)
            )
    elif keep_days is not None:
        threshold = keep_days * _SECONDS_PER_DAY
        now = time.time()
        to_delete = [p for p in json_files if _file_age_seconds(p, now) > threshold]
    deleted = 0
    for path in to_delete:
        with contextlib.suppress(OSError):
            path.unlink()
            deleted += 1
    return deleted
