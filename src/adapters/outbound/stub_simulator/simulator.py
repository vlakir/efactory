"""
StubSimulator — placeholder для Simulator port (T004 split-scope).

T008 заменит реальной реализацией через PySpice / ngspice. Сейчас
любой вызов бросает `SimulatorUnavailableError` с явной пометкой
«ngspice integration scheduled for T008».
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ports.outbound.simulator import SimulatorUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import SimulationResult


_NOT_AVAILABLE_MSG = (
    'Simulator not available in current build (T004 split-scope). '
    'ngspice integration scheduled for T008.'
)


class StubSimulator:
    async def run_op(self, netlist: Path) -> SimulationResult:  # noqa: ARG002
        raise SimulatorUnavailableError(_NOT_AVAILABLE_MSG)


__all__ = ['StubSimulator']
