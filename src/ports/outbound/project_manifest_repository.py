"""ProjectManifestRepository — outbound-порт YAML manifest persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.project import Project


class ProjectManifestRepository(Protocol):
    """
    YAML manifest как primary storage проекта (T098).

    Manifest `<project.path>/project.yaml` — источник истины;
    SQL индекс пересобирается из манифестов через `ReindexProjects`.
    """

    async def save(self, project: Project) -> None: ...

    async def load(self, project_path: Path) -> Project: ...

    async def exists(self, project_path: Path) -> bool: ...

    async def discover_all(self, storage_root: Path) -> list[Path]: ...
