"""
UpdateProject — use case manifest-first (T098 + T157 refactor).

Manifest = truth: load → mutate → save. SQL slice удалён в T157.

Ошибки:
- `ProjectNotFoundError` — каталога нет.
- `ProjectManifestMissingError` — каталог есть, manifest отсутствует.
- `ValueError` — запрещённый переход фазы.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError, get_project

if TYPE_CHECKING:
    from pathlib import Path

    from domain.phase import PhaseName, PhaseStatus
    from domain.project import Project
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


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
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
) -> Project:
    project = await get_project(
        name=command.name,
        projects_root=projects_root,
        manifest_repo=manifest_repo,
    )

    if command.new_name is not None:
        project.rename(command.new_name)
    if command.phase_update is not None:
        project.transition_phase(
            command.phase_update.name,
            command.phase_update.target_status,
        )
    project.updated_at = datetime.now(UTC)

    await manifest_repo.save(project)
    return project


__all__ = [
    'PhaseUpdate',
    'ProjectManifestMissingError',
    'ProjectNotFoundError',
    'UpdateProjectCommand',
    'update_project',
]
