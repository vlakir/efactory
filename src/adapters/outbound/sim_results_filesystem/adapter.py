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
from typing import TYPE_CHECKING

from ports.outbound.sim_results import SimResultsWriteFailedError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.sim_results import SimResult


_SIM_RESULTS_SUBDIR = '.efactory/sim-results'


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
