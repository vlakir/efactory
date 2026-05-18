"""design_to_sim — композиция `design_to_netlist` + `sim_run` (T008 Phase 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.design_to_netlist import design_to_netlist
from application.sim_run import sim_run
from domain.simulation import Simulation, SimulationStatus
from ports.outbound.simulator import SimulatorUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator


async def design_to_sim(
    *,
    project_name: str,
    schematic: Path,
    analysis: AnalysisSpec,
    netlist_output: Path | None = None,
    timeout_seconds: float = 60.0,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    exporter: SchematicExporter,
    simulator: Simulator,
) -> Simulation:
    """KiCad schematic → SPICE netlist → run analysis. Возвращает агрегат."""
    sim = await design_to_netlist(
        project_name=project_name,
        schematic=schematic,
        netlist_output=netlist_output,
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
    )
    netlist_path = sim.netlist_path
    if netlist_path is None:
        msg = 'design_to_netlist did not produce netlist_path.'
        raise RuntimeError(msg)

    try:
        result = await sim_run(
            netlist=netlist_path,
            analysis=analysis,
            simulator=simulator,
            timeout_seconds=timeout_seconds,
        )
    except SimulatorUnavailableError:
        # ngspice не установлен → status остаётся NETLIST_READY (netlist всё
        # равно полезен — пользователь может симулировать вручную).
        return sim

    return sim.model_copy(
        update={
            'status': SimulationStatus.SIMULATED,
            'result': result,
        },
    )


__all__ = ['design_to_sim']
