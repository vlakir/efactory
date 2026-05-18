"""sim_run use case — симуляция готового netlist (T008 Phase 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.sim_run import sim_run
from domain.simulation import (
    AcAnalysis,
    AnalysisSpec,
    OpAnalysis,
    SimulationResult,
    TranAnalysis,
)
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)


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


async def test_sim_run_op_forwards_analysis_to_simulator() -> None:
    simulator = FakeSimulator(
        result=SimulationResult(operating_points={'v(out)': 3.3}),
    )

    result = await sim_run(
        netlist=Path('/tmp/rc.cir'),
        analysis=OpAnalysis(),
        simulator=simulator,
    )

    assert result.operating_points == {'v(out)': 3.3}
    assert simulator.calls == [(Path('/tmp/rc.cir'), OpAnalysis(), 60.0)]


async def test_sim_run_passes_custom_timeout() -> None:
    simulator = FakeSimulator(
        result=SimulationResult(operating_points={'v(out)': 1.0}),
    )

    await sim_run(
        netlist=Path('/tmp/x.cir'),
        analysis=OpAnalysis(),
        simulator=simulator,
        timeout_seconds=5.0,
    )

    assert simulator.calls[0][2] == 5.0


async def test_sim_run_tran_forwards_full_spec() -> None:
    analysis = TranAnalysis(t_step=1e-5, t_stop=20e-3, t_start=1e-3, uic=True)
    ts_result = SimulationResult(
        operating_points={'placeholder': 0.0},  # dummy — invariant требует одну ветвь
    )
    simulator = FakeSimulator(result=ts_result)

    await sim_run(
        netlist=Path('/tmp/x.cir'),
        analysis=analysis,
        simulator=simulator,
    )

    assert simulator.calls[0][1] is analysis


async def test_sim_run_ac_forwards_full_spec() -> None:
    analysis = AcAnalysis(
        sweep='dec', n_points=20, f_start=1.0, f_stop=1e6,
    )
    simulator = FakeSimulator(
        result=SimulationResult(operating_points={'placeholder': 0.0}),
    )

    await sim_run(
        netlist=Path('/tmp/x.cir'),
        analysis=analysis,
        simulator=simulator,
    )

    assert simulator.calls[0][1] is analysis


async def test_sim_run_propagates_unavailable() -> None:
    simulator = FakeSimulator(raises=SimulatorUnavailableError('no ngspice'))

    with pytest.raises(SimulatorUnavailableError):
        await sim_run(
            netlist=Path('/tmp/x.cir'),
            analysis=OpAnalysis(),
            simulator=simulator,
        )


async def test_sim_run_propagates_failed() -> None:
    simulator = FakeSimulator(raises=SimulationFailedError('no conv'))

    with pytest.raises(SimulationFailedError):
        await sim_run(
            netlist=Path('/tmp/x.cir'),
            analysis=OpAnalysis(),
            simulator=simulator,
        )
