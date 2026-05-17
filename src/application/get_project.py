"""
GetProject — use case manifest-first (T098).

SQL `metadata_repo.get_by_name` нужен только чтобы (a) убедиться, что
проект известен системе, (b) получить `path`. Все остальные данные
проекта (имя, фазы, updated_at) берутся из YAML manifest'а — он
источник истины (CONCEPT §4.1).

Ошибки:
- `ProjectNotFoundError` — нет SQL-строки (значит проекта нет вовсе).
- `ProjectManifestMissingError` — SQL знает, manifest на диске нет
  (desync; пользователь зовёт `reindex` или восстанавливает файл).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.errors import ProjectManifestMissingError
from ports.outbound.project_manifest_repository import ManifestNotFoundError

if TYPE_CHECKING:
    from domain.project import Project
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


class ProjectNotFoundError(Exception):
    """Проект с таким именем не найден в metadata-репозитории."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Project '{name}' not found")
        self.name = name


async def get_project(
    *,
    name: str,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
) -> Project:
    sql_row = await repo.get_by_name(name)
    if sql_row is None:
        raise ProjectNotFoundError(name)
    try:
        return await manifest_repo.load(sql_row.path)
    except ManifestNotFoundError as exc:
        raise ProjectManifestMissingError(name, sql_row.path) from exc
