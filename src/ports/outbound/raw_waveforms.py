"""
RawWaveformRepository — outbound port для persist/load raw waveforms (T190).

Adapter'ы по этому port'у persist'ят `RawWaveform` sidecar к `SimResult`
JSON. Канонический FS adapter — `FileSystemRawWaveforms` (см. `adapters/
outbound/raw_waveforms_filesystem/`). Read-side используется
`/export-sim-report` без `--rerun` для рендера plot'ов из persisted
waveforms (T191).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.raw_waveform import RawWaveform, WaveformAnalysisType


class RawWaveformWriteFailedError(Exception):
    """Запись raw waveform завершилась ошибкой (FS error, schema mismatch)."""


class RawWaveformReadFailedError(Exception):
    """Чтение raw waveform завершилось ошибкой (отсутствует / corrupted)."""


class RawWaveformRepository(Protocol):
    """Outbound port: persist / load `RawWaveform` для одного проекта."""

    async def write(
        self,
        *,
        waveform: RawWaveform,
        project_root: Path,
    ) -> Path:
        """
        Persist `waveform` в проект; вернуть абсолютный path JSON.

        Бросает `RawWaveformWriteFailedError` если `project_root` не
        существует или FS не позволяет записать.
        """

    async def load_latest(
        self,
        *,
        project_root: Path,
        analysis_type: WaveformAnalysisType,
    ) -> RawWaveform | None:
        """
        Загрузить latest сохранённый waveform указанного `analysis_type`.

        Returns:
            `RawWaveform` если найден; `None` если каталог пуст / нет
            файлов нужного типа.

        Raises:
            RawWaveformReadFailedError: каталог недоступен / corrupted JSON.

        """


__all__ = [
    'RawWaveformReadFailedError',
    'RawWaveformRepository',
    'RawWaveformWriteFailedError',
]
