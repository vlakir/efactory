"""SqlAlchemyMetadataRepository — реализация MetadataRepository через async SQLA."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.outbound.persistence_sql.mapping import project_to_model

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from domain.project import Project


class SqlAlchemyMetadataRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def save(self, project: Project) -> None:
        model = project_to_model(project)
        async with self._session_factory() as session, session.begin():
            session.add(model)
