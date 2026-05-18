"""Simulator — outbound port для ngspice-based симуляции (T004 stub → T008 real)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import SimulationResult


class SimulatorUnavailableError(Exception):
    """
    Симулятор не доступен (T004 stub) или не реализован.

    StubSimulator всегда бросает эту ошибку — реальный симулятор
    подключим в T008 (PySpice + ngspice).
    """


class SimulationFailedError(Exception):
    """Симуляция стартовала, но fail'нула (convergence, syntax, ...)."""


class Simulator(Protocol):
    """SPICE-симуляция netlist'а. T008 заполнит реальной реализацией."""

    async def run_op(self, netlist: Path) -> SimulationResult:
        """
        Operating point analysis (`.OP`).

        Возвращает `SimulationResult` с node voltages / branch currents.
        Бросает `SimulatorUnavailableError` если симулятор не готов
        (T004 stub) или `SimulationFailedError` при ошибке runtime.
        """
        ...
