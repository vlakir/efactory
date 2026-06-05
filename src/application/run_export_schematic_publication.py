"""
run_export_schematic_publication — оркестрация slash-команды (T035 Phase 3).

Pipeline:

1. `get_project` — resolve slug → `Project` (raises `ProjectNotFoundError` /
   `ProjectManifestMissingError`).
2. Resolve schematic path (relative → `<project.path>/<schematic>`).
3. Compute publication ts (UTC `now()` injectable). Resolve out-dir
   `<project.path>/out/publications/<ts>/` с collision-safe суффиксом
   (`-1`, `-2`, ..., spec W-4) если каталог уже существует и не пуст.
4. `renderer.render(...)` → `SchematicPublicationArtifacts`.
5. Сборка `PublicationBundle` (schematic only).
6. `readme_writer.write(bundle, out_dir=ts_root)`.
7. Return `(bundle, ts_root)` — Phase 4 CLI печатает каскадный echo
   `publication-export: <ts_root>` (FR §3).

Use case — pure orchestrator: no IO кроме ports (renderer, writer, manifest_repo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application._publication_paths import (
    PUBLICATIONS_SUBDIR,
    SCHEMATIC_SUBDIR,
    default_now,
    resolve_schematic_path,
    resolve_ts_root,
)
from application.get_project import get_project
from domain.publication import (
    PublicationBundle,
    publication_timestamp_dirname,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from domain.publication import (
        MultiSheetMode,
        PublicationLang,
    )
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.publication_readme_writer import (
        PublicationReadmeWriter,
    )
    from ports.outbound.schematic_publication_renderer import (
        SchematicPublicationRenderer,
    )


async def run_export_schematic_publication(
    *,
    project_name: str,
    schematic: Path,
    multi_sheet_mode: MultiSheetMode,
    lang: PublicationLang,
    efactory_version: str,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
    renderer: SchematicPublicationRenderer,
    readme_writer: PublicationReadmeWriter,
    now: Callable[[], datetime] = default_now,
) -> tuple[PublicationBundle, Path]:
    """
    Compose publication-grade schematic artefacts + README в `<ts>` каталоге.

    Returns `(bundle, ts_root)` — `bundle` для downstream tooling,
    `ts_root` — абсолютный путь, который CLI печатает в каскадный echo.
    """
    project = await get_project(
        name=project_name,
        projects_root=projects_root,
        manifest_repo=manifest_repo,
    )
    schematic_resolved = resolve_schematic_path(project.path, schematic)

    timestamp = now()
    ts_dirname = publication_timestamp_dirname(timestamp)
    publications_root = project.path / PUBLICATIONS_SUBDIR
    publications_root.mkdir(parents=True, exist_ok=True)
    ts_root = resolve_ts_root(publications_root, ts_dirname)
    ts_root.mkdir(parents=True, exist_ok=True)

    schematic_out_dir = ts_root / SCHEMATIC_SUBDIR
    schematic_out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = await renderer.render(
        schematic_resolved,
        schematic_out_dir,
        multi_sheet_mode=multi_sheet_mode,
    )

    bundle = PublicationBundle(
        project=project_name,
        timestamp=timestamp,
        efactory_version=efactory_version,
        lang=lang,
        schematic=artifacts,
        sim_report=None,
    )

    await readme_writer.write(bundle, out_dir=ts_root)

    return bundle, ts_root


__all__ = ['run_export_schematic_publication']
