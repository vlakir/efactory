"""
Phase — embedded value object внутри Project agg root (T097).

Frozen Pydantic-VO с инвариантами на переходах статуса. Методы
`start / complete / skip / unskip` возвращают НОВЫЙ Phase, не
мутируют self. `transitioned_to(target)` — диспетчер по матрице
C2 из `specs/T097-phase-vo/spec.md`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PhaseName(StrEnum):
    """
    Шесть фаз жизненного цикла проекта (CONCEPT §4.3).

    Порядок объявления является каноническим — `Project.phases`
    обязан следовать ему (см. `domain.project._PHASE_ORDER`).
    """

    SCHEMATIC = 'schematic'
    SIMULATION = 'simulation'
    PCB = 'pcb'
    MAGNETICS = 'magnetics'
    ENCLOSURE = 'enclosure'
    DOCUMENTATION = 'documentation'


class PhaseStatus(StrEnum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    DONE = 'done'
    SKIPPED = 'skipped'


def _now() -> datetime:
    return datetime.now(UTC)


class Phase(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: PhaseName
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> Phase:
        if self.status is not PhaseStatus.PENDING:
            msg = (
                f"Cannot start phase '{self.name.value}': "
                f"current status is '{self.status.value}', expected 'pending'"
            )
            raise ValueError(msg)
        return self.model_copy(
            update={'status': PhaseStatus.IN_PROGRESS, 'started_at': _now()},
        )

    def complete(self) -> Phase:
        if self.status is not PhaseStatus.IN_PROGRESS:
            msg = (
                f"Cannot complete phase '{self.name.value}': "
                f"current status is '{self.status.value}', expected 'in_progress'"
            )
            raise ValueError(msg)
        return self.model_copy(
            update={'status': PhaseStatus.DONE, 'completed_at': _now()},
        )

    def skip(self) -> Phase:
        if self.status not in {PhaseStatus.PENDING, PhaseStatus.IN_PROGRESS}:
            msg = (
                f"Cannot skip phase '{self.name.value}': "
                f"current status is '{self.status.value}', "
                f"expected 'pending' or 'in_progress'"
            )
            raise ValueError(msg)
        return self.model_copy(update={'status': PhaseStatus.SKIPPED})

    def unskip(self) -> Phase:
        if self.status is not PhaseStatus.SKIPPED:
            msg = (
                f"Cannot unskip phase '{self.name.value}': "
                f"current status is '{self.status.value}', expected 'skipped'"
            )
            raise ValueError(msg)
        return self.model_copy(
            update={
                'status': PhaseStatus.PENDING,
                'started_at': None,
                'completed_at': None,
            },
        )

    def transitioned_to(self, target: PhaseStatus) -> Phase:
        """
        Диспетчер по матрице C2 (specs/T097-phase-vo/spec.md → Analyze).

        Разрешены только переходы: pending→in_progress, in_progress→done,
        pending|in_progress→skipped, skipped→pending. Всё остальное
        (включая «прыжки» вперёд по статусу и noop) — ValueError.
        """
        match self.status, target:
            case PhaseStatus.PENDING, PhaseStatus.IN_PROGRESS:
                return self.start()
            case PhaseStatus.IN_PROGRESS, PhaseStatus.DONE:
                return self.complete()
            case (PhaseStatus.PENDING, PhaseStatus.SKIPPED) | (
                PhaseStatus.IN_PROGRESS,
                PhaseStatus.SKIPPED,
            ):
                return self.skip()
            case PhaseStatus.SKIPPED, PhaseStatus.PENDING:
                return self.unskip()
            case _:
                msg = (
                    f"Forbidden phase transition for '{self.name.value}': "
                    f"'{self.status.value}' -> '{target.value}'"
                )
                raise ValueError(msg)
