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


async def test_remove_project_directory_deletes_tree(tmp_path: Path) -> None:
    target = tmp_path / 'doomed'
    target.mkdir()
    (target / 'nested').mkdir()
    (target / 'nested' / 'file.txt').write_text('payload', encoding='utf-8')
    repo = FilesystemProjectFileRepository()

    await repo.remove_project_directory(target)

    assert not target.exists()


async def test_remove_project_directory_is_idempotent_on_missing(
    tmp_path: Path,
) -> None:
    """Если каталог уже отсутствует — тихо пропускаем.

    Сценарий: пользователь вручную удалил папку проекта, потом
    запустил `project delete --name X`. Use case успешно удаляет
    запись из БД и зовёт remove_project_directory — каталога нет,
    но это не повод падать (orphan-row страшнее orphan-папки).
    """
    target = tmp_path / 'never-existed'
    repo = FilesystemProjectFileRepository()

    await repo.remove_project_directory(target)

    assert not target.exists()
