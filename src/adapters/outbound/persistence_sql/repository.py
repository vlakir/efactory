"""SqlAlchemyMetadataRepository — реализация MetadataRepository через async SQLA."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from adapters.outbound.persistence_sql.mapping import (
    model_to_project,
    project_to_model,
)
from adapters.outbound.persistence_sql.models import ProjectModel

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

    async def update(self, project: Project) -> None:
        """
        Заглушка для фазы 1 T097. Реальный UPDATE — фаза 2.

        Use case UpdateProject из фазы 1 не вызывается из CLI до
        фазы 3, так что эта ветка не активна в e2e. Фаза 2 добавит
        Alembic-миграцию (drop status / create phases table) и
        реализацию через session.merge + sync phase-rows.
        """
        msg = (
            'SqlAlchemyMetadataRepository.update is implemented in T097 phase 2 '
            '(SQL persistence). Phase 1 use case is tested with fake repo.'
        )
        raise NotImplementedError(msg)

    async def list_all(self) -> list[Project]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectModel).order_by(ProjectModel.created_at.desc()),
            )
            return [model_to_project(row) for row in result.scalars().all()]

    async def get_by_name(self, name: str) -> Project | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectModel).where(ProjectModel.name == name).limit(1),
            )
            model = result.scalars().first()
            return model_to_project(model) if model is not None else None

    async def delete_by_name(self, name: str) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                delete(ProjectModel).where(ProjectModel.name == name),
            )
