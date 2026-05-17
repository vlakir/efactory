"""
UpdateProject — use case: переименовать проект или сменить статус фазы.

В T097 CLI ограничивает каждый вызов одной правкой (Resolved #7);
на уровне use case DTO допускает обе одновременно — это даёт
атомарную сохранную операцию для будущих расширений API.

Если проекта с заданным именем нет — `ProjectNotFoundError`.
Если переход фазы запрещён — `ValueError` (от
`Phase.transitioned_to`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.get_project import ProjectNotFoundError, get_project

if TYPE_CHECKING:
    from domain.phase import PhaseName, PhaseStatus
    from domain.project import Project
    from ports.outbound.metadata_repository import MetadataRepository


@dataclass(frozen=True)
class PhaseUpdate:
    name: PhaseName
    target_status: PhaseStatus


@dataclass(frozen=True)
class UpdateProjectCommand:
    name: str
    new_name: str | None = None
    phase_update: PhaseUpdate | None = None


async def update_project(
    *,
    command: UpdateProjectCommand,
    repo: MetadataRepository,
) -> Project:
    project = await get_project(name=command.name, repo=repo)
    if command.new_name is not None:
        project.rename(command.new_name)
    if command.phase_update is not None:
        project.transition_phase(
            command.phase_update.name,
            command.phase_update.target_status,
        )
    await repo.update(project)
    return project


__all__ = [
    'PhaseUpdate',
    'ProjectNotFoundError',
    'UpdateProjectCommand',
    'update_project',
]
