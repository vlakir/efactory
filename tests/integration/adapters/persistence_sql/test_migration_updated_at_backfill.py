"""T098 миграция: projects.updated_at + backfill (= created_at для existing).

Acceptance из `specs/T098-manifest-primary/spec.md` § 4 / Resolved (a):
`updated_at` добавлено в Project (Phase 1). Миграция Phase 2:
- добавить колонку `projects.updated_at` (DateTime tz=True, NOT NULL);
- для существующих строк backfill `updated_at = created_at`
  (см. Clarify #10: «принцип наименьшего сюрприза»).

Тест: накатываем БД до T097-head (`d82c9915c172`), вставляем
SQL-only проект, накатываем до head (наша новая миграция) — ждём
`updated_at == created_at`.
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


async def test_updated_at_backfilled_to_created_at_for_pre_t098_projects(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / 'pre_t098.sqlite'
    database_url = f'sqlite+aiosqlite:///{db_file}'

    await asyncio.to_thread(_upgrade_to, database_url, 'd82c9915c172')

    legacy_id = uuid4()
    legacy_created = datetime(2026, 5, 1, 12, 30, tzinfo=UTC)

    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    'INSERT INTO projects (id, name, path, created_at) '
                    'VALUES (:id, :name, :path, :created_at)',
                ).bindparams(
                    sa.bindparam('id', type_=sa.Uuid()),
                    sa.bindparam('created_at', type_=sa.DateTime(timezone=True)),
                ),
                {
                    'id': legacy_id,
                    'name': 'legacy',
                    'path': '/p/legacy',
                    'created_at': legacy_created,
                },
            )
    finally:
        await engine.dispose()

    await asyncio.to_thread(_upgrade_to, database_url, 'head')

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        'SELECT created_at, updated_at FROM projects '
                        'WHERE id = :pid',
                    ).bindparams(sa.bindparam('pid', type_=sa.Uuid())),
                    {'pid': legacy_id},
                )
            ).fetchone()
            columns = (
                await conn.execute(text('PRAGMA table_info(projects)'))
            ).fetchall()
    finally:
        await engine.dispose()

    assert row is not None
    created_at, updated_at = row
    assert created_at == updated_at

    updated_at_col = next(col for col in columns if col[1] == 'updated_at')
    # col[3] == notnull flag (1 = NOT NULL) per PRAGMA table_info.
    assert updated_at_col[3] == 1
