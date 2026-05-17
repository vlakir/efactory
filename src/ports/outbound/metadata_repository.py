"""MetadataRepository — outbound-порт persistence метаданных."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.project import Project


class MetadataRepository(Protocol):
    """
    Persistence для метаданных проектов и сущностей предметной области.

    На старте Walking Skeleton реализован `save(Project)` (T085).
    Расширяется методами `list_all` (T088), `get_by_name` (T089),
    `delete_by_name` (T090), `update` (T097), `get_by_id` и т.д.
    по мере появления соответствующих use cases.
    """

    async def save(self, project: Project) -> None: ...

    async def update(self, project: Project) -> None: ...

    async def list_all(self) -> list[Project]: ...

    async def get_by_name(self, name: str) -> Project | None: ...

    async def delete_by_name(self, name: str) -> None: ...
