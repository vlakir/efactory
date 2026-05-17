"""Tests for application use case DeleteProject — с fake-портами."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.delete_project import delete_project
from application.get_project import ProjectNotFoundError
from domain.project import Project


class FakeMetadataRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self._projects = list(projects or [])
        self.deleted_names: list[str] = []

    async def save(self, project: Project) -> None:
        self._projects.append(project)

    async def list_all(self) -> list[Project]:
        return list(self._projects)

    async def get_by_name(self, name: str) -> Project | None:
        for project in self._projects:
            if project.name == name:
                return project
        return None

    async def delete_by_name(self, name: str) -> None:
        self.deleted_names.append(name)
        self._projects = [p for p in self._projects if p.name != name]


class FakeProjectFileRepository:
    def __init__(self) -> None:
        self.removed_paths: list[Path] = []

    async def create_project_directory(self, path: Path) -> None:
        msg = 'create_project_directory: not used in delete_project tests'
        raise NotImplementedError(msg)

    async def remove_project_directory(self, path: Path) -> None:
        self.removed_paths.append(path)


async def test_delete_project_removes_from_repo_and_filesystem() -> None:
    target = Project(name='target', path=Path('/p/target'))
    other = Project(name='other', path=Path('/p/other'))
    repo = FakeMetadataRepository([other, target])
    file_repo = FakeProjectFileRepository()

    await delete_project(name='target', repo=repo, file_repo=file_repo)

    assert repo.deleted_names == ['target']
    assert file_repo.removed_paths == [target.path]
    remaining = await repo.list_all()
    assert [p.name for p in remaining] == ['other']


async def test_delete_project_raises_when_name_absent() -> None:
    """Косвенно подтверждает «сначала get, потом delete».

    Если бы use case удалял до проверки, мы бы не увидели
    ProjectNotFoundError, и repo.deleted_names / file_repo.removed_paths
    были бы непустыми. Сейчас они пусты — порядок соблюдён.
    """
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()

    with pytest.raises(ProjectNotFoundError) as excinfo:
        await delete_project(name='ghost', repo=repo, file_repo=file_repo)

    assert 'ghost' in str(excinfo.value)
    assert repo.deleted_names == []
    assert file_repo.removed_paths == []
