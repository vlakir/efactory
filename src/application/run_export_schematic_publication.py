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

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.get_project import get_project
from domain.publication import (
    PublicationBundle,
    publication_timestamp_dirname,
)

if TYPE_CHECKING:
    from collections.abc import Callable
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


_PUBLICATIONS_SUBDIR = 'out/publications'
_SCHEMATIC_SUBDIR = 'schematic'


def _default_now() -> datetime:
    return datetime.now(UTC)


def _resolve_schematic_path(project_path: Path, schematic: Path) -> Path:
    if schematic.is_absolute():
        return schematic
    return project_path / schematic


def _resolve_ts_root(publications_root: Path, ts_dirname: str) -> Path:
    """
    Resolve collision-safe `<publications_root>/<ts_dirname>[-N]/` (W-4).

    Если каталог не существует — возвращаем как есть. Если существует
    и пуст — переиспользуем. Если существует и содержит файлы — пробуем
    суффикс `-1`, `-2`, ..., до первого свободного имени.
    """
    candidate = publications_root / ts_dirname
    if not candidate.exists():
        return candidate
    if candidate.is_dir() and not any(candidate.iterdir()):
        return candidate
    suffix = 1
    while True:
        with_suffix = publications_root / f'{ts_dirname}-{suffix}'
        if not with_suffix.exists():
            return with_suffix
        if with_suffix.is_dir() and not any(with_suffix.iterdir()):
            return with_suffix
        suffix += 1


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
    now: Callable[[], datetime] = _default_now,
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
    schematic_resolved = _resolve_schematic_path(project.path, schematic)

    timestamp = now()
    ts_dirname = publication_timestamp_dirname(timestamp)
    publications_root = project.path / _PUBLICATIONS_SUBDIR
    publications_root.mkdir(parents=True, exist_ok=True)
    ts_root = _resolve_ts_root(publications_root, ts_dirname)
    ts_root.mkdir(parents=True, exist_ok=True)

    schematic_out_dir = ts_root / _SCHEMATIC_SUBDIR
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
