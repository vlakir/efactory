"""Tests for GetProject use case — manifest-first (T098)."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError, get_project
from domain.project import Project
from ports.outbound.project_manifest_repository import ManifestNotFoundError


class FakeMetadataRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self._projects = list(projects or [])

    async def save(self, project: Project) -> None:
        self._projects.append(project)

    async def list_all(self) -> list[Project]:
        return list(self._projects)

    async def get_by_name(self, name: str) -> Project | None:
        for project in self._projects:
            if project.name == name:
                return project
        return None


class FakeManifestRepository:
    def __init__(self, *projects: Project) -> None:
        self._by_path: dict[Path, Project] = {p.path: p for p in projects}

    async def save(self, project: Project) -> None:
        self._by_path[project.path] = project

    async def load(self, project_path: Path) -> Project:
        if project_path not in self._by_path:
            msg = f'Manifest not found at {project_path}'
            raise ManifestNotFoundError(msg)
        return self._by_path[project_path]

    async def exists(self, project_path: Path) -> bool:
        return project_path in self._by_path

    async def discover_all(self, storage_root: Path) -> list[Path]:
        return sorted(p for p in self._by_path if p.parent == storage_root)


async def test_get_project_returns_manifest_state_when_found() -> None:
    """SQL даёт path, manifest даёт всё остальное (truth)."""
    target_sql = Project(name='target', path=Path('/p/target'))
    target_manifest = Project(
        id=target_sql.id,
        name='target',
        path=Path('/p/target'),
    )
    repo = FakeMetadataRepository([target_sql])
    manifest_repo = FakeManifestRepository(target_manifest)

    result = await get_project(name='target', repo=repo, manifest_repo=manifest_repo)

    assert result is target_manifest


async def test_get_project_raises_project_not_found_when_sql_missing() -> None:
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository()

    with pytest.raises(ProjectNotFoundError) as excinfo:
        await get_project(name='ghost', repo=repo, manifest_repo=manifest_repo)

    assert 'ghost' in str(excinfo.value)


async def test_get_project_raises_manifest_missing_when_sql_has_but_manifest_absent() -> None:
    """Desync: SQL знает о проекте, manifest на диске удалён."""
    sql_only = Project(name='legacy', path=Path('/p/legacy'))
    repo = FakeMetadataRepository([sql_only])
    manifest_repo = FakeManifestRepository()  # пусто

    with pytest.raises(ProjectManifestMissingError) as excinfo:
        await get_project(name='legacy', repo=repo, manifest_repo=manifest_repo)

    assert excinfo.value.project_name == 'legacy'
    assert excinfo.value.project_path == Path('/p/legacy')
