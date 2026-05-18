"""
StubSimulator — placeholder для Simulator port (T008 Phase 2).

В Phase 3 будет заменён реальным `NgspiceSimulator`; пока любой вызов
бросает `SimulatorUnavailableError` с явной пометкой про Phase 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ports.outbound.simulator import SimulatorUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, SimulationResult


_NOT_AVAILABLE_MSG = (
    'Simulator not available in current build. '
    'T008 Phase 3: ngspice adapter not implemented yet.'
)


class StubSimulator:
    async def run(
        self,
        netlist: Path,  # noqa: ARG002
        analysis: AnalysisSpec,  # noqa: ARG002
        *,
        timeout_seconds: float = 60.0,  # noqa: ARG002
    ) -> SimulationResult:
        raise SimulatorUnavailableError(_NOT_AVAILABLE_MSG)


__all__ = ['StubSimulator']
