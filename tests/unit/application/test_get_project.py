"""Tests for GetProject use case — T157 filesystem-first refactor."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError, get_project
from domain.project import Project
from ports.outbound.project_manifest_repository import ManifestNotFoundError


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


async def test_get_project_returns_manifest_state_when_found(
    tmp_path: Path,
) -> None:
    """T157: directory exists + manifest loadable → returns Project."""
    target_path = tmp_path / 'target'
    target_path.mkdir()
    target_manifest = Project(name='target', path=target_path)
    manifest_repo = FakeManifestRepository(target_manifest)

    result = await get_project(
        name='target', projects_root=tmp_path, manifest_repo=manifest_repo,
    )

    assert result is target_manifest


async def test_get_project_raises_project_not_found_when_no_directory(
    tmp_path: Path,
) -> None:
    """T157: directory отсутствует → ProjectNotFoundError."""
    manifest_repo = FakeManifestRepository()

    with pytest.raises(ProjectNotFoundError) as excinfo:
        await get_project(
            name='ghost', projects_root=tmp_path, manifest_repo=manifest_repo,
        )

    assert 'ghost' in str(excinfo.value)


async def test_get_project_raises_manifest_missing_when_dir_exists_no_yaml(
    tmp_path: Path,
) -> None:
    """T157: directory есть, manifest yaml отсутствует/повреждён → corrupt."""
    legacy_path = tmp_path / 'legacy'
    legacy_path.mkdir()  # dir exists but no manifest
    manifest_repo = FakeManifestRepository()  # пусто

    with pytest.raises(ProjectManifestMissingError) as excinfo:
        await get_project(
            name='legacy', projects_root=tmp_path, manifest_repo=manifest_repo,
        )

    assert excinfo.value.project_name == 'legacy'
    assert excinfo.value.project_path == legacy_path
