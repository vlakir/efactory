"""Simulator — outbound port для ngspice-based симуляции (T008)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, SimulationResult


class SimulatorUnavailableError(Exception):
    """Симулятор не доступен (бинарь не найден, версия не та, и т.п.)."""


class SimulationFailedError(Exception):
    """Симуляция стартовала, но fail'нула (convergence, syntax, timeout)."""


class Simulator(Protocol):
    """SPICE-симуляция netlist'а через outbound port."""

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        """
        Запустить указанный analysis на netlist'е и вернуть результат.

        Бросает `SimulatorUnavailableError`, если симулятор не доступен
        в окружении, `SimulationFailedError` — при ошибке runtime
        (convergence, syntax, timeout).
        """
        ...
