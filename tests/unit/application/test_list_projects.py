"""Tests for ListProjects use case — T157 filesystem-first refactor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from application.list_projects import list_projects
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


async def test_list_projects_returns_empty_when_root_empty() -> None:
    manifest_repo = FakeManifestRepository()

    projects = await list_projects(
        projects_root=Path('/p'), manifest_repo=manifest_repo,
    )

    assert projects == []


async def test_list_projects_returns_all_discoverable() -> None:
    first = Project(
        name='first',
        path=Path('/p/first'),
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    second = Project(
        name='second',
        path=Path('/p/second'),
        created_at=datetime(2026, 5, 2, tzinfo=UTC),
    )
    manifest_repo = FakeManifestRepository(first, second)

    projects = await list_projects(
        projects_root=Path('/p'), manifest_repo=manifest_repo,
    )

    assert {p.name for p in projects} == {'first', 'second'}


async def test_list_projects_ordering_follows_discover_all() -> None:
    """Use case не сортирует сам — отдаёт что вернул adapter."""
    first = Project(
        name='first',
        path=Path('/p/first'),
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    second = Project(
        name='second',
        path=Path('/p/second'),
        created_at=datetime(2026, 5, 2, tzinfo=UTC),
    )
    # FakeManifestRepository.discover_all returns sorted by path string.
    manifest_repo = FakeManifestRepository(second, first)

    projects = await list_projects(
        projects_root=Path('/p'), manifest_repo=manifest_repo,
    )

    assert [p.name for p in projects] == ['first', 'second']
