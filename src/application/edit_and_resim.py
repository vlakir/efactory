"""edit_and_resim — композиция edit_component_value + design_to_sim (T004b)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.design_to_sim import design_to_sim
from application.edit_component_value import edit_component_value

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec, Simulation
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator


async def edit_and_resim(
    *,
    project_name: str,
    schematic: Path,
    edits: dict[str, str],
    analysis: AnalysisSpec,
    netlist_output: Path | None = None,
    timeout_seconds: float = 60.0,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    exporter: SchematicExporter,
    simulator: Simulator,
) -> Simulation:
    """
    Применить value-edit'ы к .kicad_sch, затем design_to_sim.

    `edits` — `{reference: new_value}` mapping (например, `{'R1': '10k'}`).
    Каждый edit применяется in-place к schematic file. После — pipeline
    design → netlist → simulation, возвращается aggregate `Simulation`.

    Атомарность: каждый edit — atomic write; design_to_sim — отдельная
    транзакция. Failure в середине edits оставляет schematic в
    частично-изменённом состоянии (T004b accepted limitation; T021 в
    Phase 2 backlog добавит snapshot/rollback).
    """
    for ref, value in edits.items():
        edit_component_value(schematic, ref, value)
    return await design_to_sim(
        project_name=project_name,
        schematic=schematic,
        analysis=analysis,
        netlist_output=netlist_output,
        timeout_seconds=timeout_seconds,
        repo=repo,
        manifest_repo=manifest_repo,
        exporter=exporter,
        simulator=simulator,
    )


__all__ = ['edit_and_resim']
