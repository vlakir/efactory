"""run_export_schematic_publication use case (T035 Phase 3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from application.get_project import ProjectNotFoundError
from application.run_export_schematic_publication import (
    run_export_schematic_publication,
)
from domain.project import Project, ProjectName
from domain.publication import (
    MultiSheetMode,
    PublicationBundle,
    PublicationLang,
    SchematicPublicationArtifacts,
    SheetArtifactSet,
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
class _FakeRenderer:
    artifacts: SchematicPublicationArtifacts
    calls: list[dict] = field(default_factory=list)

    async def render(
        self,
        schematic,  # noqa: ANN001
        out_dir,  # noqa: ANN001
        *,
        multi_sheet_mode,  # noqa: ANN001
    ) -> SchematicPublicationArtifacts:
        self.calls.append(
            {
                'schematic': schematic,
                'out_dir': out_dir,
                'multi_sheet_mode': multi_sheet_mode,
            },
        )
        return self.artifacts


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


def _make_artifacts(out_dir: Path) -> SchematicPublicationArtifacts:
    color = (
        SheetArtifactSet(
            sheet_name='se-amp',
            svg=out_dir / 'color' / 'per-sheet' / 'se-amp.svg',
            pdf=out_dir / 'color' / 'per-sheet' / 'se-amp.pdf',
            png=out_dir / 'color' / 'per-sheet' / 'se-amp.png',
        ),
    )
    bw = (
        SheetArtifactSet(
            sheet_name='se-amp',
            svg=out_dir / 'bw' / 'per-sheet' / 'se-amp.svg',
            pdf=out_dir / 'bw' / 'per-sheet' / 'se-amp.pdf',
            png=out_dir / 'bw' / 'per-sheet' / 'se-amp.png',
        ),
    )
    return SchematicPublicationArtifacts(
        color_per_sheet=color,
        bw_per_sheet=bw,
        color_combined=None,
        bw_combined=None,
    )


# ─────────────────────────── happy path ────────────────────────────


async def test_returns_publication_bundle_with_schematic(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    fixed_now = datetime(2026, 6, 5, 18, 30, 0, tzinfo=UTC)
    expected_ts_root = project.path / 'out' / 'publications' / '20260605T183000Z'
    artifacts = _make_artifacts(expected_ts_root / 'schematic')
    renderer = _FakeRenderer(artifacts=artifacts)
    readme = _FakeReadmeWriter()

    bundle, ts_root = await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'se-amp.kicad_sch',
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
        now=lambda: fixed_now,
    )

    assert isinstance(bundle, PublicationBundle)
    assert bundle.project == 'se-amp'
    assert bundle.timestamp == fixed_now
    assert bundle.efactory_version == '0.3.0-dev'
    assert bundle.lang == PublicationLang.RU
    assert bundle.schematic is artifacts
    assert bundle.sim_report is None
    assert ts_root == expected_ts_root


async def test_creates_out_publications_ts_directory_tree(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    fixed_now = datetime(2026, 6, 5, 18, 30, 0, tzinfo=UTC)
    expected_ts_root = project.path / 'out' / 'publications' / '20260605T183000Z'
    renderer = _FakeRenderer(artifacts=_make_artifacts(expected_ts_root / 'schematic'))
    readme = _FakeReadmeWriter()

    _, ts_root = await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'se-amp.kicad_sch',
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
        now=lambda: fixed_now,
    )

    assert ts_root.is_dir()
    assert (ts_root / 'schematic').is_dir()


async def test_passes_resolved_schematic_path_to_renderer(tmp_path: Path) -> None:
    """Schematic relative — resolved via project.path; absolute — pass through."""
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    artifacts = _make_artifacts(project.path / 'tmp')
    renderer = _FakeRenderer(artifacts=artifacts)
    readme = _FakeReadmeWriter()

    await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'sub' / 'root.kicad_sch',
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
    )

    assert renderer.calls[0]['schematic'] == project.path / 'sub' / 'root.kicad_sch'


async def test_passes_multi_sheet_mode_to_renderer(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    artifacts = _make_artifacts(project.path / 'tmp')
    renderer = _FakeRenderer(artifacts=artifacts)
    readme = _FakeReadmeWriter()

    await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'se-amp.kicad_sch',
        multi_sheet_mode=MultiSheetMode.COMBINED,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
    )

    assert renderer.calls[0]['multi_sheet_mode'] == MultiSheetMode.COMBINED


async def test_calls_readme_writer_with_bundle_and_ts_root(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    fixed_now = datetime(2026, 6, 5, 18, 30, 0, tzinfo=UTC)
    expected_ts_root = project.path / 'out' / 'publications' / '20260605T183000Z'
    renderer = _FakeRenderer(artifacts=_make_artifacts(expected_ts_root / 'schematic'))
    readme = _FakeReadmeWriter()

    await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'se-amp.kicad_sch',
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
        now=lambda: fixed_now,
    )

    assert len(readme.calls) == 1
    assert readme.calls[0]['out_dir'] == expected_ts_root
    assert isinstance(readme.calls[0]['bundle'], PublicationBundle)


# ─────────────────────────── collision-safe ts (W-4) ────────────────────────────


async def test_collision_safe_ts_uses_suffix_when_dir_already_populated(
    tmp_path: Path,
) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    fixed_now = datetime(2026, 6, 5, 18, 30, 0, tzinfo=UTC)
    pub_root = project.path / 'out' / 'publications'
    pub_root.mkdir(parents=True, exist_ok=True)
    # Уже существующий populated ts-каталог:
    existing = pub_root / '20260605T183000Z'
    existing.mkdir()
    (existing / 'README.md').write_text('previous run', encoding='utf-8')

    artifacts = _make_artifacts(pub_root / '20260605T183000Z-1' / 'schematic')
    renderer = _FakeRenderer(artifacts=artifacts)
    readme = _FakeReadmeWriter()

    _, ts_root = await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'se-amp.kicad_sch',
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
        now=lambda: fixed_now,
    )

    assert ts_root.name == '20260605T183000Z-1'
    assert ts_root.is_dir()


async def test_collision_safe_ts_reuses_existing_empty_dir(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    repo = _FakeManifestRepo(project=project)
    fixed_now = datetime(2026, 6, 5, 18, 30, 0, tzinfo=UTC)
    pub_root = project.path / 'out' / 'publications'
    pub_root.mkdir(parents=True, exist_ok=True)
    empty_existing = pub_root / '20260605T183000Z'
    empty_existing.mkdir()

    artifacts = _make_artifacts(empty_existing / 'schematic')
    renderer = _FakeRenderer(artifacts=artifacts)
    readme = _FakeReadmeWriter()

    _, ts_root = await run_export_schematic_publication(
        project_name='se-amp',
        schematic=project.path / 'se-amp.kicad_sch',
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
        lang=PublicationLang.RU,
        efactory_version='0.3.0-dev',
        projects_root=tmp_path,
        manifest_repo=repo,
        renderer=renderer,
        readme_writer=readme,
        now=lambda: fixed_now,
    )

    assert ts_root == empty_existing


# ─────────────────────────── errors ────────────────────────────


async def test_raises_when_project_not_found(tmp_path: Path) -> None:
    repo = _FakeManifestRepo(project=None)
    renderer = _FakeRenderer(artifacts=_make_artifacts(tmp_path))
    readme = _FakeReadmeWriter()

    with pytest.raises(ProjectNotFoundError):
        await run_export_schematic_publication(
            project_name='nonexistent',
            schematic=tmp_path / 'x.kicad_sch',
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
            lang=PublicationLang.RU,
            efactory_version='0.3.0-dev',
            projects_root=tmp_path,
            manifest_repo=repo,
            renderer=renderer,
            readme_writer=readme,
        )
