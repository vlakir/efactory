"""design_to_sim — композиция `design_to_netlist` + `sim_run` (T008 Phase 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.design_to_netlist import design_to_netlist
from application.get_project import get_project
from application.run_erc_check import run_erc_check
from application.sim_run import sim_run
from domain.simulation import Simulation, SimulationStatus
from ports.outbound.simulator import SimulatorUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec
    from ports.outbound.erc import ErcReportWriter, ErcRunner
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.raw_waveforms import RawWaveformRepository
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


def _resolve_schematic(project_path: Path, schematic: Path) -> Path:
    if schematic.is_absolute():
        return schematic
    return project_path / schematic


async def design_to_sim(
    *,
    project_name: str,
    schematic: Path,
    analysis: AnalysisSpec,
    netlist_output: Path | None = None,
    timeout_seconds: float = 60.0,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
    exporter: SchematicExporter,
    simulator: Simulator,
    erc_runner: ErcRunner | None = None,
    erc_report_writer: ErcReportWriter | None = None,
    erc_timeout_seconds: float = 30.0,
    sim_results_writer: SimResultsRepository | None = None,
    raw_waveform_writer: RawWaveformRepository | None = None,
) -> Simulation:
    """
    KiCad schematic → SPICE netlist → run analysis. Возвращает агрегат.

    Если `erc_runner` задан — перед `design_to_netlist` гоняем ERC по
    реальному (resolved) `.kicad_sch` пользователя (spec T029 R8). ERC
    errors блокируют дальнейший pipeline через `ErcErrorsFoundError`.
    Warnings пропускаются (но рендерятся в отчёт, если задан
    `erc_report_writer`). Если `erc_runner=None` — gate выключен (этот
    режим — для тестов; production composition wires the real runner).
    """
    if erc_runner is not None:
        project = await get_project(
            name=project_name,
            projects_root=projects_root,
            manifest_repo=manifest_repo,
        )
        schematic_resolved = _resolve_schematic(project.path, schematic)
        await run_erc_check(
            schematic=schematic_resolved,
            project_root=project.path,
            erc_runner=erc_runner,
            report_writer=erc_report_writer,
            timeout_seconds=erc_timeout_seconds,
        )

    sim = await design_to_netlist(
        project_name=project_name,
        schematic=schematic,
        netlist_output=netlist_output,
        projects_root=projects_root,
        manifest_repo=manifest_repo,
        exporter=exporter,
    )
    netlist_path = sim.netlist_path
    if netlist_path is None:
        msg = 'design_to_netlist did not produce netlist_path.'
        raise RuntimeError(msg)

    project_root_for_persistence: Path | None = None
    if sim_results_writer is not None or raw_waveform_writer is not None:
        project_root_for_persistence = projects_root / project_name

    try:
        result = await sim_run(
            netlist=netlist_path,
            analysis=analysis,
            simulator=simulator,
            timeout_seconds=timeout_seconds,
            sim_results_writer=sim_results_writer,
            raw_waveform_writer=raw_waveform_writer,
            project_root=project_root_for_persistence,
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
