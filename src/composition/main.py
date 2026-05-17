"""Composition root: сборка графа зависимостей и точка входа CLI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from adapters.inbound.cli.app import build_app
from adapters.outbound.file_store.project_file_repository import (
    FilesystemProjectFileRepository,
)
from adapters.outbound.persistence_sql.migrations_runner import run_migrations
from adapters.outbound.persistence_sql.repository import (
    SqlAlchemyMetadataRepository,
)
from composition.settings import Settings

if TYPE_CHECKING:
    import typer


def _ensure_storage_dirs(settings: Settings) -> None:
    """
    Создать каталоги для projects_root и SQLite-БД до миграций.

    Aiosqlite/SQLite сами создают файл БД, но не создают родительский
    каталог — для default'ов вида `~/.local/share/efactory/efactory.db`
    это критично. Для других СУБД (Postgres и т.д.) пропускаем.
    """
    settings.projects_root.mkdir(parents=True, exist_ok=True)

    url = make_url(settings.database_url)
    db_path = url.database
    if (
        url.drivername.startswith('sqlite')
        and db_path is not None
        and db_path != ':memory:'
    ):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def build_cli_app() -> typer.Typer:
    logging.basicConfig(level=logging.INFO)

    settings = Settings()
    _ensure_storage_dirs(settings)

    asyncio.run(run_migrations(settings.database_url))

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    return build_app(
        projects_root=settings.projects_root,
        metadata_repository=SqlAlchemyMetadataRepository(session_factory),
        file_repository=FilesystemProjectFileRepository(),
    )


def run() -> None:
    build_cli_app()()
