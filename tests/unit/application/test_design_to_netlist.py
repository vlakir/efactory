"""design_to_netlist use case — экспорт без симуляции (T008 Phase 4)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.design_to_netlist import design_to_netlist
from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError
from domain.simulation import SimulationStatus
from ports.outbound.project_manifest_repository import ManifestNotFoundError
from ports.outbound.schematic_exporter import SchematicExportError

if TYPE_CHECKING:
    from domain.project import Project


class FakeMetadataRepository:
    def __init__(self, project: Project | None = None) -> None:
        self._project = project

    async def get_by_name(self, name: str):  # noqa: ARG002,ANN201
        return self._project


class FakeManifestRepository:
    def __init__(self, project: Project | None = None) -> None:
        self._project = project

    async def load(self, project_path: Path):  # noqa: ARG002,ANN201
        if self._project is None:
            raise ManifestNotFoundError('absent')
        return self._project


class FakeSchematicExporter:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[tuple[Path, Path]] = []

    async def export_spice_netlist(self, schematic: Path, output: Path) -> Path:
        self.calls.append((schematic, output))
        if self._raises is not None:
            raise self._raises
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('* fake netlist\n', encoding='utf-8')
        return output


def _make_project(path: Path):  # noqa: ANN201
    from domain.project import Project

    return Project(name='demo', path=path)


async def test_design_to_netlist_exports_and_returns_netlist_ready(
    tmp_path: Path,
) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()

    sim = await design_to_netlist(
        project_name='demo',
        schematic=Path('schematic/rc.kicad_sch'),
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
    )

    assert sim.status is SimulationStatus.NETLIST_READY
    assert sim.netlist_path == project.path / 'sim' / 'rc.cir'
    assert sim.schematic_path == project.path / 'schematic' / 'rc.kicad_sch'
    assert sim.result is None
    assert exporter.calls == [
        (project.path / 'schematic' / 'rc.kicad_sch', sim.netlist_path),
    ]


async def test_design_to_netlist_absolute_schematic_path_kept(
    tmp_path: Path,
) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    abs_schematic = tmp_path / 'external' / 'imported.kicad_sch'
    abs_schematic.parent.mkdir(parents=True, exist_ok=True)
    abs_schematic.write_text('dummy')

    sim = await design_to_netlist(
        project_name='demo',
        schematic=abs_schematic,
        repo=FakeMetadataRepository(project),
        manifest_repo=FakeManifestRepository(project),
        exporter=FakeSchematicExporter(),
    )

    assert sim.schematic_path == abs_schematic


async def test_design_to_netlist_custom_netlist_output(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    custom_output = tmp_path / 'my_out' / 'custom.cir'

    sim = await design_to_netlist(
        project_name='demo',
        schematic=Path('schematic/x.kicad_sch'),
        netlist_output=custom_output,
        repo=FakeMetadataRepository(project),
        manifest_repo=FakeManifestRepository(project),
        exporter=FakeSchematicExporter(),
    )

    assert sim.netlist_path == custom_output


async def test_design_to_netlist_unknown_project_raises() -> None:
    with pytest.raises(ProjectNotFoundError):
        await design_to_netlist(
            project_name='ghost',
            schematic=Path('schematic/x.kicad_sch'),
            repo=FakeMetadataRepository(None),
            manifest_repo=FakeManifestRepository(None),
            exporter=FakeSchematicExporter(),
        )


async def test_design_to_netlist_manifest_missing_raises(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    with pytest.raises(ProjectManifestMissingError):
        await design_to_netlist(
            project_name='demo',
            schematic=Path('x.kicad_sch'),
            repo=FakeMetadataRepository(project),
            manifest_repo=FakeManifestRepository(None),
            exporter=FakeSchematicExporter(),
        )


async def test_design_to_netlist_propagates_exporter_error(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    exporter = FakeSchematicExporter(raises=SchematicExportError('bad sch'))

    with pytest.raises(SchematicExportError, match='bad sch'):
        await design_to_netlist(
            project_name='demo',
            schematic=Path('schematic/x.kicad_sch'),
            repo=FakeMetadataRepository(project),
            manifest_repo=FakeManifestRepository(project),
            exporter=exporter,
        )
