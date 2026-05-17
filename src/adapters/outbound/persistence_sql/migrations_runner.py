"""Запуск Alembic-миграций программно из composition / тестов."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[4] / 'alembic.ini'


async def run_migrations(database_url: str) -> None:
    """
    Накатить миграции до head на указанный database_url.

    Alembic API — sync, поэтому работаем через asyncio.to_thread.
    """

    def _upgrade() -> None:
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option('sqlalchemy.url', database_url)
        command.upgrade(cfg, 'head')

    await asyncio.to_thread(_upgrade)
