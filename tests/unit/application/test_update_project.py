"""UpdateProject use case — T157 filesystem-first refactor."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
    update_project,
)
from domain.phase import PhaseName, PhaseStatus
from domain.project import Project, ProjectStatus
from ports.outbound.project_manifest_repository import ManifestNotFoundError


class FakeManifestRepository:
    """In-memory manifest keyed by project.path."""

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


async def test_update_project_renames_and_persists_to_manifest(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / 'old'
    project_path.mkdir()
    project = Project(name='old', path=project_path)
    manifest_repo = FakeManifestRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(name='old', new_name='new'),
        projects_root=tmp_path,
        manifest_repo=manifest_repo,
    )

    assert result.name == 'new'
    # Manifest хранится по path; rename path не меняет → ключ тот же.
    assert await manifest_repo.load(project_path) is result


async def test_update_project_unknown_name_raises(tmp_path: Path) -> None:
    manifest_repo = FakeManifestRepository()

    with pytest.raises(ProjectNotFoundError):
        await update_project(
            command=UpdateProjectCommand(name='missing', new_name='whatever'),
            projects_root=tmp_path,
            manifest_repo=manifest_repo,
        )


async def test_update_project_missing_manifest_raises_project_manifest_missing(
    tmp_path: Path,
) -> None:
    """Directory есть, manifest yaml отсутствует → corrupt."""
    project_path = tmp_path / 'ghost'
    project_path.mkdir()
    manifest_repo = FakeManifestRepository()  # manifest нет

    with pytest.raises(ProjectManifestMissingError) as exc_info:
        await update_project(
            command=UpdateProjectCommand(name='ghost', new_name='still-ghost'),
            projects_root=tmp_path,
            manifest_repo=manifest_repo,
        )

    assert exc_info.value.project_name == 'ghost'


async def test_update_phase_start_transitions_in_place(tmp_path: Path) -> None:
    project_path = tmp_path / 'p'
    project_path.mkdir()
    project = Project(name='p', path=project_path)
    manifest_repo = FakeManifestRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.IN_PROGRESS,
            ),
        ),
        projects_root=tmp_path,
        manifest_repo=manifest_repo,
    )

    assert result.phases[0].status is PhaseStatus.IN_PROGRESS
    assert result.phases[0].started_at is not None
    assert result.status is ProjectStatus.IDEA


async def test_update_phase_invalid_transition_raises_value_error(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / 'p'
    project_path.mkdir()
    project = Project(name='p', path=project_path)
    manifest_repo = FakeManifestRepository(project)

    with pytest.raises(ValueError):  # noqa: PT011
        await update_project(
            command=UpdateProjectCommand(
                name='p',
                phase_update=PhaseUpdate(
                    name=PhaseName.SCHEMATIC,
                    target_status=PhaseStatus.DONE,  # nelzya pending → done
                ),
            ),
            projects_root=tmp_path,
            manifest_repo=manifest_repo,
        )


async def test_update_project_bumps_updated_at(tmp_path: Path) -> None:
    project_path = tmp_path / 'p'
    project_path.mkdir()
    project = Project(name='p', path=project_path)
    original_updated_at = project.updated_at
    manifest_repo = FakeManifestRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(name='p', new_name='renamed'),
        projects_root=tmp_path,
        manifest_repo=manifest_repo,
    )

    assert result.updated_at > original_updated_at


async def test_update_project_progresses_status_after_phase_done(
    tmp_path: Path,
) -> None:
    """Phase Schematic IN_PROGRESS → DONE bumps status."""
    project_path = tmp_path / 'p'
    project_path.mkdir()
    project = Project(name='p', path=project_path)
    manifest_repo = FakeManifestRepository(project)

    # Start phase
    project = await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.IN_PROGRESS,
            ),
        ),
        projects_root=tmp_path,
        manifest_repo=manifest_repo,
    )

    # Close phase
    result = await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.DONE,
            ),
        ),
        projects_root=tmp_path,
        manifest_repo=manifest_repo,
    )

    assert result.phases[0].status is PhaseStatus.DONE
    assert result.status is ProjectStatus.SCHEMATIC
