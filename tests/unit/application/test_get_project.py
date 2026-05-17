"""Tests for application use case GetProject — с fake-портом."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.get_project import ProjectNotFoundError, get_project
from domain.project import Project


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


async def test_get_project_returns_when_found() -> None:
    target = Project(name='target', path=Path('/p/target'))
    other = Project(name='other', path=Path('/p/other'))
    repo = FakeMetadataRepository([other, target])

    result = await get_project(name='target', repo=repo)

    assert result is target


async def test_get_project_raises_project_not_found_when_absent() -> None:
    repo = FakeMetadataRepository()

    with pytest.raises(ProjectNotFoundError) as excinfo:
        await get_project(name='ghost', repo=repo)

    assert 'ghost' in str(excinfo.value)
