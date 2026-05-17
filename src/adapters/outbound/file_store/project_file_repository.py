"""Filesystem-реализация ProjectFileRepository."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ProjectDirectoryExistsError(Exception):
    """Папка проекта уже существует — отказываем, чтобы не перетереть данные."""


class FilesystemProjectFileRepository:
    async def create_project_directory(self, path: Path) -> None:
        def _mkdir() -> None:
            if path.exists():
                msg = f'Project directory already exists: {path}'
                raise ProjectDirectoryExistsError(msg)
            path.mkdir(parents=True)

        await asyncio.to_thread(_mkdir)
