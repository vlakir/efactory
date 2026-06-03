"""
Pending-staged scanner для T026 apply-staged use case.

Рекурсивно обходит project root и собирает entries `<active>.kicad_sch +
<active>.kicad_sch.staged + <active>.kicad_sch.staged.meta.json` (sidecar).
Если sidecar отсутствует (crash между tmp.replace staged и meta write) —
entry включается с `parent_hash=None`, apply use case это разрешает только
с `--accept-overwrite` (unknown active state).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.outbound.schematic_kicad.staged_metadata import read_staged_metadata
from adapters.outbound.schematic_kicad.staged_paths import meta_path
from ports.outbound.staged_schematics import PendingStagedEntry

if TYPE_CHECKING:
    from pathlib import Path


_STAGED_GLOB = '*.kicad_sch.staged'
_STAGED_SUFFIX = '.staged'


def _strip_staged_suffix(staged: Path) -> Path:
    name = staged.name
    base = name.removesuffix(_STAGED_SUFFIX)
    return staged.with_name(base)


def scan_pending_staged(project_root: Path) -> list[PendingStagedEntry]:
    """Найти все pending `.kicad_sch.staged` в project_root рекурсивно."""
    if not project_root.is_dir():
        return []
    entries: list[PendingStagedEntry] = []
    for staged in sorted(project_root.rglob(_STAGED_GLOB)):
        if not staged.is_file():
            continue
        active = _strip_staged_suffix(staged)
        meta = meta_path(staged)
        parent_hash: str | None = None
        if meta.is_file():
            parent_hash = read_staged_metadata(meta).parent_hash
        entries.append(
            PendingStagedEntry(
                active_path=active,
                staged_path=staged,
                meta_path=meta,
                parent_hash=parent_hash,
            )
        )
    return entries


class KicadPendingStagedScanner:
    """Adapter-инкарнация `PendingStagedScanner` для KiCad staged-файлов."""

    def scan(self, project_root: Path) -> list[PendingStagedEntry]:
        return scan_pending_staged(project_root)


__all__ = ['KicadPendingStagedScanner', 'scan_pending_staged']
