"""ReindexProjects use case — manifest→SQL primary + SQL→manifest bootstrap (T098)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from datetime import date

from application.reindex_projects import (
    ReindexSummary,
    reindex_projects,
)
from domain.decision import Decision, DecisionStatus
from domain.project import Project
from ports.outbound.decision_repository import DecisionNotFoundError
from ports.outbound.project_manifest_repository import (
    ManifestInvalidError,
    ManifestNotFoundError,
)


class FakeMetadataRepository:
    def __init__(
        self,
        *projects: Project,
        save_raises_for: set[str] | None = None,
        delete_raises_for: set[str] | None = None,
    ) -> None:
        self._by_name: dict[str, Project] = {p.name: p for p in projects}
        self._by_id: dict[object, Project] = {p.id: p for p in projects}
        self._save_raises_for = save_raises_for or set()
        self._delete_raises_for = delete_raises_for or set()
        self.deleted_names: list[str] = []

    async def save(self, project: Project) -> None:
        if project.name in self._save_raises_for:
            raise SQLAlchemyError(f'forced failure for {project.name}')
        self._by_name[project.name] = project
        self._by_id[project.id] = project

    async def update(self, project: Project) -> None:
        self._by_name[project.name] = project
        self._by_id[project.id] = project

    async def list_all(self) -> list[Project]:
        return list(self._by_name.values())

    async def get_by_name(self, name: str) -> Project | None:
        return self._by_name.get(name)

    async def delete_by_name(self, name: str) -> None:
        if name in self._delete_raises_for:
            raise SQLAlchemyError(f'forced delete failure for {name}')
        project = self._by_name.pop(name, None)
        if project is not None:
            self._by_id.pop(project.id, None)
            self.deleted_names.append(name)


class FakeManifestRepository:
    def __init__(
        self,
        *projects: Project,
        invalid_at: set[Path] | None = None,
        save_raises_for: set[Path] | None = None,
    ) -> None:
        self._by_path: dict[Path, Project] = {p.path: p for p in projects}
        self._invalid_at = invalid_at or set()
        self._save_raises_for = save_raises_for or set()
        self.saved: list[Project] = []

    async def save(self, project: Project) -> None:
        if project.path in self._save_raises_for:
            msg = f'forced save failure at {project.path}'
            raise OSError(msg)
        self._by_path[project.path] = project
        self.saved.append(project)

    async def load(self, project_path: Path) -> Project:
        if project_path in self._invalid_at:
            msg = f'Invalid manifest at {project_path}'
            raise ManifestInvalidError(msg)
        if project_path not in self._by_path:
            msg = f'Manifest not found at {project_path}'
            raise ManifestNotFoundError(msg)
        return self._by_path[project_path]

    async def exists(self, project_path: Path) -> bool:
        return project_path in self._by_path

    async def discover_all(self, storage_root: Path) -> list[Path]:
        return sorted(
            p for p in self._by_path if p.parent == storage_root
        )


async def test_reindex_empty_storage_returns_zero_summary() -> None:
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository()

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary == ReindexSummary(
        indexed=0, bootstrapped=0, orphans=[], failed=[],
    )


async def test_reindex_indexes_manifest_into_sql_when_absent() -> None:
    """Manifest на диске, SQL пустой → indexed=1."""
    project = Project(name='m-only', path=Path('/storage/m-only'))
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository(project)

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.indexed == 1
    assert summary.bootstrapped == 0
    assert summary.orphans == []
    assert summary.failed == []
    assert await repo.get_by_name('m-only') is not None


async def test_reindex_upserts_when_both_manifest_and_sql_exist() -> None:
    """Идемпотентность: повторный reindex без изменений = чистый indexed."""
    project = Project(name='both', path=Path('/storage/both'))
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.indexed == 1
    assert summary.bootstrapped == 0
    assert summary.orphans == []
    assert summary.failed == []


async def test_reindex_bootstraps_manifest_for_sql_only_projects() -> None:
    """SQL-only запись → создать manifest из SQL (Clarify #3 (B))."""
    legacy = Project(
        name='legacy',
        path=Path('/storage/legacy'),
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    repo = FakeMetadataRepository(legacy)
    manifest_repo = FakeManifestRepository()

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.indexed == 0
    assert summary.bootstrapped == 1
    assert summary.orphans == []
    assert summary.failed == []
    # Manifest должен быть записан.
    assert len(manifest_repo.saved) == 1
    bootstrapped = manifest_repo.saved[0]
    assert bootstrapped.name == 'legacy'
    # updated_at = created_at (Clarify #10)
    assert bootstrapped.updated_at == bootstrapped.created_at


async def test_reindex_remove_orphans_deletes_sql_rows_without_manifest() -> None:
    """--remove-orphans: SQL-only записи удаляются из SQL, в orphans — имена."""
    orphan = Project(name='orphan', path=Path('/storage/orphan'))
    survivor_project = Project(name='alive', path=Path('/storage/alive'))
    repo = FakeMetadataRepository(orphan, survivor_project)
    manifest_repo = FakeManifestRepository(survivor_project)

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
        remove_orphans=True,
    )

    assert summary.indexed == 1  # alive проиндексирован
    assert summary.bootstrapped == 0  # bootstrap отключён --remove-orphans'ом
    assert summary.orphans == ['orphan']
    assert summary.failed == []
    assert repo.deleted_names == ['orphan']


async def test_reindex_collects_failed_manifests_and_continues() -> None:
    """Битый manifest не блокирует обработку остальных (best-effort)."""
    good = Project(name='good', path=Path('/storage/good'))
    broken_path = Path('/storage/broken')
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository(
        good,
        Project(name='broken', path=broken_path),  # будет в discover_all
        invalid_at={broken_path},
    )

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.indexed == 1
    assert summary.bootstrapped == 0
    assert summary.orphans == []
    assert len(summary.failed) == 1
    failed_path, failed_msg = summary.failed[0]
    assert failed_path == broken_path
    assert 'Invalid manifest' in failed_msg


async def test_reindex_collects_failed_sql_upserts_and_continues() -> None:
    """SQL upsert упал → failed, остальные обрабатываются."""
    good = Project(name='good', path=Path('/storage/good'))
    bad = Project(name='bad', path=Path('/storage/bad'))
    repo = FakeMetadataRepository(save_raises_for={'bad'})
    manifest_repo = FakeManifestRepository(good, bad)

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.indexed == 1
    assert len(summary.failed) == 1
    assert summary.failed[0][0] == bad.path


async def test_reindex_remove_orphans_delete_failure_logged_to_failed() -> None:
    """SQL delete падает → orphan не в orphans, ошибка в failed."""
    orphan = Project(name='cursed', path=Path('/storage/cursed'))
    repo = FakeMetadataRepository(orphan, delete_raises_for={'cursed'})
    manifest_repo = FakeManifestRepository()

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
        remove_orphans=True,
    )

    assert summary.orphans == []
    assert len(summary.failed) == 1
    assert summary.failed[0][0] == orphan.path
    assert 'forced delete failure' in summary.failed[0][1]


async def test_reindex_bootstrap_save_failure_marks_orphan_and_failed() -> None:
    """SQL-only, но manifest.save падает (e.g., каталога нет) → orphan + failed."""
    legacy = Project(name='legacy', path=Path('/storage/legacy'))
    repo = FakeMetadataRepository(legacy)
    manifest_repo = FakeManifestRepository(
        save_raises_for={legacy.path},
    )

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.bootstrapped == 0
    assert summary.orphans == ['legacy']
    assert len(summary.failed) == 1
    assert summary.failed[0][0] == legacy.path


class FakeDecisionRepository:
    """T099: in-memory decisions keyed by project_path → list[Decision]."""

    def __init__(
        self,
        decisions_by_path: dict[Path, list[Decision]] | None = None,
    ) -> None:
        self._by_path: dict[Path, list[Decision]] = decisions_by_path or {}
        self.saved: list[tuple[Path, Decision]] = []

    async def save(self, project_path: Path, decision: Decision) -> Path:
        self._by_path.setdefault(project_path, []).append(decision)
        self.saved.append((project_path, decision))
        return project_path / 'decisions' / f'{decision.id}.md'

    async def load(self, project_path: Path, decision_id: str) -> Decision:
        for d in self._by_path.get(project_path, []):
            if d.id == decision_id:
                return d
        raise DecisionNotFoundError(decision_id)

    async def list_all(self, project_path: Path) -> list[Decision]:
        return list(self._by_path.get(project_path, []))

    async def next_id(self, project_path: Path) -> str:  # pragma: no cover
        existing = self._by_path.get(project_path, [])
        nums = [int(d.id[1:]) for d in existing]
        return f'D{max(nums) + 1 if nums else 1:03d}'


def _make_decision(decision_id: str = 'D001') -> Decision:
    return Decision(
        id=decision_id,
        title='choose',
        date=date(2026, 5, 17),
        status=DecisionStatus.ACCEPTED,
        summary='s',
        rationale='r',
    )


async def test_reindex_syncs_decisions_from_markdown_into_manifest() -> None:
    """T099: Project.decisions пересобирается из markdown при reindex."""
    project = Project(name='p', path=Path('/storage/p'))
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository(project)
    decision_repo = FakeDecisionRepository(
        {project.path: [_make_decision('D001'), _make_decision('D002')]},
    )

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
        decision_repo=decision_repo,
    )

    assert summary.indexed == 1
    reloaded = await manifest_repo.load(project.path)
    assert len(reloaded.decisions) == 2
    assert [r.id for r in reloaded.decisions] == ['D001', 'D002']


async def test_reindex_without_decision_repo_preserves_t098_behavior() -> None:
    """Backward compat: decision_repo=None — поведение как до T099."""
    project = Project(name='p', path=Path('/storage/p'))
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository(project)

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
    )

    assert summary.indexed == 1
    reloaded = await manifest_repo.load(project.path)
    assert reloaded.decisions == ()


@pytest.mark.parametrize('remove_orphans', [False, True])
async def test_reindex_indexed_count_orders_deterministically(
    remove_orphans: bool,
) -> None:
    """discover_all отдаёт sorted paths — обработка детерминирована."""
    a = Project(name='a', path=Path('/storage/a'))
    b = Project(name='b', path=Path('/storage/b'))
    c = Project(name='c', path=Path('/storage/c'))
    repo = FakeMetadataRepository()
    manifest_repo = FakeManifestRepository(b, a, c)  # порядок «вставки»

    summary = await reindex_projects(
        storage_root=Path('/storage'),
        repo=repo,
        manifest_repo=manifest_repo,
        remove_orphans=remove_orphans,
    )

    assert summary.indexed == 3
    assert [p.name for p in manifest_repo.saved] == []  # save'ов не было
