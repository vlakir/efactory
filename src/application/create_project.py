"""CreateProject — use case manifest-first + git init (T098 + T010 + T157)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.project import Project
from ports.outbound.git_repository import GitUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.git_repository import GitRepository
    from ports.outbound.project_file_repository import ProjectFileRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


@dataclass(frozen=True)
class CreateProjectResult:
    """T010 N9: CLI должен знать, получилось ли git init, без знания инфры."""

    project: Project
    git_initialized: bool


_INITIAL_COMMIT_TEMPLATE = 'efactory: create project {name}'


async def create_project(
    name: str,
    projects_root: Path,
    file_repo: ProjectFileRepository,
    manifest_repo: ProjectManifestRepository,
    git_repo: GitRepository,
) -> CreateProjectResult:
    """T157: manifest first, git init last; SQL upsert удалён."""
    project = Project(name=name, path=projects_root / name)
    await file_repo.create_project_directory(project.path)
    await manifest_repo.save(project)

    git_initialized = True
    try:
        await git_repo.init_with_initial_commit(
            project.path,
            _INITIAL_COMMIT_TEMPLATE.format(name=name),
        )
    except GitUnavailableError:
        git_initialized = False

    return CreateProjectResult(project=project, git_initialized=git_initialized)
