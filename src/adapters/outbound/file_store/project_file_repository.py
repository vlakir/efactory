"""Filesystem-реализация ProjectFileRepository."""

from __future__ import annotations

import asyncio
import shutil
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

    async def remove_project_directory(self, path: Path) -> None:
        def _rmtree() -> None:
            if not path.exists():
                return
            shutil.rmtree(path)

        await asyncio.to_thread(_rmtree)
