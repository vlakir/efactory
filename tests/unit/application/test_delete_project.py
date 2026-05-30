"""Tests for application use case DeleteProject — T157 filesystem-first."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.delete_project import delete_project
from application.get_project import ProjectNotFoundError


class FakeProjectFileRepository:
    def __init__(self) -> None:
        self.removed_paths: list[Path] = []

    async def create_project_directory(self, path: Path) -> None:
        msg = 'create_project_directory: not used in delete_project tests'
        raise NotImplementedError(msg)

    async def remove_project_directory(self, path: Path) -> None:
        self.removed_paths.append(path)


async def test_delete_project_removes_existing_directory(tmp_path: Path) -> None:
    target_path = tmp_path / 'target'
    target_path.mkdir()
    file_repo = FakeProjectFileRepository()

    await delete_project(
        name='target', projects_root=tmp_path, file_repo=file_repo,
    )

    assert file_repo.removed_paths == [target_path]


async def test_delete_project_raises_when_no_directory(tmp_path: Path) -> None:
    file_repo = FakeProjectFileRepository()

    with pytest.raises(ProjectNotFoundError) as excinfo:
        await delete_project(
            name='ghost', projects_root=tmp_path, file_repo=file_repo,
        )

    assert 'ghost' in str(excinfo.value)
    assert file_repo.removed_paths == []
