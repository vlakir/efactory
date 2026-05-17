"""UpdateProject use case — manifest-first (T098)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from application.errors import (
    IndexPersistenceError,
    ProjectManifestMissingError,
)
from application.get_project import ProjectNotFoundError
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
    update_project,
)
from domain.phase import PhaseName, PhaseStatus
from domain.project import Project, ProjectStatus
from ports.outbound.project_manifest_repository import ManifestNotFoundError


class FakeMetadataRepository:
    """In-memory storage; ловим вызовы save/update для проверки."""

    def __init__(
        self,
        *projects: Project,
        update_raises: Exception | None = None,
    ) -> None:
        self._by_name: dict[str, Project] = {p.name: p for p in projects}
        self._by_id: dict[object, Project] = {p.id: p for p in projects}
        self.update_calls: list[Project] = []
        self._update_raises = update_raises

    async def save(self, project: Project) -> None:
        self._by_name[project.name] = project
        self._by_id[project.id] = project

    async def update(self, project: Project) -> None:
        if self._update_raises is not None:
            raise self._update_raises
        self.update_calls.append(project)
        # допускаем rename — найти старое name по id и выкинуть
        old_name = next(
            (n for n, p in self._by_name.items() if p.id == project.id), None
        )
        if old_name is not None:
            self._by_name.pop(old_name, None)
        self._by_name[project.name] = project
        self._by_id[project.id] = project

    async def get_by_name(self, name: str) -> Project | None:
        return self._by_name.get(name)

    async def list_all(self) -> list[Project]:
        return list(self._by_name.values())

    async def delete_by_name(self, name: str) -> None:
        project = self._by_name.pop(name, None)
        if project is not None:
            self._by_id.pop(project.id, None)


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


async def test_update_project_renames_and_persists_to_manifest_and_sql() -> None:
    project = Project(name='old', path=Path('/p/old'))
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(name='old', new_name='new'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert result.name == 'new'
    assert repo.update_calls == [result]
    # Manifest хранится по path; rename path не меняет → ключ тот же.
    assert await manifest_repo.load(project.path) is result


async def test_update_project_unknown_name_raises() -> None:
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository()

    with pytest.raises(ProjectNotFoundError):
        await update_project(
            command=UpdateProjectCommand(name='missing', new_name='whatever'),
            repo=repo,
            manifest_repo=manifest_repo,
        )


async def test_update_project_missing_manifest_raises_project_manifest_missing() -> None:
    """SQL знает о проекте, но manifest на диске отсутствует → desync."""
    project = Project(name='ghost', path=Path('/p/ghost'))
    repo = FakeMetadataRepository(project)  # SQL есть
    manifest_repo = FakeManifestRepository()  # manifest нет

    with pytest.raises(ProjectManifestMissingError) as exc_info:
        await update_project(
            command=UpdateProjectCommand(name='ghost', new_name='still-ghost'),
            repo=repo,
            manifest_repo=manifest_repo,
        )

    assert exc_info.value.project_name == 'ghost'
    assert exc_info.value.project_path == Path('/p/ghost')


async def test_update_phase_start_transitions_in_place() -> None:
    project = Project(name='p', path=Path('/p'))
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.IN_PROGRESS,
            ),
        ),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert result.phases[0].status is PhaseStatus.IN_PROGRESS
    assert result.phases[0].started_at is not None
    assert result.status is ProjectStatus.IDEA
    assert repo.update_calls == [result]


async def test_update_phase_invalid_transition_raises_value_error() -> None:
    project = Project(name='p', path=Path('/p'))
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)

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
            manifest_repo=manifest_repo,
        )

    assert repo.update_calls == []


async def test_update_project_progresses_status_after_phase_done() -> None:
    project = Project(name='p', path=Path('/p'))
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)

    await update_project(
        command=UpdateProjectCommand(
            name='p',
            phase_update=PhaseUpdate(
                name=PhaseName.SCHEMATIC,
                target_status=PhaseStatus.IN_PROGRESS,
            ),
        ),
        repo=repo,
        manifest_repo=manifest_repo,
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
        manifest_repo=manifest_repo,
    )

    assert result.status is ProjectStatus.SCHEMATIC
    assert len(repo.update_calls) == 2


async def test_update_project_bumps_updated_at() -> None:
    """`updated_at` явно перевыставляется в момент save (Resolved (a))."""
    project = Project(
        name='p',
        path=Path('/p'),
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)

    result = await update_project(
        command=UpdateProjectCommand(name='p', new_name='p2'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert result.updated_at > project.created_at


async def test_update_project_partial_failure_raises_index_persistence_error() -> None:
    """Manifest сохранён, SQL update упал → IndexPersistenceError (C2)."""
    project = Project(name='unstable', path=Path('/p/unstable'))
    sql_error = SQLAlchemyError('lost connection')
    repo = FakeMetadataRepository(project, update_raises=sql_error)
    manifest_repo = FakeManifestRepository(project)

    with pytest.raises(IndexPersistenceError) as exc_info:
        await update_project(
            command=UpdateProjectCommand(name='unstable', new_name='renamed'),
            repo=repo,
            manifest_repo=manifest_repo,
        )

    assert exc_info.value.project_name == 'unstable'
    assert exc_info.value.__cause__ is sql_error
    # Manifest успели сохранить до фейла SQL — на диске лежит truth.
    saved_manifest = await manifest_repo.load(project.path)
    assert saved_manifest.name == 'renamed'
