"""
compose_sim_results_bundle — T191 use case: --rerun / persistent load.

Orchestrate сборку `SimulationResultsBundle` для `/export-sim-report`:

- `rerun=True` → запустить design_to_sim per analysis (TRAN/AC),
  persist через T190 sim_results+raw_waveform writers (если поданы),
  собрать bundle из in-memory результатов.
- `rerun=False` → загрузить latest TRAN/AC waveforms через
  `RawWaveformRepository.load_latest`. Каждый optional — missing
  signals в bundle отсутствуют (writer выдаст metadata-only секции).

Trace signals: если `tran_signals` / `ac_signals` пусты — берём все
ключи из соответствующих traces; иначе используем указанные.

Cleanly hexagonal: caller (CLI) парсит аргументы и инжектит зависимости;
use case не знает о Typer, схемах CLI-флагов и форматах SPICE-чисел.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.design_to_sim import design_to_sim
from application.get_project import get_project
from domain.publication import SimulationResultsBundle
from domain.raw_waveform import (
    WaveformAnalysisType,
    waveform_to_ac_sweep,
    waveform_to_time_series,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AcAnalysis, TranAnalysis
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.raw_waveforms import RawWaveformRepository
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


async def compose_sim_results_bundle(
    *,
    project_name: str,
    efactory_version: str,
    rerun: bool,
    schematic: Path | None,
    tran_analysis: TranAnalysis | None,
    ac_analysis: AcAnalysis | None,
    tran_signals: tuple[str, ...],
    ac_signals: tuple[str, ...],
    sim_timeout_seconds: float,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
    exporter: SchematicExporter,
    simulator: Simulator,
    raw_waveform_repo: RawWaveformRepository,
    sim_results_writer: SimResultsRepository | None = None,
) -> SimulationResultsBundle:
    """
    T191: build `SimulationResultsBundle` for `/export-sim-report`.

    Raises `ValueError` if `rerun=True` без `schematic`.
    """
    publication_ts = datetime.now(UTC)
    tran_ts = None
    ac_data = None

    if rerun:
        if schematic is None:
            msg = 'compose_sim_results_bundle: rerun=True требует schematic.'
            raise ValueError(msg)
        if tran_analysis is not None:
            sim = await design_to_sim(
                project_name=project_name,
                schematic=schematic,
                analysis=tran_analysis,
                timeout_seconds=sim_timeout_seconds,
                projects_root=projects_root,
                manifest_repo=manifest_repo,
                exporter=exporter,
                simulator=simulator,
                sim_results_writer=sim_results_writer,
                raw_waveform_writer=raw_waveform_repo,
            )
            if sim.result is not None and sim.result.time_series is not None:
                tran_ts = sim.result.time_series
        if ac_analysis is not None:
            sim = await design_to_sim(
                project_name=project_name,
                schematic=schematic,
                analysis=ac_analysis,
                timeout_seconds=sim_timeout_seconds,
                projects_root=projects_root,
                manifest_repo=manifest_repo,
                exporter=exporter,
                simulator=simulator,
                sim_results_writer=sim_results_writer,
                raw_waveform_writer=raw_waveform_repo,
            )
            if sim.result is not None and sim.result.ac_sweep is not None:
                ac_data = sim.result.ac_sweep
    else:
        project_obj = await get_project(
            name=project_name,
            projects_root=projects_root,
            manifest_repo=manifest_repo,
        )
        tran_wf = await raw_waveform_repo.load_latest(
            project_root=project_obj.path,
            analysis_type=WaveformAnalysisType.TRAN,
        )
        ac_wf = await raw_waveform_repo.load_latest(
            project_root=project_obj.path,
            analysis_type=WaveformAnalysisType.AC,
        )
        if tran_wf is not None:
            tran_ts = waveform_to_time_series(tran_wf)
        if ac_wf is not None:
            ac_data = waveform_to_ac_sweep(ac_wf)

    if tran_ts is not None:
        tran_signals_resolved = tran_signals or tuple(tran_ts.traces.keys())
    else:
        tran_signals_resolved = ()
    if ac_data is not None:
        ac_signals_resolved = ac_signals or tuple(ac_data.traces_real.keys())
    else:
        ac_signals_resolved = ()

    return SimulationResultsBundle(
        project=project_name,
        efactory_version=efactory_version,
        publication_timestamp=publication_ts,
        source_simulation_timestamp=None if rerun else publication_ts,
        tran=tran_ts,
        tran_signals=tran_signals_resolved,
        ac_sweep=ac_data,
        ac_signals=ac_signals_resolved,
    )


__all__ = ['compose_sim_results_bundle']
