"""sim_run — запуск симуляции на готовом netlist'е (T008 Phase 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, SimulationResult
    from ports.outbound.simulator import Simulator


async def sim_run(
    *,
    netlist: Path,
    analysis: AnalysisSpec,
    simulator: Simulator,
    timeout_seconds: float = 60.0,
) -> SimulationResult:
    """
    Запустить указанный analysis на готовом netlist'е.

    Тонкая обёртка над `Simulator.run`. Бросает `SimulatorUnavailableError`
    / `SimulationFailedError` неизменно.
    """
    return await simulator.run(
        netlist,
        analysis,
        timeout_seconds=timeout_seconds,
    )


__all__ = ['sim_run']
