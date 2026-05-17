"""
UpdateProject — use case manifest-first (T098).

Manifest = truth: загружаем актуальное состояние с диска, мутируем,
переписываем manifest, дальше переиндексируем SQL. SQL-строка нужна
только для path lookup (через `get_project` → `get_by_name`).

В T097 CLI ограничивает каждый вызов одной правкой; на уровне use case
DTO допускает обе одновременно — это даёт атомарную сохранную операцию
для будущих расширений API.

Ошибки:
- `ProjectNotFoundError` — нет SQL-строки с таким именем.
- `ProjectManifestMissingError` — SQL есть, manifest на диске нет
  (desync; пользователю предлагается `reindex`).
- `IndexPersistenceError` — manifest сохранён, SQL update упал
  (partial failure C2; truth уцелел, SQL stale).
- `ValueError` — запрещённый переход фазы (от `Phase.transitioned_to`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from application.errors import (
    IndexPersistenceError,
    ProjectManifestMissingError,
)
from application.get_project import ProjectNotFoundError, get_project

if TYPE_CHECKING:
    from domain.phase import PhaseName, PhaseStatus
    from domain.project import Project
    from ports.outbound.metadata_repository import MetadataRepository
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
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
) -> Project:
    project = await get_project(
        name=command.name,
        repo=repo,
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
    try:
        await repo.update(project)
    except SQLAlchemyError as exc:
        raise IndexPersistenceError(command.name, exc) from exc
    return project


__all__ = [
    'IndexPersistenceError',
    'PhaseUpdate',
    'ProjectManifestMissingError',
    'ProjectNotFoundError',
    'UpdateProjectCommand',
    'update_project',
]
