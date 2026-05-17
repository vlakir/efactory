"""CreateProject — use case Walking Skeleton: domain → persistence → файлы."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.project import Project

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository


async def create_project(
    name: str,
    projects_root: Path,
    repo: MetadataRepository,
    file_repo: ProjectFileRepository,
) -> Project:
    project = Project(name=name, path=projects_root / name)
    await repo.save(project)
    await file_repo.create_project_directory(project.path)
    return project
