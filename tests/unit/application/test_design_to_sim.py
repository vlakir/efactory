"""design_to_sim use case — unit с fake-портами (T004 / T008)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.design_to_sim import design_to_sim
from application.errors import ProjectManifestMissingError
from application.get_project import ProjectNotFoundError
from domain.simulation import (
    AnalysisSpec,
    OpAnalysis,
    SimulationResult,
    SimulationStatus,
)
from ports.outbound.project_manifest_repository import ManifestNotFoundError
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)

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


class FakeSimulator:
    def __init__(
        self,
        *,
        result: SimulationResult | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


def _make_project(path: Path):  # noqa: ANN201
    from domain.project import Project

    return Project(name='demo', path=path)


async def test_design_to_sim_exports_netlist_and_stub_simulator_returns_netlist_ready(
    tmp_path: Path,
) -> None:
    """T004 acceptance: SimulatorUnavailableError → status=NETLIST_READY."""
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    schematic = Path('schematic/rc.kicad_sch')  # relative

    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(
        raises=SimulatorUnavailableError('stub'),
    )

    sim = await design_to_sim(
        project_name='demo',
        analysis=OpAnalysis(),
                schematic=schematic,
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
        simulator=simulator,
    )

    assert sim.status is SimulationStatus.NETLIST_READY
    assert sim.netlist_path == project.path / 'sim' / 'rc.cir'
    assert sim.schematic_path == project.path / 'schematic' / 'rc.kicad_sch'
    assert sim.netlist_path is not None
    assert sim.netlist_path.is_file()  # exporter создал
    assert exporter.calls == [
        (project.path / 'schematic' / 'rc.kicad_sch', sim.netlist_path),
    ]
    assert sim.result is None


async def test_design_to_sim_returns_simulated_when_real_simulator_works(
    tmp_path: Path,
) -> None:
    """Будущий T008: реальный Simulator → status=SIMULATED."""
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(
        result=SimulationResult(operating_points={'V(out)': 3.3}),
    )

    sim = await design_to_sim(
        project_name='demo',
        analysis=OpAnalysis(),
                schematic=Path('schematic/rc.kicad_sch'),
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
        simulator=simulator,
    )

    assert sim.status is SimulationStatus.SIMULATED
    assert sim.result is not None
    assert sim.result.operating_points == {'V(out)': 3.3}
    assert len(simulator.calls) == 1
    netlist_called, analysis_called, timeout_called = simulator.calls[0]
    assert netlist_called == project.path / 'sim' / 'rc.cir'
    assert isinstance(analysis_called, OpAnalysis)
    assert timeout_called == 60.0


async def test_design_to_sim_absolute_schematic_path_kept(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    abs_schematic = tmp_path / 'external' / 'imported.kicad_sch'
    abs_schematic.parent.mkdir(parents=True, exist_ok=True)
    abs_schematic.write_text('dummy')
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(raises=SimulatorUnavailableError('stub'))

    sim = await design_to_sim(
        project_name='demo',
        analysis=OpAnalysis(),
                schematic=abs_schematic,
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
        simulator=simulator,
    )

    assert sim.schematic_path == abs_schematic


async def test_design_to_sim_custom_netlist_output(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    custom_output = tmp_path / 'my_out' / 'custom.cir'
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(raises=SimulatorUnavailableError('stub'))

    sim = await design_to_sim(
        project_name='demo',
        analysis=OpAnalysis(),
                schematic=Path('schematic/x.kicad_sch'),
        netlist_output=custom_output,
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
        simulator=simulator,
    )

    assert sim.netlist_path == custom_output


async def test_design_to_sim_unknown_project_raises() -> None:
    repo = FakeMetadataRepository(None)
    manifest_repo = FakeManifestRepository(None)
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(raises=SimulatorUnavailableError('stub'))

    with pytest.raises(ProjectNotFoundError):
        await design_to_sim(
            project_name='ghost',
            analysis=OpAnalysis(),
            schematic=Path('schematic/x.kicad_sch'),
            repo=repo,
            manifest_repo=manifest_repo,
            exporter=exporter,
            simulator=simulator,
        )


async def test_design_to_sim_manifest_missing_raises(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(None)  # manifest нет
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(raises=SimulatorUnavailableError('stub'))

    with pytest.raises(ProjectManifestMissingError):
        await design_to_sim(
            project_name='demo',
            analysis=OpAnalysis(),
                    schematic=Path('x.kicad_sch'),
            repo=repo,
            manifest_repo=manifest_repo,
            exporter=exporter,
            simulator=simulator,
        )


async def test_design_to_sim_propagates_exporter_error(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter(raises=SchematicExportError('bad sch'))
    simulator = FakeSimulator(raises=SimulatorUnavailableError('stub'))

    with pytest.raises(SchematicExportError, match='bad sch'):
        await design_to_sim(
            project_name='demo',
            analysis=OpAnalysis(),
                    schematic=Path('schematic/x.kicad_sch'),
            repo=repo,
            manifest_repo=manifest_repo,
            exporter=exporter,
            simulator=simulator,
        )


async def test_design_to_sim_propagates_simulation_failed(tmp_path: Path) -> None:
    """Future T008: SimulationFailedError (convergence) → пробрасывается."""
    project = _make_project(tmp_path / 'demo')
    project.path.mkdir(parents=True, exist_ok=True)
    repo = FakeMetadataRepository(project)
    manifest_repo = FakeManifestRepository(project)
    exporter = FakeSchematicExporter()
    simulator = FakeSimulator(raises=SimulationFailedError('no conv'))

    with pytest.raises(SimulationFailedError):
        await design_to_sim(
            project_name='demo',
            analysis=OpAnalysis(),
                    schematic=Path('schematic/x.kicad_sch'),
            repo=repo,
            manifest_repo=manifest_repo,
            exporter=exporter,
            simulator=simulator,
        )
