"""
run_export_sim_report — оркестрация `/export-sim-report` (T035 Phase 3.2).

Pipeline:

1. `get_project` — validate project from `sim_results.project` slug.
2. Resolve out-dir `<project.path>/out/publications/<ts>/` (collision-safe
   per W-4); `<ts>` берётся из `sim_results.publication_timestamp`.
3. `writer.write(sim_results, out_dir=<ts_root>/sim-report/, lang=lang)`
   → `SimReportArtifacts`.
4. Сборка `PublicationBundle` (sim-report only).
5. `readme_writer.write(bundle, out_dir=<ts_root>)`.
6. Return `(bundle, ts_root)`.

**Scope discipline:** этот use case НЕ обнаруживает / не загружает
существующих результатов симуляции и НЕ запускает свежую через
`--rerun`. Caller (Phase 4 CLI) сам решает (rerun → `design_to_sim`;
no-rerun → reader; см. T190 BACKLOG для persistence raw waveforms),
собирает `SimulationResultsBundle` и передаёт сюда. Это позволяет
use case оставаться чистым orchestrator'ом без зависимости от
SPICE-стека / FS reader'а.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application._publication_paths import (
    PUBLICATIONS_SUBDIR,
    SIM_REPORT_SUBDIR,
    resolve_ts_root,
)
from application.get_project import get_project
from domain.publication import (
    PublicationBundle,
    publication_timestamp_dirname,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.publication import (
        PublicationLang,
        SimulationResultsBundle,
    )
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.publication_readme_writer import (
        PublicationReadmeWriter,
    )
    from ports.outbound.sim_report_writer import SimReportWriter


async def run_export_sim_report(
    *,
    sim_results: SimulationResultsBundle,
    lang: PublicationLang,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
    writer: SimReportWriter,
    readme_writer: PublicationReadmeWriter,
) -> tuple[PublicationBundle, Path]:
    """
    Compose publication-grade sim-report + README в `<ts>` каталоге.

    `sim_results` приходит pre-built от caller'а: `project` slug,
    `efactory_version`, `publication_timestamp` (UTC), и optional
    данные анализа (tran/ac/sweep/magnetics/measurements).

    Returns `(bundle, ts_root)` — `bundle` для downstream tooling,
    `ts_root` — абсолютный путь для каскадного echo CLI.
    """
    project = await get_project(
        name=sim_results.project,
        projects_root=projects_root,
        manifest_repo=manifest_repo,
    )

    ts_dirname = publication_timestamp_dirname(sim_results.publication_timestamp)
    publications_root = project.path / PUBLICATIONS_SUBDIR
    publications_root.mkdir(parents=True, exist_ok=True)
    ts_root = resolve_ts_root(publications_root, ts_dirname)
    ts_root.mkdir(parents=True, exist_ok=True)

    sim_report_out_dir = ts_root / SIM_REPORT_SUBDIR
    sim_report_out_dir.mkdir(parents=True, exist_ok=True)

    sim_artifacts = await writer.write(
        sim_results,
        out_dir=sim_report_out_dir,
        lang=lang,
    )

    bundle = PublicationBundle(
        project=sim_results.project,
        timestamp=sim_results.publication_timestamp,
        efactory_version=sim_results.efactory_version,
        lang=lang,
        schematic=None,
        sim_report=sim_artifacts,
    )

    await readme_writer.write(bundle, out_dir=ts_root)

    return bundle, ts_root


__all__ = ['run_export_sim_report']
