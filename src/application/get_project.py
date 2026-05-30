"""
GetProject — use case manifest-first (T098 + T157 refactor).

Post-T157: SQL `MetadataRepository` удалён. Filesystem единственный
источник истины — directory presence + `project.yaml` manifest.

Ошибки:
- `ProjectNotFoundError` — каталога `<projects_root>/<name>/` нет.
- `ProjectManifestMissingError` — каталог есть, но `project.yaml`
  отсутствует или повреждён (project corrupt).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.errors import ProjectManifestMissingError
from ports.outbound.project_manifest_repository import ManifestNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.project import Project
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


class ProjectNotFoundError(Exception):
    """Проект с таким именем не найден в `projects_root`."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Project '{name}' not found")
        self.name = name


async def get_project(
    *,
    name: str,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
) -> Project:
    path = projects_root / name
    if not path.is_dir():
        raise ProjectNotFoundError(name)
    try:
        return await manifest_repo.load(path)
    except ManifestNotFoundError as exc:
        raise ProjectManifestMissingError(name, path) from exc
