"""
ListProjects — use case: получить все проекты (T157 refactor).

Post-T157: filesystem-first — scan `projects_root` через manifest
adapter `discover_all`, load каждый. Corrupt projects (manifest
missing/broken) silently skipped — `validate_manifests` use case
(бывший reindex_projects) даёт явный диагностический отчёт.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ports.outbound.project_manifest_repository import (
    ManifestInvalidError,
    ManifestNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.project import Project
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


async def list_projects(
    *,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
) -> list[Project]:
    paths = await manifest_repo.discover_all(projects_root)
    projects: list[Project] = []
    for path in paths:
        try:
            projects.append(await manifest_repo.load(path))
        except (ManifestNotFoundError, ManifestInvalidError):
            # Corrupt project — skip; validate_manifests diagnostic.
            continue
    return projects
