"""
FileSystemRawWaveforms — sidecar JSON для raw SPICE waveforms (T190).

Канонический FS-layout:
    <project>/.efactory/sim-results/<TS-safe>-<analysis>.waveform.json

Атомарность: пишем сначала в `.tmp`, потом `Path.replace`. Имя файла
соответствует SimResult с суффиксом `.waveform.json` (вместо `.json`),
чтобы в одном каталоге лежали парные snapshot + waveform.

`load_latest` сортирует по filename (timestamp prefix → chronological),
возвращает наиболее свежий совпадающего analysis_type.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

from domain.raw_waveform import RawWaveform, WaveformAnalysisType
from ports.outbound.raw_waveforms import (
    RawWaveformReadFailedError,
    RawWaveformWriteFailedError,
)

if TYPE_CHECKING:
    from pathlib import Path


_SIM_RESULTS_SUBDIR = '.efactory/sim-results'
_WAVEFORM_SUFFIX = '.waveform.json'


def _filename_for(waveform: RawWaveform) -> str:
    ts_safe = waveform.timestamp.replace(':', '-')
    return f'{ts_safe}-{waveform.analysis_type.value}{_WAVEFORM_SUFFIX}'


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
        raise RawWaveformWriteFailedError(msg)
    try:
        sim_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f'cannot create sim-results dir: {sim_dir}'
        raise RawWaveformWriteFailedError(msg) from exc
    try:
        tmp_path.write_text(payload_text, encoding='utf-8')
        tmp_path.replace(final_path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        msg = f'failed to write raw waveform: {final_path}'
        raise RawWaveformWriteFailedError(msg) from exc


def _load_sync(
    *,
    sim_dir: Path,
    analysis_type: WaveformAnalysisType,
) -> RawWaveform | None:
    if not sim_dir.is_dir():
        return None
    suffix_marker = f'-{analysis_type.value}{_WAVEFORM_SUFFIX}'
    candidates = sorted(
        p for p in sim_dir.iterdir() if p.is_file() and p.name.endswith(suffix_marker)
    )
    if not candidates:
        return None
    latest = candidates[-1]
    try:
        payload_text = latest.read_text(encoding='utf-8')
    except OSError as exc:
        msg = f'failed to read raw waveform: {latest}'
        raise RawWaveformReadFailedError(msg) from exc
    try:
        data: Any = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        msg = f'raw waveform JSON corrupted: {latest}'
        raise RawWaveformReadFailedError(msg) from exc
    try:
        return RawWaveform.model_validate(data)
    except ValueError as exc:
        msg = f'raw waveform schema mismatch: {latest}'
        raise RawWaveformReadFailedError(msg) from exc


class FileSystemRawWaveforms:
    """Persist / load `RawWaveform` в `<project_root>/.efactory/sim-results/`."""

    async def write(
        self,
        *,
        waveform: RawWaveform,
        project_root: Path,
    ) -> Path:
        sim_dir = project_root / _SIM_RESULTS_SUBDIR
        filename = _filename_for(waveform)
        final_path = sim_dir / filename
        tmp_path = sim_dir / f'{filename}.tmp'
        payload_text = json.dumps(
            waveform.model_dump(mode='json'),
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

    async def load_latest(
        self,
        *,
        project_root: Path,
        analysis_type: WaveformAnalysisType,
    ) -> RawWaveform | None:
        sim_dir = project_root / _SIM_RESULTS_SUBDIR
        return await asyncio.to_thread(
            _load_sync,
            sim_dir=sim_dir,
            analysis_type=analysis_type,
        )


__all__ = ['FileSystemRawWaveforms']
