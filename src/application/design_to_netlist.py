"""design_to_netlist — KiCad schematic → SPICE netlist (T008 Phase 4)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from application.get_project import get_project
from domain.simulation import Simulation, SimulationStatus

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter

_DEFAULT_SIM_SUBDIR = 'sim'


def _resolve_schematic_path(project_path: Path, schematic: Path) -> Path:
    if schematic.is_absolute():
        return schematic
    return project_path / schematic


def _default_netlist_path(project_path: Path, schematic_resolved: Path) -> Path:
    return project_path / _DEFAULT_SIM_SUBDIR / f'{schematic_resolved.stem}.cir'


async def design_to_netlist(
    *,
    project_name: str,
    schematic: Path,
    netlist_output: Path | None = None,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    exporter: SchematicExporter,
) -> Simulation:
    """Только экспорт SPICE netlist из KiCad schematic — без симуляции."""
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

    await asyncio.to_thread(
        lambda: output.parent.mkdir(parents=True, exist_ok=True),
    )

    netlist_path = await exporter.export_spice_netlist(
        schematic_resolved,
        output,
    )

    return Simulation(
        project_id=project.id,
        schematic_path=schematic_resolved,
        netlist_path=netlist_path,
        status=SimulationStatus.NETLIST_READY,
    )


__all__ = ['design_to_netlist']
