"""validate_manifests use case (T157: renamed from reindex_projects)."""

from __future__ import annotations

from pathlib import Path

from application.reindex_projects import (
    ReindexSummary,
    ValidateManifestsSummary,
    reindex_projects,
    validate_manifests,
)
from domain.project import Project
from ports.outbound.project_manifest_repository import ManifestNotFoundError


class FakeManifestRepository:
    def __init__(
        self,
        *projects: Project,
        broken_paths: set[Path] | None = None,
    ) -> None:
        self._by_path: dict[Path, Project] = {p.path: p for p in projects}
        self._broken = broken_paths or set()

    async def save(self, project: Project) -> None:
        self._by_path[project.path] = project

    async def load(self, project_path: Path) -> Project:
        if project_path in self._broken or project_path not in self._by_path:
            raise ManifestNotFoundError(str(project_path))
        return self._by_path[project_path]

    async def exists(self, project_path: Path) -> bool:
        return project_path in self._by_path

    async def discover_all(self, storage_root: Path) -> list[Path]:
        return sorted(p for p in self._by_path if p.parent == storage_root)


async def test_validate_manifests_returns_summary_on_clean_root() -> None:
    p1 = Project(name='a', path=Path('/p/a'))
    p2 = Project(name='b', path=Path('/p/b'))
    manifest_repo = FakeManifestRepository(p1, p2)

    summary = await validate_manifests(
        storage_root=Path('/p'),
        manifest_repo=manifest_repo,
    )

    assert isinstance(summary, ValidateManifestsSummary)
    assert summary.valid == 2
    assert summary.failed == []


async def test_validate_manifests_collects_failures() -> None:
    good = Project(name='good', path=Path('/p/good'))
    broken = Project(name='broken', path=Path('/p/broken'))
    manifest_repo = FakeManifestRepository(
        good, broken,
        broken_paths={broken.path},
    )

    summary = await validate_manifests(
        storage_root=Path('/p'),
        manifest_repo=manifest_repo,
    )

    assert summary.valid == 1
    assert len(summary.failed) == 1
    assert summary.failed[0][0] == broken.path


async def test_validate_manifests_empty_root() -> None:
    manifest_repo = FakeManifestRepository()

    summary = await validate_manifests(
        storage_root=Path('/p'),
        manifest_repo=manifest_repo,
    )

    assert summary.valid == 0
    assert summary.failed == []


async def test_reindex_projects_backward_compat_alias() -> None:
    """T157: `reindex_projects` остаётся как alias `validate_manifests`."""
    assert reindex_projects is validate_manifests
    assert ReindexSummary is ValidateManifestsSummary
