"""Integration: SqlAlchemyMetadataRepository через реальный SQLite в tmp_path.

Проверяет, что save() сохраняет domain.Project в таблицу projects через
async SQLAlchemy + aiosqlite. Схема накатывается через Alembic
(тот же путь, что и в production через composition root).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from adapters.outbound.persistence_sql.migrations_runner import run_migrations
from adapters.outbound.persistence_sql.repository import (
    SqlAlchemyMetadataRepository,
)
from domain.project import Project

if TYPE_CHECKING:
    pass


async def test_save_persists_project_row(tmp_path: Path) -> None:
    db_file = tmp_path / 'test.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        project = Project(name='test-amp', path=Path('/p/test-amp'))
        await repo.save(project)

        async with engine.connect() as conn:
            result = await conn.execute(
                text('SELECT id, name, path, status FROM projects'),
            )
            rows = result.fetchall()
    finally:
        await engine.dispose()

    assert len(rows) == 1
    saved_id, saved_name, saved_path, saved_status = rows[0]
    assert saved_name == 'test-amp'
    assert saved_path == str(project.path)
    assert saved_status == 'created'
    assert str(saved_id).replace('-', '') == project.id.hex
