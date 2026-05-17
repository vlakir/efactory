"""
ListProjects — use case: получить все проекты для CLI / UI.

Тонкий: делегирует выборку и сортировку adapter'у (repository.list_all).
Бизнес-логики сейчас нет — расширим, когда понадобятся фильтры/
пагинация/ACL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.project import Project
    from ports.outbound.metadata_repository import MetadataRepository


async def list_projects(*, repo: MetadataRepository) -> list[Project]:
    return await repo.list_all()
