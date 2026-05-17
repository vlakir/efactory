"""
GetProject — use case: получить проект по имени или сигналить ошибку.

При отсутствии записи в repo поднимается `ProjectNotFoundError`. Это
явное application-исключение, чтобы CLI / API могли отличить «нет
такого» от «БД упала» и вернуть пользователю осмысленный exit-code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.project import Project
    from ports.outbound.metadata_repository import MetadataRepository


class ProjectNotFoundError(Exception):
    """Проект с таким именем не найден в metadata-репозитории."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Project '{name}' not found")
        self.name = name


async def get_project(
    *,
    name: str,
    repo: MetadataRepository,
) -> Project:
    project = await repo.get_by_name(name)
    if project is None:
        raise ProjectNotFoundError(name)
    return project
