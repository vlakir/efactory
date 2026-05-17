"""MetadataRepository — outbound-порт persistence метаданных."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.project import Project


class MetadataRepository(Protocol):
    """
    Persistence для метаданных проектов и сущностей предметной области.

    На старте Walking Skeleton реализован только `save(Project)`.
    Расширяется методами `get_by_id`, `list`, `delete` по мере появления
    соответствующих use cases.
    """

    async def save(self, project: Project) -> None: ...
