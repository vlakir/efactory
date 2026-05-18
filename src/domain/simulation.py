"""Simulation — runtime VO для KiCad → SPICE pipeline (T004)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SimulationStatus(StrEnum):
    PENDING = 'pending'  # создан, ничего не сделано
    NETLIST_READY = 'netlist_ready'  # `.cir` экспортирован
    SIMULATED = 'simulated'  # результаты получены (T008)
    FAILED = 'failed'  # ошибка export / simulate


class SimulationResult(BaseModel):
    """Минимальный shape результатов; T008 расширит."""

    model_config = ConfigDict(frozen=True)

    operating_points: dict[str, float] = Field(default_factory=dict)


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
