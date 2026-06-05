"""run_export_sim_report use case (T035 Phase 3.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from application.get_project import ProjectNotFoundError
from application.run_export_sim_report import run_export_sim_report
from domain.project import Project, ProjectName
from domain.publication import (
    PublicationBundle,
    PublicationLang,
    SimReportArtifacts,
    SimulationResultsBundle,
)

if TYPE_CHECKING:
    from pathlib import Path


# ─────────────────────────── fakes ────────────────────────────


@dataclass
class _FakeManifestRepo:
    project: Project | None = None

    async def load(self, project_path):  # noqa: ANN001,ANN201
        if self.project is None:
            from ports.outbound.project_manifest_repository import (  # noqa: PLC0415
                ManifestNotFoundError,
            )

            raise ManifestNotFoundError(project_path)
        return self.project

    async def exists(self, project_path):  # noqa: ANN001,ANN201
        return self.project is not None


@dataclass
class _FakeSimReportWriter:
    artifacts_factory: object = None
    calls: list[dict] = field(default_factory=list)

    async def write(self, sim_results, *, out_dir, lang):  # noqa: ANN001,ANN201
        self.calls.append({'sim_results': sim_results, 'out_dir': out_dir, 'lang': lang})
        if callable(self.artifacts_factory):
            return self.artifacts_factory(out_dir)
        return SimReportArtifacts(
            report_md=out_dir / 'report.md',
            plots=(),
            tables=(),
            source_simulation_ts=sim_results.source_simulation_timestamp,
        )


@dataclass
class _FakeReadmeWriter:
    calls: list[dict] = field(default_factory=list)

    async def write(self, bundle, *, out_dir):  # noqa: ANN001,ANN201
        self.calls.append({'bundle': bundle, 'out_dir': out_dir})
        return out_dir / 'README.md'


def _make_project(tmp_path: Path, name: str = 'se-amp') -> Project:
    project_dir = tmp_path / name
    project_dir.mkdir(parents=True, exist_ok=True)
    return Project(
        id=uuid4(),
        name=ProjectName(name),
        path=project_dir,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _make_bundle(
    *,
    project: str = 'se-amp',
    timestamp: datetime | None = None,
) -> SimulationResultsBundle:
    return SimulationResultsBundle(
        project=project,
        efactory_version='0.3.0-dev',
        publication_timestamp=timestamp or datetime(2026, 6, 5, 18, 30, 0, tzinfo=UTC),
    )


# ─────────────────────────── happy path ────────────────────────────


async def test_returns_publication_bundle_with_sim_report(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    sim_results = _make_bundle()
    writer = _FakeSimReportWriter()
    readme = _FakeReadmeWriter()

    bundle, ts_root = await run_export_sim_report(
        sim_results=sim_results,
        lang=PublicationLang.RU,
        projects_root=tmp_path,
        manifest_repo=repo,
        writer=writer,
        readme_writer=readme,
    )

    assert isinstance(bundle, PublicationBundle)
    assert bundle.project == 'se-amp'
    assert bundle.timestamp == sim_results.publication_timestamp
    assert bundle.efactory_version == '0.3.0-dev'
    assert bundle.lang == PublicationLang.RU
    assert bundle.schematic is None
    assert bundle.sim_report is not None
    assert ts_root == project.path / 'out' / 'publications' / '20260605T183000Z'


async def test_creates_out_publications_ts_sim_report_directory_tree(
    tmp_path: Path,
) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    writer = _FakeSimReportWriter()
    readme = _FakeReadmeWriter()

    _, ts_root = await run_export_sim_report(
        sim_results=_make_bundle(),
        lang=PublicationLang.RU,
        projects_root=tmp_path,
        manifest_repo=repo,
        writer=writer,
        readme_writer=readme,
    )

    assert ts_root.is_dir()
    assert (ts_root / 'sim-report').is_dir()


async def test_passes_sim_results_and_lang_to_writer(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    sim_results = _make_bundle()
    writer = _FakeSimReportWriter()
    readme = _FakeReadmeWriter()

    await run_export_sim_report(
        sim_results=sim_results,
        lang=PublicationLang.EN,
        projects_root=tmp_path,
        manifest_repo=repo,
        writer=writer,
        readme_writer=readme,
    )

    assert len(writer.calls) == 1
    assert writer.calls[0]['sim_results'] is sim_results
    assert writer.calls[0]['lang'] == PublicationLang.EN
    assert writer.calls[0]['out_dir'].name == 'sim-report'


async def test_calls_readme_writer_with_bundle_and_ts_root(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    writer = _FakeSimReportWriter()
    readme = _FakeReadmeWriter()

    bundle_out, ts_root = await run_export_sim_report(
        sim_results=_make_bundle(),
        lang=PublicationLang.RU,
        projects_root=tmp_path,
        manifest_repo=repo,
        writer=writer,
        readme_writer=readme,
    )

    assert len(readme.calls) == 1
    assert readme.calls[0]['out_dir'] == ts_root
    assert readme.calls[0]['bundle'] is bundle_out


# ─────────────────────────── collision-safe ts (W-4) ────────────────────────────


async def test_collision_safe_ts_uses_suffix_when_dir_populated(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    pub_root = project.path / 'out' / 'publications'
    pub_root.mkdir(parents=True, exist_ok=True)
    existing = pub_root / '20260605T183000Z'
    existing.mkdir()
    (existing / 'README.md').write_text('prev', encoding='utf-8')

    writer = _FakeSimReportWriter()
    readme = _FakeReadmeWriter()

    _, ts_root = await run_export_sim_report(
        sim_results=_make_bundle(),
        lang=PublicationLang.RU,
        projects_root=tmp_path,
        manifest_repo=repo,
        writer=writer,
        readme_writer=readme,
    )

    assert ts_root.name == '20260605T183000Z-1'


# ─────────────────────────── errors ────────────────────────────


async def test_raises_when_project_not_found(tmp_path: Path) -> None:
    repo = _FakeManifestRepo(project=None)
    writer = _FakeSimReportWriter()
    readme = _FakeReadmeWriter()

    with pytest.raises(ProjectNotFoundError):
        await run_export_sim_report(
            sim_results=_make_bundle(project='nonexistent'),
            lang=PublicationLang.RU,
            projects_root=tmp_path,
            manifest_repo=repo,
            writer=writer,
            readme_writer=readme,
        )
