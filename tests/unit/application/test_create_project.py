"""Tests for application use case CreateProject — T157 filesystem-first."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.create_project import create_project
from ports.outbound.git_repository import (
    GitOperationError,
    GitUnavailableError,
)

if TYPE_CHECKING:
    from domain.project import Project


class FakeProjectFileRepository:
    def __init__(self) -> None:
        self.created_dirs: list[Path] = []

    async def create_project_directory(self, path: Path) -> None:
        self.created_dirs.append(path)


class FakeManifestRepository:
    def __init__(self) -> None:
        self.saved: list[Project] = []

    async def save(self, project: Project) -> None:
        self.saved.append(project)


class FakeGitRepository:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[tuple[Path, str]] = []
        self._raises = raises

    async def init_with_initial_commit(
        self, project_path: Path, message: str,
    ) -> None:
        if self._raises is not None:
            raise self._raises
        self.calls.append((project_path, message))


async def test_create_project_writes_manifest_then_git() -> None:
    """Manifest first → git init last (T157: SQL slice removed)."""
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository()

    result = await create_project(
        name='my-amp',
        projects_root=Path('/projects'),
        file_repo=file_repo,
        manifest_repo=manifest_repo,
        git_repo=git_repo,
    )

    project = result.project
    assert project.name == 'my-amp'
    assert project.path == Path('/projects/my-amp')
    assert file_repo.created_dirs == [project.path]
    assert manifest_repo.saved == [project]
    assert git_repo.calls == [(project.path, 'efactory: create project my-amp')]
    assert result.git_initialized is True


async def test_create_project_returns_domain_aggregate() -> None:
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository()

    result = await create_project(
        name='preamp',
        projects_root=Path('/p'),
        file_repo=file_repo,
        manifest_repo=manifest_repo,
        git_repo=git_repo,
    )

    project = result.project
    assert project.id is not None
    assert project.created_at is not None
    assert project.updated_at is not None
    assert project.status.value == 'idea'


async def test_create_project_git_unavailable_returns_flag_false() -> None:
    """git нет на машине → проект создан без VCS, git_initialized=False."""
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository(raises=GitUnavailableError('git not found'))

    result = await create_project(
        name='no-git',
        projects_root=Path('/p'),
        file_repo=file_repo,
        manifest_repo=manifest_repo,
        git_repo=git_repo,
    )

    assert result.project.name == 'no-git'
    assert result.git_initialized is False
    assert manifest_repo.saved == [result.project]


async def test_create_project_git_operation_error_propagates() -> None:
    """GitOperationError — серьёзный FS-сбой, пробрасывается до CLI."""
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository(raises=GitOperationError('permission denied'))

    with pytest.raises(GitOperationError):
        await create_project(
            name='broken-git',
            projects_root=Path('/p'),
            file_repo=file_repo,
            manifest_repo=manifest_repo,
            git_repo=git_repo,
        )
