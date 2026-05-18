"""StubSimulator — placeholder; всегда бросает SimulatorUnavailableError (T008 Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.stub_simulator.simulator import StubSimulator
from domain.simulation import (
    AcAnalysis,
    OpAnalysis,
    TranAnalysis,
)
from ports.outbound.simulator import SimulatorUnavailableError


async def test_run_op_raises_unavailable() -> None:
    simulator = StubSimulator()

    with pytest.raises(SimulatorUnavailableError, match='Phase 3'):
        await simulator.run(Path('/tmp/dummy.cir'), OpAnalysis())


async def test_run_tran_raises_unavailable() -> None:
    simulator = StubSimulator()
    analysis = TranAnalysis(t_step=1e-5, t_stop=1e-3)

    with pytest.raises(SimulatorUnavailableError, match='Phase 3'):
        await simulator.run(Path('/tmp/dummy.cir'), analysis)


async def test_run_ac_raises_unavailable() -> None:
    simulator = StubSimulator()
    analysis = AcAnalysis(n_points=10, f_start=1.0, f_stop=1e3)

    with pytest.raises(SimulatorUnavailableError, match='Phase 3'):
        await simulator.run(Path('/tmp/dummy.cir'), analysis)
