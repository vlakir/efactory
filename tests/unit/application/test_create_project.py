"""Tests for application use case CreateProject — с fake-портами."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.create_project import create_project

if TYPE_CHECKING:
    from domain.project import Project


class FakeMetadataRepository:
    def __init__(self) -> None:
        self.saved: list[Project] = []

    async def save(self, project: Project) -> None:
        self.saved.append(project)


class FakeProjectFileRepository:
    def __init__(self) -> None:
        self.created_dirs: list[Path] = []

    async def create_project_directory(self, path: Path) -> None:
        self.created_dirs.append(path)


async def test_create_project_saves_and_creates_directory() -> None:
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()

    project = await create_project(
        name='my-amp',
        projects_root=Path('/projects'),
        repo=repo,
        file_repo=file_repo,
    )

    assert project.name == 'my-amp'
    assert project.path == Path('/projects/my-amp')
    assert repo.saved == [project]
    assert file_repo.created_dirs == [project.path]


async def test_create_project_returns_domain_aggregate() -> None:
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()

    project = await create_project(
        name='preamp',
        projects_root=Path('/p'),
        repo=repo,
        file_repo=file_repo,
    )

    assert project.id is not None
    assert project.created_at is not None
    assert project.status.value == 'created'
