"""Tests `sim_run` + RawWaveformRepository persistence hook (T190)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.sim_run import sim_run
from domain.raw_waveform import RawWaveform, WaveformAnalysisType
from domain.simulation import (
    AcAnalysis,
    AcSweep,
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

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        return self._result


class _RecordingWaveformWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[RawWaveform, Path]] = []

    async def write(self, *, waveform: RawWaveform, project_root: Path) -> Path:
        self.calls.append((waveform, project_root))
        return project_root / '.efactory' / 'sim-results' / 'fake.waveform.json'

    async def load_latest(
        self,
        *,
        project_root: Path,
        analysis_type: WaveformAnalysisType,
    ) -> RawWaveform | None:
        return None


@pytest.fixture
def tran_result() -> SimulationResult:
    return SimulationResult(
        time_series=TimeSeries(
            time=(0.0, 1e-6, 2e-6),
            traces={'v(out)': (0.0, 0.5, 1.0)},
        ),
    )


@pytest.fixture
def ac_result() -> SimulationResult:
    return SimulationResult(
        ac_sweep=AcSweep(
            frequency=(10.0, 100.0, 1000.0),
            traces_real={'v(out)': (1.0, 0.9, 0.5)},
            traces_imag={'v(out)': (0.0, 0.1, 0.3)},
        ),
    )


@pytest.fixture
def op_result() -> SimulationResult:
    return SimulationResult(operating_points={'v(out)': 1.2})


@pytest.mark.asyncio
async def test_tran_writes_raw_waveform(
    tmp_path: Path, tran_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist = project_root / 'amp.cir'
    netlist.touch()
    writer = _RecordingWaveformWriter()

    await sim_run(
        netlist=netlist,
        analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
        simulator=_FakeSimulator(tran_result),
        raw_waveform_writer=writer,
        project_root=project_root,
    )

    assert len(writer.calls) == 1
    wf, root = writer.calls[0]
    assert root == project_root
    assert wf.analysis_type == WaveformAnalysisType.TRAN
    assert wf.x_axis_name == 'time'
    assert wf.x_axis == (0.0, 1e-6, 2e-6)
    assert wf.traces == {'v(out)': (0.0, 0.5, 1.0)}
    assert wf.traces_imag is None


@pytest.mark.asyncio
async def test_ac_writes_raw_waveform_with_imag(
    tmp_path: Path, ac_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist = project_root / 'amp.cir'
    netlist.touch()
    writer = _RecordingWaveformWriter()

    await sim_run(
        netlist=netlist,
        analysis=AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e6),
        simulator=_FakeSimulator(ac_result),
        raw_waveform_writer=writer,
        project_root=project_root,
    )

    wf, _ = writer.calls[0]
    assert wf.analysis_type == WaveformAnalysisType.AC
    assert wf.x_axis_name == 'frequency'
    assert wf.traces == {'v(out)': (1.0, 0.9, 0.5)}
    assert wf.traces_imag == {'v(out)': (0.0, 0.1, 0.3)}


@pytest.mark.asyncio
async def test_op_does_not_write_waveform(
    tmp_path: Path, op_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist = project_root / 'amp.cir'
    netlist.touch()
    writer = _RecordingWaveformWriter()

    await sim_run(
        netlist=netlist,
        analysis=OpAnalysis(),
        simulator=_FakeSimulator(op_result),
        raw_waveform_writer=writer,
        project_root=project_root,
    )

    assert writer.calls == []


@pytest.mark.asyncio
async def test_waveform_writer_no_op_when_omitted(
    tmp_path: Path, tran_result: SimulationResult
) -> None:
    """Без writer и без project_root — никаких persist-сайд-эффектов."""
    netlist = tmp_path / 'amp.cir'
    netlist.touch()

    result = await sim_run(
        netlist=netlist,
        analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
        simulator=_FakeSimulator(tran_result),
    )
    assert result is tran_result


@pytest.mark.asyncio
async def test_waveform_writer_without_project_root_silent(
    tmp_path: Path, tran_result: SimulationResult
) -> None:
    """raw_waveform_writer без project_root — writer не вызывается (silent skip)."""
    netlist = tmp_path / 'amp.cir'
    netlist.touch()
    writer = _RecordingWaveformWriter()

    await sim_run(
        netlist=netlist,
        analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
        simulator=_FakeSimulator(tran_result),
        raw_waveform_writer=writer,
    )
    assert writer.calls == []


@pytest.mark.asyncio
async def test_waveform_source_netlist_falls_back_outside_project_root(
    tmp_path: Path, tran_result: SimulationResult
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    netlist_outside = tmp_path / 'shared' / 'amp.cir'
    netlist_outside.parent.mkdir()
    netlist_outside.touch()
    writer = _RecordingWaveformWriter()

    await sim_run(
        netlist=netlist_outside,
        analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
        simulator=_FakeSimulator(tran_result),
        raw_waveform_writer=writer,
        project_root=project_root,
    )

    wf, _ = writer.calls[0]
    assert wf.source_netlist == 'amp.cir'
