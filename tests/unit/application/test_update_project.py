"""UpdateProject use case — с fake-репозиторием."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.get_project import ProjectNotFoundError
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
    update_project,
)
from domain.phase import PhaseName, PhaseStatus
from domain.project import Project, ProjectStatus


class FakeMetadataRepository:
    """In-memory storage; ловим вызовы save/update для проверки."""

    def __init__(self, *projects: Project) -> None:
        self._by_name: dict[str, Project] = {p.name: p for p in projects}
        self.update_calls: list[Project] = []

    async def save(self, project: Project) -> None:
        self._by_name[project.name] = project

    async def update(self, project: Project) -> None:
        self.update_calls.append(project)
        self._by_name = {
            n: p for n, p in self._by_name.items() if p.id != project.id
        }
        self._by_name[project.name] = project

    async def get_by_name(self, name: str) -> Project | None:
        return self._by_name.get(name)

    async def list_all(self) -> list[Project]:
        return list(self._by_name.values())

    async def delete_by_name(self, name: str) -> None:
        self._by_name.pop(name, None)


async def test_update_project_renames_and_persists() -> None:
    project = Project(name='old', path=Path('/p/old'))
    repo = FakeMetadataRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(name='old', new_name='new'),
        repo=repo,
    )

    assert result.name == 'new'
    assert repo.update_calls == [result]
    assert await repo.get_by_name('new') is result
    assert await repo.get_by_name('old') is None


async def test_update_project_unknown_name_raises() -> None:
    repo = FakeMetadataRepository()

    with pytest.raises(ProjectNotFoundError):
        await update_project(
            command=UpdateProjectCommand(name='missing', new_name='whatever'),
            repo=repo,
        )


async def test_update_phase_start_transitions_in_place() -> None:
    project = Project(name='p', path=Path('/p'))
    repo = FakeMetadataRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.IN_PROGRESS,
            ),
        ),
        repo=repo,
    )

    assert result.phases[0].status is PhaseStatus.IN_PROGRESS
    assert result.phases[0].started_at is not None
    assert result.status is ProjectStatus.IDEA  # ещё in_progress, не done
    assert repo.update_calls == [result]


async def test_update_phase_invalid_transition_raises_value_error() -> None:
    """Прыжок pending → done через CLI/use case запрещён (Analyze C2)."""
    project = Project(name='p', path=Path('/p'))
    repo = FakeMetadataRepository(project)

    with pytest.raises(ValueError, match='Forbidden phase transition'):
        await update_project(
            command=UpdateProjectCommand(
                name='p',
                phase_update=PhaseUpdate(
                    name=PhaseName.SCHEMATIC,
                    target_status=PhaseStatus.DONE,
                ),
            ),
            repo=repo,
        )

    assert repo.update_calls == []  # rolled back: ничего не сохранилось


async def test_update_project_progresses_status_after_phase_done() -> None:
    project = Project(name='p', path=Path('/p'))
    repo = FakeMetadataRepository(project)

    await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.IN_PROGRESS,
            ),
        ),
        repo=repo,
    )
    result = await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.DONE,
            ),
        ),
        repo=repo,
    )

    assert result.status is ProjectStatus.SCHEMATIC
    assert len(repo.update_calls) == 2
