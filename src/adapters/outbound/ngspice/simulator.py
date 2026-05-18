"""NgspiceSimulator — реальный SPICE-симулятор через subprocess (T008 Phase 3)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from adapters.outbound.ngspice.raw_parser import (
    NgspiceRawParseError,
    parse_ngspice_raw,
)
from adapters.outbound.ngspice.wrapper import build_wrapper
from domain.application import ApplicationKind
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
)
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, SimulationResult
    from ports.outbound.app_manager import AppManager


class NgspiceSimulator:
    def __init__(self, app_manager: AppManager) -> None:
        self._app_manager = app_manager

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        wrapper_path = netlist.parent / f'{netlist.stem}.wrapper.cir'
        raw_path = netlist.parent / f'{netlist.stem}.raw'

        netlist_content = await asyncio.to_thread(netlist.read_text)
        wrapper_text = build_wrapper(netlist_content, analysis, raw_path)
        await asyncio.to_thread(wrapper_path.write_text, wrapper_text)

        try:
            result = await self._app_manager.run(
                ApplicationKind.NGSPICE,
                ['-b', str(wrapper_path)],
                timeout_seconds=timeout_seconds,
            )
        except ApplicationNotInstalledError as exc:
            msg = (
                f'ngspice not available: {exc}. Install via '
                f'`apt install ngspice` / `brew install ngspice`.'
            )
            raise SimulatorUnavailableError(msg) from exc
        except ApplicationStartError as exc:
            msg = f'ngspice failed to start: {exc}'
            raise SimulationFailedError(msg) from exc

        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            msg = f'ngspice exit {result.returncode} on {netlist}: {details}'
            raise SimulationFailedError(msg)

        raw_exists = await asyncio.to_thread(raw_path.is_file)
        if not raw_exists:
            details = result.stderr.strip() or result.stdout.strip()
            msg = f'ngspice exit 0 but raw file {raw_path} not produced: {details}'
            raise SimulationFailedError(msg)

        raw_text = await asyncio.to_thread(raw_path.read_text)
        try:
            return parse_ngspice_raw(raw_text)
        except NgspiceRawParseError as exc:
            msg = f'ngspice raw parse failed: {exc}'
            raise SimulationFailedError(msg) from exc


__all__ = ['NgspiceSimulator']
