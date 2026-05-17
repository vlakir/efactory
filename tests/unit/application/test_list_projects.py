"""Tests for application use case ListProjects — с fake-портом."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from application.list_projects import list_projects
from domain.project import Project


class FakeMetadataRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self._projects = list(projects or [])

    async def save(self, project: Project) -> None:
        self._projects.append(project)

    async def list_all(self) -> list[Project]:
        return list(self._projects)


async def test_list_projects_returns_empty_when_repo_empty() -> None:
    repo = FakeMetadataRepository()

    projects = await list_projects(repo=repo)

    assert projects == []


async def test_list_projects_returns_projects_from_repo() -> None:
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
    repo = FakeMetadataRepository([second, first])

    projects = await list_projects(repo=repo)

    assert projects == [second, first]


async def test_list_projects_delegates_ordering_to_repo() -> None:
    """Use case не сортирует сам — отдаёт что вернул repo."""
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

    repo_asc = FakeMetadataRepository([first, second])
    repo_desc = FakeMetadataRepository([second, first])

    assert (await list_projects(repo=repo_asc))[0].name == 'first'
    assert (await list_projects(repo=repo_desc))[0].name == 'second'
