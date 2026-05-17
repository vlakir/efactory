"""Integration: FilesystemProjectFileRepository — реальная FS в tmp_path."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.outbound.file_store.project_file_repository import (
    FilesystemProjectFileRepository,
    ProjectDirectoryExistsError,
)

if TYPE_CHECKING:
    from pathlib import Path


async def test_creates_project_directory(tmp_path: Path) -> None:
    target = tmp_path / 'my-amp'
    repo = FilesystemProjectFileRepository()

    await repo.create_project_directory(target)

    assert target.is_dir()


async def test_creates_intermediate_parents(tmp_path: Path) -> None:
    target = tmp_path / 'projects' / 'nested' / 'my-amp'
    repo = FilesystemProjectFileRepository()

    await repo.create_project_directory(target)

    assert target.is_dir()


async def test_raises_if_directory_already_exists(tmp_path: Path) -> None:
    target = tmp_path / 'existing'
    target.mkdir()
    repo = FilesystemProjectFileRepository()

    with pytest.raises(ProjectDirectoryExistsError):
        await repo.create_project_directory(target)
