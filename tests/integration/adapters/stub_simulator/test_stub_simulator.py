"""StubSimulator — placeholder; всегда бросает SimulatorUnavailableError (T004)."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.stub_simulator.simulator import StubSimulator
from ports.outbound.simulator import SimulatorUnavailableError


async def test_run_op_raises_unavailable() -> None:
    simulator = StubSimulator()

    with pytest.raises(SimulatorUnavailableError, match='T008'):
        await simulator.run_op(Path('/tmp/dummy.cir'))
