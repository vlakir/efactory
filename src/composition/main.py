"""Composition root: сборка графа зависимостей и точка входа CLI."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

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


def build_cli_app() -> typer.Typer:
    logging.basicConfig(level=logging.INFO)

    settings = Settings()

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
