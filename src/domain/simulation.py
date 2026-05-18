"""Simulation — runtime VO для KiCad → SPICE pipeline (T004 / T008)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationStatus(StrEnum):
    PENDING = 'pending'
    NETLIST_READY = 'netlist_ready'
    SIMULATED = 'simulated'
    FAILED = 'failed'


class OpAnalysis(BaseModel):
    """Operating-point analysis (`.OP`)."""

    model_config = ConfigDict(frozen=True)

    type: Literal['op'] = 'op'


class TranAnalysis(BaseModel):
    """Transient analysis (`.TRAN <t_step> <t_stop> [<t_start>] [UIC]`)."""

    model_config = ConfigDict(frozen=True)

    type: Literal['tran'] = 'tran'
    t_step: float = Field(gt=0.0)
    t_stop: float = Field(gt=0.0)
    t_start: float = Field(default=0.0, ge=0.0)
    uic: bool = False

    @model_validator(mode='after')
    def _check_t_stop_after_t_start(self) -> Self:
        if self.t_stop <= self.t_start:
            msg = (
                f'TranAnalysis: t_stop ({self.t_stop}) must be greater than '
                f't_start ({self.t_start}).'
            )
            raise ValueError(msg)
        return self


class AcAnalysis(BaseModel):
    """AC sweep analysis (`.AC <dec|lin|oct> <n_points> <f_start> <f_stop>`)."""

    model_config = ConfigDict(frozen=True)

    type: Literal['ac'] = 'ac'
    sweep: Literal['dec', 'lin', 'oct'] = 'dec'
    n_points: int = Field(gt=0)
    f_start: float = Field(gt=0.0)
    f_stop: float = Field(gt=0.0)

    @model_validator(mode='after')
    def _check_f_stop_after_f_start(self) -> Self:
        if self.f_stop <= self.f_start:
            msg = (
                f'AcAnalysis: f_stop ({self.f_stop}) must be greater than '
                f'f_start ({self.f_start}).'
            )
            raise ValueError(msg)
        return self


AnalysisSpec = Annotated[
    OpAnalysis | TranAnalysis | AcAnalysis,
    Field(discriminator='type'),
]


class TimeSeries(BaseModel):
    """Tabular результат tran-анализа: time + named traces."""

    model_config = ConfigDict(frozen=True)

    time: tuple[float, ...] = Field(min_length=1)
    traces: dict[str, tuple[float, ...]]

    @model_validator(mode='after')
    def _check_trace_lengths_match_time(self) -> Self:
        n = len(self.time)
        for name, values in self.traces.items():
            if len(values) != n:
                msg = (
                    f'TimeSeries: trace {name!r} has {len(values)} samples '
                    f'but time has {n}.'
                )
                raise ValueError(msg)
        return self


class AcSweep(BaseModel):
    """AC-sweep результат: frequency + complex traces как (real, imag)."""

    model_config = ConfigDict(frozen=True)

    frequency: tuple[float, ...] = Field(min_length=1)
    traces_real: dict[str, tuple[float, ...]]
    traces_imag: dict[str, tuple[float, ...]]

    @model_validator(mode='after')
    def _check_trace_lengths_and_keys(self) -> Self:
        n = len(self.frequency)
        if set(self.traces_real) != set(self.traces_imag):
            msg = (
                f'AcSweep: traces_real keys {sorted(self.traces_real)!r} != '
                f'traces_imag keys {sorted(self.traces_imag)!r}.'
            )
            raise ValueError(msg)
        for name, values in self.traces_real.items():
            if len(values) != n:
                msg = (
                    f'AcSweep: traces_real[{name!r}] has {len(values)} '
                    f'samples but frequency has {n}.'
                )
                raise ValueError(msg)
        for name, values in self.traces_imag.items():
            if len(values) != n:
                msg = (
                    f'AcSweep: traces_imag[{name!r}] has {len(values)} '
                    f'samples but frequency has {n}.'
                )
                raise ValueError(msg)
        return self


class SimulationResult(BaseModel):
    """Результат одного анализа — ровно одна из трёх ветвей заполнена."""

    model_config = ConfigDict(frozen=True)

    operating_points: dict[str, float] | None = None
    time_series: TimeSeries | None = None
    ac_sweep: AcSweep | None = None

    @model_validator(mode='after')
    def _check_exactly_one_branch(self) -> Self:
        filled = [
            name
            for name, value in (
                ('operating_points', self.operating_points),
                ('time_series', self.time_series),
                ('ac_sweep', self.ac_sweep),
            )
            if value is not None
        ]
        if len(filled) != 1:
            msg = (
                f'SimulationResult: exactly one of (operating_points, '
                f'time_series, ac_sweep) must be set; got {filled}.'
            )
            raise ValueError(msg)
        return self


class Simulation(BaseModel):
    """Runtime агрегат одной симуляции (T004 не persist'ится; T008 — TBD)."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    schematic_path: Path
    netlist_path: Path | None = None
    status: SimulationStatus = SimulationStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: SimulationResult | None = None
