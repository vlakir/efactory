"""SqlAlchemyMetadataRepository — реализация MetadataRepository через async SQLA."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from adapters.outbound.persistence_sql.mapping import (
    _phase_to_model,
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
        """
        Idempotent upsert by id (T098 C1).

        Если строки с таким id нет — `session.add` (INSERT); если есть —
        копируем поля и перезаписываем коллекцию phases (delete-orphan
        каскад почистит старые). Один путь для CreateProject и
        ReindexProjects.
        """
        async with self._session_factory() as session, session.begin():
            existing = await session.get(ProjectModel, project.id)
            if existing is None:
                session.add(project_to_model(project))
                return
            existing.name = project.name
            existing.path = str(project.path)
            existing.created_at = project.created_at
            existing.updated_at = project.updated_at
            existing.phases = [
                _phase_to_model(project.id, phase) for phase in project.phases
            ]

    async def update(self, project: Project) -> None:
        """
        Обновить name и набор phases существующего проекта.

        Загружает ORM-инстанс по id (selectin подтянет phases-relation),
        заменяет name и пересоздаёт список PhaseModel — `delete-orphan`
        каскад чистит старые строки. Use case вызывает `update` только
        после успешного `get_by_name`, поэтому отсутствие в БД — это
        нарушение инварианта (race / неверный id) → ValueError.
        """
        async with self._session_factory() as session, session.begin():
            existing = await session.get(ProjectModel, project.id)
            if existing is None:
                msg = (
                    f'Project {project.id} not found for update '
                    '(concurrent deletion or invalid id)'
                )
                raise ValueError(msg)
            existing.name = project.name
            existing.phases = [
                _phase_to_model(project.id, phase) for phase in project.phases
            ]

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
        """
        Через ORM-delete, чтобы `delete-orphan` cascade почистил phases.

        Bulk-`DELETE FROM projects` оставил бы orphan phase-rows, т.к.
        FK `ondelete=CASCADE` требует включённого `PRAGMA foreign_keys`
        на SQLite (по умолчанию выключен). ORM-cascade срабатывает в
        Python, независимо от SQLite-настроек, поэтому надёжнее.
        Идемпотентность сохраняется: отсутствующий проект — no-op.
        """
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(ProjectModel).where(ProjectModel.name == name).limit(1),
            )
            model = result.scalars().first()
            if model is not None:
                await session.delete(model)
