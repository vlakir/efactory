"""Unit tests `compose_sim_results_bundle` (T191)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.compose_sim_results_bundle import compose_sim_results_bundle
from domain.publication import SimulationResultsBundle
from domain.raw_waveform import RawWaveform, WaveformAnalysisType
from domain.simulation import (
    AcAnalysis,
    AcSweep,
    Simulation,
    SimulationResult,
    SimulationStatus,
    TimeSeries,
    TranAnalysis,
)

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter


class _FakeRawWaveformRepo:
    def __init__(
        self,
        *,
        tran: RawWaveform | None = None,
        ac: RawWaveform | None = None,
    ) -> None:
        self._tran = tran
        self._ac = ac
        self.writes: list[tuple[RawWaveform, Path]] = []

    async def write(self, *, waveform: RawWaveform, project_root: Path) -> Path:
        self.writes.append((waveform, project_root))
        return project_root / 'wf.json'

    async def load_latest(
        self,
        *,
        project_root: Path,
        analysis_type: WaveformAnalysisType,
    ) -> RawWaveform | None:
        if analysis_type == WaveformAnalysisType.TRAN:
            return self._tran
        if analysis_type == WaveformAnalysisType.AC:
            return self._ac
        return None


def _tran_waveform() -> RawWaveform:
    return RawWaveform(
        timestamp='2026-06-06T01:00:00Z',
        analysis_type=WaveformAnalysisType.TRAN,
        source_netlist='amp.cir',
        x_axis_name='time',
        x_axis=(0.0, 1e-6, 2e-6),
        traces={'v(out)': (0.0, 0.5, 1.0)},
    )


def _ac_waveform() -> RawWaveform:
    return RawWaveform(
        timestamp='2026-06-06T01:00:00Z',
        analysis_type=WaveformAnalysisType.AC,
        source_netlist='amp.cir',
        x_axis_name='frequency',
        x_axis=(10.0, 100.0, 1000.0),
        traces={'v(out)': (1.0, 0.9, 0.5)},
        traces_imag={'v(out)': (0.0, 0.1, 0.3)},
    )


class _FakeManifestRepo:
    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    async def load(self, *, name: str, projects_root: Path) -> object:  # noqa: ARG002
        return None


def _make_project(project_root: Path, name: str = 'demo') -> Path:
    proj_dir = project_root / name
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / '.efactory').mkdir(exist_ok=True)
    return proj_dir


@pytest.fixture
def projects_root_path(tmp_path: Path) -> Path:
    return tmp_path / 'projects'


@pytest.mark.asyncio
async def test_no_rerun_loads_persistent_tran_and_ac(
    projects_root_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proj_dir = _make_project(projects_root_path)
    repo = _FakeRawWaveformRepo(tran=_tran_waveform(), ac=_ac_waveform())

    async def _fake_get_project(**_: object) -> object:
        class _P:
            path = proj_dir

        return _P()

    monkeypatch.setattr(
        'application.compose_sim_results_bundle.get_project',
        _fake_get_project,
    )

    bundle = await compose_sim_results_bundle(
        project_name='demo',
        efactory_version='0.1.0',
        rerun=False,
        schematic=None,
        tran_analysis=None,
        ac_analysis=None,
        tran_signals=(),
        ac_signals=(),
        sim_timeout_seconds=60.0,
        projects_root=projects_root_path,
        manifest_repo=_FakeManifestRepo(proj_dir),  # type: ignore[arg-type]
        exporter=object(),  # type: ignore[arg-type]
        simulator=object(),  # type: ignore[arg-type]
        raw_waveform_repo=repo,
    )

    assert isinstance(bundle, SimulationResultsBundle)
    assert bundle.tran is not None
    assert bundle.ac_sweep is not None
    assert bundle.tran_signals == ('v(out)',)
    assert bundle.ac_signals == ('v(out)',)
    assert bundle.source_simulation_timestamp is not None


@pytest.mark.asyncio
async def test_no_rerun_missing_waveforms_yields_empty_bundle(
    projects_root_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proj_dir = _make_project(projects_root_path)
    repo = _FakeRawWaveformRepo()  # both None

    async def _fake_get_project(**_: object) -> object:
        class _P:
            path = proj_dir

        return _P()

    monkeypatch.setattr(
        'application.compose_sim_results_bundle.get_project',
        _fake_get_project,
    )

    bundle = await compose_sim_results_bundle(
        project_name='demo',
        efactory_version='0.1.0',
        rerun=False,
        schematic=None,
        tran_analysis=None,
        ac_analysis=None,
        tran_signals=(),
        ac_signals=(),
        sim_timeout_seconds=60.0,
        projects_root=projects_root_path,
        manifest_repo=_FakeManifestRepo(proj_dir),  # type: ignore[arg-type]
        exporter=object(),  # type: ignore[arg-type]
        simulator=object(),  # type: ignore[arg-type]
        raw_waveform_repo=repo,
    )
    assert bundle.tran is None
    assert bundle.ac_sweep is None
    assert bundle.tran_signals == ()
    assert bundle.ac_signals == ()


@pytest.mark.asyncio
async def test_rerun_requires_schematic(
    projects_root_path: Path,
) -> None:
    repo = _FakeRawWaveformRepo()
    with pytest.raises(ValueError, match='rerun=True требует schematic'):
        await compose_sim_results_bundle(
            project_name='demo',
            efactory_version='0.1.0',
            rerun=True,
            schematic=None,
            tran_analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
            ac_analysis=None,
            tran_signals=(),
            ac_signals=(),
            sim_timeout_seconds=60.0,
            projects_root=projects_root_path,
            manifest_repo=_FakeManifestRepo(projects_root_path),  # type: ignore[arg-type]
            exporter=object(),  # type: ignore[arg-type]
            simulator=object(),  # type: ignore[arg-type]
            raw_waveform_repo=repo,
        )


@pytest.mark.asyncio
async def test_rerun_calls_design_to_sim_per_analysis(
    projects_root_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRawWaveformRepo()
    calls: list[AnalysisSpec] = []

    tran_result = SimulationResult(
        time_series=TimeSeries(time=(0.0, 1.0), traces={'v(out)': (0.0, 1.0)}),
    )
    ac_result = SimulationResult(
        ac_sweep=AcSweep(
            frequency=(1.0, 10.0),
            traces_real={'v(out)': (1.0, 0.5)},
            traces_imag={'v(out)': (0.0, 0.1)},
        ),
    )

    async def _fake_design_to_sim(
        *,
        project_name: str,  # noqa: ARG001
        schematic: Path,  # noqa: ARG001
        analysis: AnalysisSpec,
        **_kwargs: object,
    ) -> Simulation:
        calls.append(analysis)
        result = (
            tran_result
            if isinstance(analysis, TranAnalysis)
            else ac_result
            if isinstance(analysis, AcAnalysis)
            else SimulationResult(operating_points={})
        )
        return Simulation(
            project_id=__import__('uuid').uuid4(),
            schematic_path=schematic,
            status=SimulationStatus.SIMULATED,
            result=result,
        )

    monkeypatch.setattr(
        'application.compose_sim_results_bundle.design_to_sim',
        _fake_design_to_sim,
    )

    bundle = await compose_sim_results_bundle(
        project_name='demo',
        efactory_version='0.2.0',
        rerun=True,
        schematic=Path('demo.kicad_sch'),
        tran_analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
        ac_analysis=AcAnalysis(
            sweep='dec', n_points=10, f_start=1.0, f_stop=1e6
        ),
        tran_signals=(),
        ac_signals=(),
        sim_timeout_seconds=60.0,
        projects_root=projects_root_path,
        manifest_repo=_FakeManifestRepo(projects_root_path),  # type: ignore[arg-type]
        exporter=object(),  # type: ignore[arg-type]
        simulator=object(),  # type: ignore[arg-type]
        raw_waveform_repo=repo,
    )

    assert len(calls) == 2
    assert isinstance(calls[0], TranAnalysis)
    assert isinstance(calls[1], AcAnalysis)
    assert bundle.tran is not None
    assert bundle.ac_sweep is not None
    assert bundle.source_simulation_timestamp is None
    assert bundle.efactory_version == '0.2.0'


@pytest.mark.asyncio
async def test_rerun_only_tran(
    projects_root_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRawWaveformRepo()

    async def _fake(
        *,
        project_name: str,  # noqa: ARG001
        schematic: Path,
        analysis: AnalysisSpec,
        **_kwargs: object,
    ) -> Simulation:
        return Simulation(
            project_id=__import__('uuid').uuid4(),
            schematic_path=schematic,
            status=SimulationStatus.SIMULATED,
            result=SimulationResult(
                time_series=TimeSeries(
                    time=(0.0,), traces={'v(a)': (1.0,), 'v(b)': (2.0,)}
                ),
            )
            if isinstance(analysis, TranAnalysis)
            else SimulationResult(operating_points={}),
        )

    monkeypatch.setattr(
        'application.compose_sim_results_bundle.design_to_sim',
        _fake,
    )

    bundle = await compose_sim_results_bundle(
        project_name='demo',
        efactory_version='0.1.0',
        rerun=True,
        schematic=Path('s.kicad_sch'),
        tran_analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
        ac_analysis=None,
        tran_signals=(),
        ac_signals=(),
        sim_timeout_seconds=60.0,
        projects_root=projects_root_path,
        manifest_repo=_FakeManifestRepo(projects_root_path),  # type: ignore[arg-type]
        exporter=object(),  # type: ignore[arg-type]
        simulator=object(),  # type: ignore[arg-type]
        raw_waveform_repo=repo,
    )
    assert bundle.tran is not None
    assert bundle.ac_sweep is None
    assert set(bundle.tran_signals) == {'v(a)', 'v(b)'}


@pytest.mark.asyncio
async def test_custom_signals_filter_applied(
    projects_root_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proj_dir = _make_project(projects_root_path)
    wf = RawWaveform(
        timestamp='2026-06-06T01:00:00Z',
        analysis_type=WaveformAnalysisType.TRAN,
        source_netlist='amp.cir',
        x_axis_name='time',
        x_axis=(0.0, 1.0),
        traces={'v(in)': (0.0, 1.0), 'v(out)': (0.0, 5.0)},
    )
    repo = _FakeRawWaveformRepo(tran=wf)

    async def _fake_get_project(**_: object) -> object:
        class _P:
            path = proj_dir

        return _P()

    monkeypatch.setattr(
        'application.compose_sim_results_bundle.get_project',
        _fake_get_project,
    )

    bundle = await compose_sim_results_bundle(
        project_name='demo',
        efactory_version='0.1.0',
        rerun=False,
        schematic=None,
        tran_analysis=None,
        ac_analysis=None,
        tran_signals=('v(out)',),
        ac_signals=(),
        sim_timeout_seconds=60.0,
        projects_root=projects_root_path,
        manifest_repo=_FakeManifestRepo(proj_dir),  # type: ignore[arg-type]
        exporter=object(),  # type: ignore[arg-type]
        simulator=object(),  # type: ignore[arg-type]
        raw_waveform_repo=repo,
    )
    assert bundle.tran_signals == ('v(out)',)
