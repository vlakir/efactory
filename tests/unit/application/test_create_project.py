"""Tests for application use case CreateProject — с fake-портами."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import SQLAlchemyError

from application.create_project import create_project
from application.errors import IndexPersistenceError
from ports.outbound.git_repository import (
    GitOperationError,
    GitUnavailableError,
)

if TYPE_CHECKING:
    from domain.project import Project


class FakeMetadataRepository:
    def __init__(self, *, save_raises: Exception | None = None) -> None:
        self.saved: list[Project] = []
        self._save_raises = save_raises

    async def save(self, project: Project) -> None:
        if self._save_raises is not None:
            raise self._save_raises
        self.saved.append(project)


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
        self, project_path: Path, message: str
    ) -> None:
        if self._raises is not None:
            raise self._raises
        self.calls.append((project_path, message))


async def test_create_project_writes_manifest_then_sql_index_then_git() -> None:
    """Манифест записан до SQL до git init (T010 C1)."""
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository()

    result = await create_project(
        name='my-amp',
        projects_root=Path('/projects'),
        repo=repo,
        file_repo=file_repo,
        manifest_repo=manifest_repo,
        git_repo=git_repo,
    )

    project = result.project
    assert project.name == 'my-amp'
    assert project.path == Path('/projects/my-amp')
    assert file_repo.created_dirs == [project.path]
    assert manifest_repo.saved == [project]
    assert repo.saved == [project]
    assert git_repo.calls == [(project.path, 'efactory: create project my-amp')]
    assert result.git_initialized is True


async def test_create_project_returns_domain_aggregate() -> None:
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository()

    result = await create_project(
        name='preamp',
        projects_root=Path('/p'),
        repo=repo,
        file_repo=file_repo,
        manifest_repo=manifest_repo,
        git_repo=git_repo,
    )

    project = result.project
    assert project.id is not None
    assert project.created_at is not None
    assert project.updated_at is not None
    assert project.status.value == 'idea'


async def test_create_project_partial_failure_raises_index_persistence_error() -> None:
    """SQL upsert fails after manifest saved → IndexPersistenceError (C2).

    Manifest на диске остаётся (truth), пользователь зовёт `reindex`.
    """
    sql_error = SQLAlchemyError('connection lost')
    repo = FakeMetadataRepository(save_raises=sql_error)
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository()

    with pytest.raises(IndexPersistenceError) as exc_info:
        await create_project(
            name='ill-fated',
            projects_root=Path('/p'),
            repo=repo,
            file_repo=file_repo,
            manifest_repo=manifest_repo,
            git_repo=git_repo,
        )

    assert exc_info.value.project_name == 'ill-fated'
    assert exc_info.value.__cause__ is sql_error
    # Manifest успели записать до фейла SQL.
    assert len(manifest_repo.saved) == 1
    assert manifest_repo.saved[0].name == 'ill-fated'
    assert file_repo.created_dirs == [Path('/p/ill-fated')]
    # git init не зовётся при SQL fail (T010 C1 (A): git после всего)
    assert git_repo.calls == []


async def test_create_project_git_unavailable_returns_flag_false() -> None:
    """T010 N9: git нет на машине → проект создан без VCS, git_initialized=False."""
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository(raises=GitUnavailableError('git not found'))

    result = await create_project(
        name='no-git',
        projects_root=Path('/p'),
        repo=repo,
        file_repo=file_repo,
        manifest_repo=manifest_repo,
        git_repo=git_repo,
    )

    assert result.project.name == 'no-git'
    assert result.git_initialized is False
    assert repo.saved == [result.project]  # проект всё равно сохранён


async def test_create_project_git_operation_error_propagates() -> None:
    """GitOperationError — серьёзный FS-сбой, пробрасывается до CLI (Spec § 3)."""
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()
    git_repo = FakeGitRepository(raises=GitOperationError('permission denied'))

    with pytest.raises(GitOperationError):
        await create_project(
            name='broken-git',
            projects_root=Path('/p'),
            repo=repo,
            file_repo=file_repo,
            manifest_repo=manifest_repo,
            git_repo=git_repo,
        )
