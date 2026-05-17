"""Integration: SqlAlchemyMetadataRepository через реальный SQLite в tmp_path.

Проверяет, что save() / list_all() работают с domain.Project через
async SQLAlchemy + aiosqlite. Схема накатывается через Alembic
(тот же путь, что и в production через composition root).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from adapters.outbound.persistence_sql.migrations_runner import run_migrations
from adapters.outbound.persistence_sql.repository import (
    SqlAlchemyMetadataRepository,
)
from domain.project import Project


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


async def test_list_all_returns_projects_sorted_by_created_at_desc(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / 'test_list.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        old = Project(
            name='old',
            path=Path('/p/old'),
            created_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        middle = Project(
            name='middle',
            path=Path('/p/middle'),
            created_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        new = Project(
            name='new',
            path=Path('/p/new'),
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
        for project in (old, new, middle):  # порядок вставки ≠ порядок выдачи
            await repo.save(project)

        result = await repo.list_all()
    finally:
        await engine.dispose()

    assert [p.name for p in result] == ['new', 'middle', 'old']
    assert all(p.status.value == 'created' for p in result)


async def test_list_all_returns_empty_when_no_projects(tmp_path: Path) -> None:
    db_file = tmp_path / 'test_empty.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        result = await repo.list_all()
    finally:
        await engine.dispose()

    assert result == []


async def test_get_by_name_returns_project_when_present(tmp_path: Path) -> None:
    db_file = tmp_path / 'test_get.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        wanted = Project(name='target', path=Path('/p/target'))
        await repo.save(Project(name='other', path=Path('/p/other')))
        await repo.save(wanted)

        result = await repo.get_by_name('target')
    finally:
        await engine.dispose()

    assert result is not None
    assert result.id == wanted.id
    assert result.name == 'target'
    assert result.path == Path('/p/target')


async def test_get_by_name_returns_none_when_absent(tmp_path: Path) -> None:
    db_file = tmp_path / 'test_missing.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        await repo.save(Project(name='present', path=Path('/p/present')))

        result = await repo.get_by_name('ghost')
    finally:
        await engine.dispose()

    assert result is None
