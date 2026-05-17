"""T097 миграция d82c9915c172: backfill 6 pending phases для existing проектов.

Acceptance из `specs/T097-phase-vo/spec.md` § Success Criteria:
«Alembic migration отрабатывает на БД с существующими SQL-only
проектами без потери данных проекта (id, name, path, created_at)».
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from adapters.outbound.persistence_sql.migrations_runner import ALEMBIC_INI


def _upgrade_to(database_url: str, revision: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option('sqlalchemy.url', database_url)
    command.upgrade(cfg, revision)


async def test_phases_table_backfill_for_existing_sql_only_projects(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / 'pre_t097.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await asyncio.to_thread(_upgrade_to, database_url, '97a7c34eaf3b')

    engine = create_async_engine(database_url)
    try:
        legacy_id = uuid4()
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    'INSERT INTO projects (id, name, path, created_at, status) '
                    'VALUES (:id, :name, :path, :created_at, :status)',
                ).bindparams(
                    sa.bindparam('id', type_=sa.Uuid()),
                    sa.bindparam('created_at', type_=sa.DateTime(timezone=True)),
                ),
                {
                    'id': legacy_id,
                    'name': 'legacy-amp',
                    'path': '/p/legacy-amp',
                    'created_at': datetime(2026, 5, 1, tzinfo=UTC),
                    'status': 'created',
                },
            )
    finally:
        await engine.dispose()

    await asyncio.to_thread(_upgrade_to, database_url, 'head')

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            project_row = (
                await conn.execute(
                    text('SELECT id, name, path FROM projects'),
                )
            ).fetchone()
            phase_rows = (
                await conn.execute(
                    text(
                        'SELECT name, status, started_at, completed_at '
                        'FROM phases WHERE project_id = :pid ORDER BY name',
                    ).bindparams(sa.bindparam('pid', type_=sa.Uuid())),
                    {'pid': legacy_id},
                )
            ).fetchall()
            projects_columns = (
                await conn.execute(text('PRAGMA table_info(projects)'))
            ).fetchall()
    finally:
        await engine.dispose()

    assert project_row is not None
    saved_id, saved_name, saved_path = project_row
    assert saved_name == 'legacy-amp'
    assert saved_path == '/p/legacy-amp'
    assert str(saved_id).replace('-', '') == legacy_id.hex

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

    assert 'status' not in {col[1] for col in projects_columns}
