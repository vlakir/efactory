"""
RawWaveform — persistent сырые точки симуляции (TRAN / AC / DC) (T190).

В отличие от `SimResult` (lightweight summary snapshot для SessionStart
hook'а), `RawWaveform` хранит полные массивы time/frequency/sweep + traces
для последующего рендера publication-grade plots в `/export-sim-report`
без `--rerun` (см. spec T035 §3, T190 BACKLOG).

Канонический FS-layout — `<PROJECT_ROOT>/.efactory/sim-results/
<TIMESTAMP-safe>-<analysis>.waveform.json`, schema_version=1.

Domain-уровень — без знания о FS / JSON serialization (живут в adapter).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

RAW_WAVEFORM_SCHEMA_VERSION: Literal[1] = 1

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class WaveformAnalysisType(StrEnum):
    """Виды анализов, чьи raw waveforms persist'ятся (T190)."""

    TRAN = 'tran'
    AC = 'ac'
    DC = 'dc'


class RawWaveform(BaseModel):
    """
    JSON snapshot raw waveforms одного analysis-прогона.

    Sidecar для `SimResult` summary JSON. Используется `/export-sim-report`
    без `--rerun` для рендера TRAN/AC/DC plots без повторного запуска SPICE.

    `traces_imag` обязателен **только** для AC (complex sweeps); TRAN и DC
    — real-mode, `traces_imag is None`.
    """

    model_config = _FROZEN

    schema_version: Literal[1] = RAW_WAVEFORM_SCHEMA_VERSION
    timestamp: str = Field(min_length=1)
    analysis_type: WaveformAnalysisType
    source_netlist: str = Field(min_length=1)
    x_axis_name: str = Field(min_length=1)
    x_axis: tuple[float, ...] = Field(min_length=1)
    traces: dict[str, tuple[float, ...]]
    traces_imag: dict[str, tuple[float, ...]] | None = None

    @model_validator(mode='after')
    def _check_traces_lengths_match_x_axis(self) -> Self:
        n = len(self.x_axis)
        for name, values in self.traces.items():
            if len(values) != n:
                msg = (
                    f'RawWaveform: trace {name!r} has {len(values)} samples '
                    f'but x_axis has {n}.'
                )
                raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_traces_imag_consistency(self) -> Self:
        if self.analysis_type == WaveformAnalysisType.AC:
            if self.traces_imag is None:
                msg = 'RawWaveform: AC analysis requires traces_imag (complex).'
                raise ValueError(msg)
            if set(self.traces_imag) != set(self.traces):
                msg = (
                    f'RawWaveform: AC traces_imag keys {sorted(self.traces_imag)!r} '
                    f'!= traces keys {sorted(self.traces)!r}.'
                )
                raise ValueError(msg)
            n = len(self.x_axis)
            for name, values in self.traces_imag.items():
                if len(values) != n:
                    msg = (
                        f'RawWaveform: traces_imag[{name!r}] has {len(values)} '
                        f'samples but x_axis has {n}.'
                    )
                    raise ValueError(msg)
        elif self.traces_imag is not None:
            msg = (
                f'RawWaveform: traces_imag must be None for '
                f'{self.analysis_type.value} (only AC stores complex).'
            )
            raise ValueError(msg)
        return self


__all__ = [
    'RAW_WAVEFORM_SCHEMA_VERSION',
    'Annotated',
    'RawWaveform',
    'WaveformAnalysisType',
]
