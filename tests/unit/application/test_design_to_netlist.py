"""design_to_netlist use case — T157 filesystem-first."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.design_to_netlist import design_to_netlist
from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError
from domain.project import Project
from domain.simulation import SimulationStatus
from ports.outbound.project_manifest_repository import ManifestNotFoundError
from ports.outbound.schematic_exporter import SchematicExportError


class FakeManifestRepository:
    def __init__(self, project: Project | None = None) -> None:
        self._project = project

    async def load(self, project_path: Path):  # noqa: ARG002, ANN201
        if self._project is None:
            raise ManifestNotFoundError('absent')
        return self._project

    async def exists(self, project_path: Path) -> bool:  # noqa: ARG002
        return self._project is not None


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


def _setup_project(tmp_path: Path, name: str = 'demo') -> Project:
    project_path = tmp_path / name
    project_path.mkdir(parents=True, exist_ok=True)
    return Project(name=name, path=project_path)


async def test_design_to_netlist_exports_and_returns_netlist_ready(
    tmp_path: Path,
) -> None:
    project = _setup_project(tmp_path)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()

    sim = await design_to_netlist(
        project_name='demo',
        schematic=Path('schematic/rc.kicad_sch'),
        projects_root=tmp_path,
        manifest_repo=manifest_repo,
        exporter=exporter,
    )

    assert sim.status is SimulationStatus.NETLIST_READY
    assert sim.netlist_path == project.path / 'sim' / 'rc.cir'
    assert sim.schematic_path == project.path / 'schematic' / 'rc.kicad_sch'


async def test_design_to_netlist_absolute_schematic_path_kept(
    tmp_path: Path,
) -> None:
    project = _setup_project(tmp_path)
    abs_schematic = tmp_path / 'external' / 'imported.kicad_sch'
    abs_schematic.parent.mkdir(parents=True, exist_ok=True)
    abs_schematic.write_text('dummy')

    sim = await design_to_netlist(
        project_name='demo',
        schematic=abs_schematic,
        projects_root=tmp_path,
        manifest_repo=FakeManifestRepository(project),
        exporter=FakeSchematicExporter(),
    )

    assert sim.schematic_path == abs_schematic


async def test_design_to_netlist_custom_netlist_output(tmp_path: Path) -> None:
    project = _setup_project(tmp_path)
    custom_output = tmp_path / 'my_out' / 'custom.cir'

    sim = await design_to_netlist(
        project_name='demo',
        schematic=Path('schematic/x.kicad_sch'),
        netlist_output=custom_output,
        projects_root=tmp_path,
        manifest_repo=FakeManifestRepository(project),
        exporter=FakeSchematicExporter(),
    )

    assert sim.netlist_path == custom_output


async def test_design_to_netlist_unknown_project_raises(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        await design_to_netlist(
            project_name='ghost',
            schematic=Path('schematic/x.kicad_sch'),
            projects_root=tmp_path,
            manifest_repo=FakeManifestRepository(None),
            exporter=FakeSchematicExporter(),
        )


async def test_design_to_netlist_manifest_missing_raises(tmp_path: Path) -> None:
    (tmp_path / 'demo').mkdir()
    with pytest.raises(ProjectManifestMissingError):
        await design_to_netlist(
            project_name='demo',
            schematic=Path('x.kicad_sch'),
            projects_root=tmp_path,
            manifest_repo=FakeManifestRepository(None),
            exporter=FakeSchematicExporter(),
        )


async def test_design_to_netlist_propagates_exporter_error(tmp_path: Path) -> None:
    project = _setup_project(tmp_path)
    exporter = FakeSchematicExporter(raises=SchematicExportError('bad sch'))

    with pytest.raises(SchematicExportError, match='bad sch'):
        await design_to_netlist(
            project_name='demo',
            schematic=Path('schematic/x.kicad_sch'),
            projects_root=tmp_path,
            manifest_repo=FakeManifestRepository(project),
            exporter=exporter,
        )
