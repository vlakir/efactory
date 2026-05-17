"""CreateProject — use case manifest-first (T098 phase C)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from application.errors import IndexPersistenceError
from domain.project import Project

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


async def create_project(
    name: str,
    projects_root: Path,
    repo: MetadataRepository,
    file_repo: ProjectFileRepository,
    manifest_repo: ProjectManifestRepository,
) -> Project:
    project = Project(name=name, path=projects_root / name)
    await file_repo.create_project_directory(project.path)
    await manifest_repo.save(project)
    try:
        await repo.save(project)
    except SQLAlchemyError as exc:
        raise IndexPersistenceError(name, exc) from exc
    return project
