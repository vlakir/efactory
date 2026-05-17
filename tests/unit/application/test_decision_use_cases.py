"""Application use cases for Decision (T099 Phase 2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import SQLAlchemyError

from application.add_decision import add_decision
from application.errors import (
    DecisionPersistenceError,
    IndexPersistenceError,
)
from application.get_decision import get_decision
from application.get_project import ProjectNotFoundError
from application.list_decisions import list_decisions
from domain.decision import Decision, DecisionStatus
from domain.project import Project
from ports.outbound.decision_repository import DecisionNotFoundError
from ports.outbound.project_manifest_repository import ManifestNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterable


class FakeMetadataRepository:
    def __init__(
        self,
        *projects: Project,
        update_raises: Exception | None = None,
    ) -> None:
        self._by_name: dict[str, Project] = {p.name: p for p in projects}
        self.updates: list[Project] = []
        self._update_raises = update_raises

    async def save(self, project: Project) -> None:
        self._by_name[project.name] = project

    async def update(self, project: Project) -> None:
        if self._update_raises is not None:
            raise self._update_raises
        self.updates.append(project)
        self._by_name[project.name] = project

    async def list_all(self) -> list[Project]:
        return list(self._by_name.values())

    async def get_by_name(self, name: str) -> Project | None:
        return self._by_name.get(name)

    async def delete_by_name(self, name: str) -> None:
        self._by_name.pop(name, None)


class FakeManifestRepository:
    def __init__(
        self,
        *projects: Project,
        save_raises: Exception | None = None,
    ) -> None:
        self._by_path: dict[Path, Project] = {p.path: p for p in projects}
        self._save_raises = save_raises
        self.saves: list[Project] = []

    async def save(self, project: Project) -> None:
        if self._save_raises is not None:
            raise self._save_raises
        self._by_path[project.path] = project
        self.saves.append(project)

    async def load(self, project_path: Path) -> Project:
        if project_path not in self._by_path:
            raise ManifestNotFoundError(str(project_path))
        return self._by_path[project_path]

    async def exists(self, project_path: Path) -> bool:
        return project_path in self._by_path

    async def discover_all(self, storage_root: Path) -> list[Path]:
        return sorted(p for p in self._by_path if p.parent == storage_root)


class FakeDecisionRepository:
    def __init__(self, decisions: Iterable[Decision] | None = None) -> None:
        self._items: list[Decision] = list(decisions or [])

    async def save(self, project_path: Path, decision: Decision) -> Path:
        self._items.append(decision)
        return project_path / 'decisions' / f'{decision.id}.md'

    async def load(self, project_path: Path, decision_id: str) -> Decision:  # noqa: ARG002
        for d in self._items:
            if d.id == decision_id:
                return d
        raise DecisionNotFoundError(decision_id)

    async def list_all(self, project_path: Path) -> list[Decision]:  # noqa: ARG002
        return sorted(self._items, key=lambda d: int(d.id[1:]))

    async def next_id(self, project_path: Path) -> str:  # noqa: ARG002
        if not self._items:
            return 'D001'
        max_n = max(int(d.id[1:]) for d in self._items)
        return f'D{max_n + 1:03d}'


def _project(name: str = 'p', path: Path = Path('/p')) -> Project:
    return Project(name=name, path=path)


async def test_add_decision_writes_markdown_and_updates_manifest() -> None:
    project = _project()
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    decision_repo = FakeDecisionRepository()

    decision = await add_decision(
        project_name='p',
        title='Choose SE',
        decision_date=date(2026, 5, 17),
        status=DecisionStatus.ACCEPTED,
        summary='SE для наушников',
        rationale='Меньше искажений',
        repo=repo,
        manifest_repo=manifest_repo,
        decision_repo=decision_repo,
    )

    assert decision.id == 'D001'
    assert decision.title == 'Choose SE'
    assert len(decision_repo._items) == 1  # noqa: SLF001  pragma: no cover
    saved_manifest = await manifest_repo.load(project.path)
    assert len(saved_manifest.decisions) == 1
    assert saved_manifest.decisions[0].id == 'D001'
    assert repo.updates[0].id == project.id


async def test_add_decision_auto_increments_id() -> None:
    project = _project()
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    decision_repo = FakeDecisionRepository()

    for _ in range(3):
        await add_decision(
            project_name='p',
            title='x',
            decision_date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
            repo=repo,
            manifest_repo=manifest_repo,
            decision_repo=decision_repo,
        )

    ids = [d.id for d in await decision_repo.list_all(project.path)]
    assert ids == ['D001', 'D002', 'D003']


async def test_add_decision_unknown_project_raises() -> None:
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository()
    decision_repo = FakeDecisionRepository()

    with pytest.raises(ProjectNotFoundError):
        await add_decision(
            project_name='missing',
            title='x',
            decision_date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
            repo=repo,
            manifest_repo=manifest_repo,
            decision_repo=decision_repo,
        )


async def test_add_decision_manifest_save_failure_raises_decision_persistence() -> None:
    """N3: markdown сохранён, manifest fails → DecisionPersistenceError."""
    project = _project()
    repo = FakeMetadataRepository(project)
    fs_error = OSError('disk full')
    manifest_repo = FakeManifestRepository(project, save_raises=fs_error)
    decision_repo = FakeDecisionRepository()

    with pytest.raises(DecisionPersistenceError) as exc:
        await add_decision(
            project_name='p',
            title='x',
            decision_date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
            repo=repo,
            manifest_repo=manifest_repo,
            decision_repo=decision_repo,
        )

    assert exc.value.decision_id == 'D001'
    assert exc.value.__cause__ is fs_error
    # markdown успели записать
    assert len(decision_repo._items) == 1  # noqa: SLF001


async def test_add_decision_sql_update_failure_raises_index_persistence() -> None:
    project = _project()
    sql_error = SQLAlchemyError('connection lost')
    repo = FakeMetadataRepository(project, update_raises=sql_error)
    manifest_repo = FakeManifestRepository(project)
    decision_repo = FakeDecisionRepository()

    with pytest.raises(IndexPersistenceError):
        await add_decision(
            project_name='p',
            title='x',
            decision_date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
            repo=repo,
            manifest_repo=manifest_repo,
            decision_repo=decision_repo,
        )

    # markdown + manifest успели; SQL stale, recoverable через reindex.
    saved_manifest = await manifest_repo.load(project.path)
    assert len(saved_manifest.decisions) == 1


async def test_list_decisions_returns_from_markdown_not_manifest() -> None:
    """Markdown = truth: даже если manifest decisions stale, list даёт markdown."""
    project = _project()
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    decisions = [
        Decision(
            id='D001',
            title='a',
            date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
        ),
        Decision(
            id='D002',
            title='b',
            date=date(2026, 5, 18),
            status=DecisionStatus.PROPOSED,
            summary='s2',
            rationale='r2',
        ),
    ]
    decision_repo = FakeDecisionRepository(decisions)

    result = await list_decisions(
        project_name='p',
        repo=repo,
        manifest_repo=manifest_repo,
        decision_repo=decision_repo,
    )

    assert [d.id for d in result] == ['D001', 'D002']


async def test_get_decision_returns_loaded() -> None:
    project = _project()
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    target = Decision(
        id='D003',
        title='c',
        date=date(2026, 5, 17),
        status=DecisionStatus.REJECTED,
        summary='s',
        rationale='r',
    )
    decision_repo = FakeDecisionRepository([target])

    result = await get_decision(
        project_name='p',
        decision_id='D003',
        repo=repo,
        manifest_repo=manifest_repo,
        decision_repo=decision_repo,
    )

    assert result == target


async def test_get_decision_missing_raises_decision_not_found() -> None:
    project = _project()
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    decision_repo = FakeDecisionRepository()

    with pytest.raises(DecisionNotFoundError):
        await get_decision(
            project_name='p',
            decision_id='D999',
            repo=repo,
            manifest_repo=manifest_repo,
            decision_repo=decision_repo,
        )
