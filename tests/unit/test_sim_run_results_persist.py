"""Tests для интеграции `sim_run` с SimResultsRepository (T016 Phase C).

`sim_run` — тонкая обёртка над `Simulator.run`; T016 расширяет её
двумя optional параметрами (`sim_results_writer`, `project_root`).
При обоих заданных — после `simulator.run` use case собирает
`SimResult` snapshot и просит writer его persist'ить. При одном из
двух — `ValueError`, чтобы не получить неконсистентный вызов.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.sim_run import sim_run
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import (
    OpAnalysis,
    SimulationResult,
    TimeSeries,
    TranAnalysis,
)

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec


class _FakeSimulator:
    def __init__(self, result: SimulationResult) -> None:
        self._result = result
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        return self._result


class _RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[SimResult, Path]] = []

    async def write(self, *, result: SimResult, project_root: Path) -> Path:
        self.calls.append((result, project_root))
        return project_root / '.efactory' / 'sim-results' / 'fake.json'


@pytest.fixture
def op_simulation_result() -> SimulationResult:
    return SimulationResult(operating_points={'V(out)': 1.23, 'V(in)': 0.5})


@pytest.fixture
def tran_simulation_result() -> SimulationResult:
    return SimulationResult(
        time_series=TimeSeries(
            time=(0.0, 1.0, 2.0),
            traces={'V(out)': (0.0, 0.5, 1.0)},
        ),
    )


@pytest.mark.asyncio
async def test_sim_run_works_without_writer(
    tmp_path: Path, op_simulation_result: SimulationResult
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.touch()
    sim = _FakeSimulator(op_simulation_result)

    result = await sim_run(netlist=netlist, analysis=OpAnalysis(), simulator=sim)

    assert result is op_simulation_result
    assert sim.calls == [(netlist, OpAnalysis(), 60.0)]


@pytest.mark.asyncio
async def test_sim_run_calls_writer_when_configured(
    tmp_path: Path, op_simulation_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist = project_root / 'amp.cir'
    netlist.touch()
    sim = _FakeSimulator(op_simulation_result)
    writer = _RecordingWriter()

    await sim_run(
        netlist=netlist,
        analysis=OpAnalysis(),
        simulator=sim,
        sim_results_writer=writer,
        project_root=project_root,
    )

    assert len(writer.calls) == 1
    snapshot, root = writer.calls[0]
    assert root == project_root
    assert snapshot.analysis_type is AnalysisType.OP
    assert snapshot.tool == 'ngspice'
    assert snapshot.source_file == 'amp.cir'
    assert snapshot.duration_seconds >= 0
    assert snapshot.summary


@pytest.mark.asyncio
async def test_sim_run_writer_records_tran_summary(
    tmp_path: Path, tran_simulation_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist = project_root / 'amp.cir'
    netlist.touch()
    analysis = TranAnalysis(t_step=1e-6, t_stop=1e-3)
    sim = _FakeSimulator(tran_simulation_result)
    writer = _RecordingWriter()

    await sim_run(
        netlist=netlist,
        analysis=analysis,
        simulator=sim,
        sim_results_writer=writer,
        project_root=project_root,
    )

    snapshot, _ = writer.calls[0]
    assert snapshot.analysis_type is AnalysisType.TRAN
    assert 'tran' in snapshot.summary.lower() or 'time' in snapshot.summary.lower()


@pytest.mark.asyncio
async def test_sim_run_source_file_falls_back_when_outside_project_root(
    tmp_path: Path, op_simulation_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist_outside = tmp_path / 'shared' / 'amp.cir'
    netlist_outside.parent.mkdir()
    netlist_outside.touch()
    sim = _FakeSimulator(op_simulation_result)
    writer = _RecordingWriter()

    await sim_run(
        netlist=netlist_outside,
        analysis=OpAnalysis(),
        simulator=sim,
        sim_results_writer=writer,
        project_root=project_root,
    )

    snapshot, _ = writer.calls[0]
    assert snapshot.source_file == 'amp.cir'


@pytest.mark.asyncio
async def test_sim_run_rejects_partial_persist_args(
    tmp_path: Path, op_simulation_result: SimulationResult
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.touch()
    sim = _FakeSimulator(op_simulation_result)
    writer = _RecordingWriter()

    with pytest.raises(ValueError, match='project_root'):
        await sim_run(
            netlist=netlist,
            analysis=OpAnalysis(),
            simulator=sim,
            sim_results_writer=writer,
        )

    with pytest.raises(ValueError, match='sim_results_writer'):
        await sim_run(
            netlist=netlist,
            analysis=OpAnalysis(),
            simulator=sim,
            project_root=tmp_path,
        )


@pytest.mark.asyncio
async def test_sim_run_does_not_persist_when_both_omitted(
    tmp_path: Path, op_simulation_result: SimulationResult
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.touch()
    sim = _FakeSimulator(op_simulation_result)
    writer = _RecordingWriter()

    await sim_run(netlist=netlist, analysis=OpAnalysis(), simulator=sim)

    assert writer.calls == []
