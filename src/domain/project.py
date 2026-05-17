"""Project — корневой агрегат предметной области efactory."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from domain.phase import Phase, PhaseName, PhaseStatus


class ProjectStatus(StrEnum):
    """Уровень зрелости проекта (CONCEPT §4.3). Derived от phases."""

    IDEA = 'idea'
    SCHEMATIC = 'schematic'
    SIMULATED = 'simulated'
    PCB_DESIGNED = 'pcb_designed'
    MAGNETICS_DONE = 'magnetics_done'
    ENCLOSURE_DONE = 'enclosure_done'
    PRODUCTION_READY = 'production_ready'


def _validate_name(value: str) -> str:
    if not value.strip():
        msg = 'Project name must not be empty or whitespace-only'
        raise ValueError(msg)
    if value in {'.', '..'}:
        msg = 'Project name must not be "." or ".."'
        raise ValueError(msg)
    if '/' in value or '\\' in value:
        msg = 'Project name must not contain path separators ("/" or "\\")'
        raise ValueError(msg)
    return value


ProjectName = Annotated[str, AfterValidator(_validate_name)]


_PHASE_ORDER: tuple[PhaseName, ...] = (
    PhaseName.SCHEMATIC,
    PhaseName.SIMULATION,
    PhaseName.PCB,
    PhaseName.MAGNETICS,
    PhaseName.ENCLOSURE,
    PhaseName.DOCUMENTATION,
)


_STATUS_BY_LAST_CLOSED: dict[PhaseName | None, ProjectStatus] = {
    None: ProjectStatus.IDEA,
    PhaseName.SCHEMATIC: ProjectStatus.SCHEMATIC,
    PhaseName.SIMULATION: ProjectStatus.SIMULATED,
    PhaseName.PCB: ProjectStatus.PCB_DESIGNED,
    PhaseName.MAGNETICS: ProjectStatus.MAGNETICS_DONE,
    PhaseName.ENCLOSURE: ProjectStatus.ENCLOSURE_DONE,
    PhaseName.DOCUMENTATION: ProjectStatus.PRODUCTION_READY,
}


def _default_phases() -> tuple[Phase, ...]:
    return tuple(Phase(name=name) for name in _PHASE_ORDER)


def _validate_phases(phases: tuple[Phase, ...]) -> tuple[Phase, ...]:
    if len(phases) != len(_PHASE_ORDER):
        msg = f'Project must have exactly {len(_PHASE_ORDER)} phases, got {len(phases)}'
        raise ValueError(msg)
    actual_names = tuple(p.name for p in phases)
    if actual_names != _PHASE_ORDER:
        msg = (
            f'Phases must be in canonical order '
            f'{tuple(p.value for p in _PHASE_ORDER)}, '
            f'got {tuple(p.value for p in actual_names)}'
        )
        raise ValueError(msg)
    return phases


PhasesTuple = Annotated[tuple[Phase, ...], AfterValidator(_validate_phases)]


class Project(BaseModel):
    """Aggregate root: один проект РЭА (схема, плата, корпус, документация)."""

    # `extra='ignore'` — страховка для T098 YAML manifest load:
    # ручные правки могут содержать поля будущих фич (description,
    # decisions, etc.); v1 их молча игнорирует, документировано в спеке.
    model_config = ConfigDict(validate_assignment=True, extra='ignore')

    id: UUID = Field(default_factory=uuid4)
    name: ProjectName
    path: Path
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    phases: PhasesTuple = Field(default_factory=_default_phases)

    # `@computed_field` + `@property` — канонический Pydantic v2 паттерн
    # для derived-полей, попадающих в `model_dump` (нужно для T098 YAML
    # manifest). Mypy не поддерживает декораторы поверх `@property`
    # (см. pydantic/pydantic#5916) — `prop-decorator` ignore документирован
    # самой Pydantic как рекомендуемый workaround. Согласовано с Владимиром.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> ProjectStatus:
        """
        Derived: последняя непрерывно-закрытая фаза с начала.

        Phase «закрыта» если status in {done, skipped}. Chain
        прерывается на первой pending|in_progress — все done
        ПОСЛЕ неё не зачитываются (spec → Resolved #4).
        """
        last_closed: PhaseName | None = None
        for phase in self.phases:
            if phase.status in {PhaseStatus.DONE, PhaseStatus.SKIPPED}:
                last_closed = phase.name
            else:
                break
        return _STATUS_BY_LAST_CLOSED[last_closed]

    def rename(self, new_name: str) -> None:
        """In-place rename. `validate_assignment` дёрнет ProjectName validator."""
        self.name = new_name

    def transition_phase(
        self,
        phase_name: PhaseName,
        target: PhaseStatus,
    ) -> None:
        """
        In-place смена статуса одной фазы по матрице C2.

        Делегирует на `Phase.transitioned_to(target)` (которая
        бросает ValueError на запрещённых переходах) и пересобирает
        кортеж `phases`.
        """
        idx = _PHASE_ORDER.index(phase_name)
        new_phase = self.phases[idx].transitioned_to(target)
        self.phases = (*self.phases[:idx], new_phase, *self.phases[idx + 1 :])
