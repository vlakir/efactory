"""Integration: SqlAlchemyMetadataRepository через реальный SQLite в tmp_path.

Проверяет, что save() / list_all() работают с domain.Project через
async SQLAlchemy + aiosqlite. Схема накатывается через Alembic
(тот же путь, что и в production через composition root).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from adapters.outbound.persistence_sql.migrations_runner import run_migrations
from adapters.outbound.persistence_sql.repository import (
    SqlAlchemyMetadataRepository,
)
from domain.phase import PhaseName, PhaseStatus
from domain.project import Project, ProjectStatus


async def test_save_persists_project_row_and_six_default_phases(
    tmp_path: Path,
) -> None:
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
            project_rows = (
                await conn.execute(text('SELECT id, name, path FROM projects'))
            ).fetchall()
            phase_rows = (
                await conn.execute(
                    text(
                        'SELECT name, status, started_at, completed_at '
                        'FROM phases WHERE project_id = :pid '
                        'ORDER BY name',
                    ).bindparams(sa.bindparam('pid', type_=sa.Uuid())),
                    {'pid': project.id},
                )
            ).fetchall()
    finally:
        await engine.dispose()

    assert len(project_rows) == 1
    saved_id, saved_name, saved_path = project_rows[0]
    assert saved_name == 'test-amp'
    assert saved_path == str(project.path)
    assert str(saved_id).replace('-', '') == project.id.hex

    assert len(phase_rows) == 6
    assert {row[0] for row in phase_rows} == {
        'schematic',
        'simulation',
        'pcb',
        'magnetics',
        'enclosure',
        'documentation',
    }
    assert all(row[1] == 'pending' for row in phase_rows)
    assert all(row[2] is None and row[3] is None for row in phase_rows)


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
    assert all(p.status.value == 'idea' for p in result)


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
    assert len(result.phases) == 6
    assert all(p.status is PhaseStatus.PENDING for p in result.phases)


async def test_save_and_get_round_trip_preserves_phase_state(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / 'test_roundtrip.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        project = Project(name='rt', path=Path('/p/rt'))
        project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.IN_PROGRESS)
        project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.DONE)
        project.transition_phase(PhaseName.SIMULATION, PhaseStatus.SKIPPED)
        await repo.save(project)

        loaded = await repo.get_by_name('rt')
    finally:
        await engine.dispose()

    assert loaded is not None
    assert loaded.phases[0].status is PhaseStatus.DONE
    assert loaded.phases[0].started_at is not None
    assert loaded.phases[0].completed_at is not None
    assert loaded.phases[1].status is PhaseStatus.SKIPPED
    assert loaded.phases[1].completed_at is None
    assert all(
        p.status is PhaseStatus.PENDING for p in loaded.phases[2:]
    )
    assert loaded.status is ProjectStatus.SIMULATED  # skipped считается закрытой


async def test_update_persists_rename_and_phase_transitions(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / 'test_update.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        project = Project(name='before', path=Path('/p/before'))
        await repo.save(project)

        project.rename('after')
        project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.IN_PROGRESS)
        project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.DONE)
        await repo.update(project)

        loaded = await repo.get_by_name('after')
        old = await repo.get_by_name('before')
    finally:
        await engine.dispose()

    assert old is None
    assert loaded is not None
    assert loaded.id == project.id
    assert loaded.phases[0].status is PhaseStatus.DONE
    assert loaded.status is ProjectStatus.SCHEMATIC


async def test_update_unknown_id_raises_value_error(tmp_path: Path) -> None:
    db_file = tmp_path / 'test_update_404.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        orphan = Project(name='orphan', path=Path('/p/orphan'))

        with pytest.raises(ValueError, match='not found for update'):
            await repo.update(orphan)
    finally:
        await engine.dispose()


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


async def test_delete_by_name_removes_row_and_cascades_phases(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / 'test_delete.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        doomed = Project(name='doomed', path=Path('/p/doomed'))
        alive = Project(name='alive', path=Path('/p/alive'))
        await repo.save(doomed)
        await repo.save(alive)

        await repo.delete_by_name('doomed')

        remaining = await repo.list_all()
        async with engine.connect() as conn:
            orphan_phase_rows = (
                await conn.execute(
                    text(
                        'SELECT COUNT(*) FROM phases WHERE project_id = :pid',
                    ).bindparams(sa.bindparam('pid', type_=sa.Uuid())),
                    {'pid': doomed.id},
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert [p.name for p in remaining] == ['alive']
    assert orphan_phase_rows == 0


async def test_delete_by_name_is_noop_when_absent(tmp_path: Path) -> None:
    """Удаление несуществующего ряда не падает.

    Use case сам проверяет существование через get_by_name перед
    delete_by_name, так что adapter-уровень тут защищать незачем —
    но должен быть идемпотентен на повторных вызовах.
    """
    db_file = tmp_path / 'test_delete_noop.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await run_migrations(database_url)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        repo = SqlAlchemyMetadataRepository(session_factory)

        await repo.save(Project(name='kept', path=Path('/p/kept')))

        await repo.delete_by_name('never-existed')

        remaining = await repo.list_all()
    finally:
        await engine.dispose()

    assert [p.name for p in remaining] == ['kept']
