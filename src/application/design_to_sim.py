"""design_to_sim — KiCad → SPICE netlist (+ stub simulation) (T004 split-scope)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from application.get_project import get_project
from domain.simulation import Simulation, SimulationStatus
from ports.outbound.simulator import SimulatorUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator

_DEFAULT_SIM_SUBDIR = 'sim'


def _resolve_schematic_path(project_path: Path, schematic: Path) -> Path:
    """Если относительный — резолвим относительно project_path."""
    if schematic.is_absolute():
        return schematic
    return project_path / schematic


def _default_netlist_path(project_path: Path, schematic_resolved: Path) -> Path:
    return project_path / _DEFAULT_SIM_SUBDIR / f'{schematic_resolved.stem}.cir'


async def design_to_sim(
    *,
    project_name: str,
    schematic: Path,
    netlist_output: Path | None = None,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    exporter: SchematicExporter,
    simulator: Simulator,
) -> Simulation:
    """
    KiCad schematic → SPICE netlist (+ stub simulation в T004).

    T008 заменит stub-симулятор реальным; интерфейс не меняется.
    """
    project = await get_project(
        name=project_name,
        repo=repo,
        manifest_repo=manifest_repo,
    )

    schematic_resolved = _resolve_schematic_path(project.path, schematic)
    output = netlist_output or _default_netlist_path(
        project.path,
        schematic_resolved,
    )

    # mkdir sim/ — pipeline сам создаёт.
    await asyncio.to_thread(
        lambda: output.parent.mkdir(parents=True, exist_ok=True),
    )

    netlist_path = await exporter.export_spice_netlist(
        schematic_resolved,
        output,
    )

    sim = Simulation(
        project_id=project.id,
        schematic_path=schematic_resolved,
        netlist_path=netlist_path,
        status=SimulationStatus.NETLIST_READY,
    )

    try:
        result = await simulator.run_op(netlist_path)
    except SimulatorUnavailableError:
        # T004 split-scope: stub бросает; status остаётся NETLIST_READY.
        return sim

    return sim.model_copy(
        update={
            'status': SimulationStatus.SIMULATED,
            'result': result,
        },
    )


__all__ = ['design_to_sim']
