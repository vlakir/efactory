"""Tests for application use case CreateProject — с fake-портами."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import SQLAlchemyError

from application.create_project import create_project
from application.errors import IndexPersistenceError

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


async def test_create_project_writes_manifest_then_sql_index() -> None:
    """Манифест должен быть записан до SQL — manifest = primary truth."""
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()

    project = await create_project(
        name='my-amp',
        projects_root=Path('/projects'),
        repo=repo,
        file_repo=file_repo,
        manifest_repo=manifest_repo,
    )

    assert project.name == 'my-amp'
    assert project.path == Path('/projects/my-amp')
    assert file_repo.created_dirs == [project.path]
    assert manifest_repo.saved == [project]
    assert repo.saved == [project]


async def test_create_project_returns_domain_aggregate() -> None:
    repo = FakeMetadataRepository()
    file_repo = FakeProjectFileRepository()
    manifest_repo = FakeManifestRepository()

    project = await create_project(
        name='preamp',
        projects_root=Path('/p'),
        repo=repo,
        file_repo=file_repo,
        manifest_repo=manifest_repo,
    )

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

    with pytest.raises(IndexPersistenceError) as exc_info:
        await create_project(
            name='ill-fated',
            projects_root=Path('/p'),
            repo=repo,
            file_repo=file_repo,
            manifest_repo=manifest_repo,
        )

    assert exc_info.value.project_name == 'ill-fated'
    assert exc_info.value.__cause__ is sql_error
    # Manifest успели записать до фейла SQL.
    assert len(manifest_repo.saved) == 1
    assert manifest_repo.saved[0].name == 'ill-fated'
    assert file_repo.created_dirs == [Path('/p/ill-fated')]
