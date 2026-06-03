"""
ApplyStagedSchematic — use case T026 Phase 2.

Применить pending `<active>.kicad_sch.staged` → `<active>.kicad_sch`
для всех staged-файлов внутри проекта. Pre-checks (per file):

- **Lock check.** Если KiCad GUI всё ещё держит active (lock-файл
  присутствует), skip без `force=True`. Stale-lock — норма (Phase 0
  finding KiCad 10 SIGTERM/SIGKILL leak), поэтому force нужен часто.
- **Parent-hash check.** Если `current_active_hash ≠ parent_hash` из
  sidecar (active изменён извне после staged write — реальный data
  loss risk), skip без `accept_overwrite=True`.

Apply per file = atomic `staged.replace(active)` + delete sidecar.
Без git activity (user коммитит сам). Multi-sheet — рекурсивный scan.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from application.get_project import ProjectNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.staged_schematics import (
        LockDetector,
        PendingStagedScanner,
    )


_SkipReason = Literal['lock', 'parent_hash_mismatch']


@dataclass(frozen=True)
class SkippedStagedEntry:
    """Staged-файл, который не применили + причина."""

    active_path: Path
    reason: _SkipReason
    current_hash: str | None = None
    expected_hash: str | None = None


@dataclass(frozen=True)
class ApplyStagedOutcome:
    """Результат apply-staged по всем pending файлам проекта."""

    project_root: Path
    applied: tuple[Path, ...]
    skipped: tuple[SkippedStagedEntry, ...]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def apply_staged_schematic(
    *,
    name: str,
    projects_root: Path,
    lock_detector: LockDetector,
    scanner: PendingStagedScanner,
    force: bool = False,
    accept_overwrite: bool = False,
) -> ApplyStagedOutcome:
    """Применить pending staged → active для всех файлов проекта `name`."""
    project_root = projects_root / name
    if not project_root.is_dir():
        raise ProjectNotFoundError(name)
    entries = scanner.scan(project_root)
    applied: list[Path] = []
    skipped: list[SkippedStagedEntry] = []
    for entry in entries:
        if lock_detector.is_held_by_kicad(entry.active_path) and not force:
            skipped.append(
                SkippedStagedEntry(
                    active_path=entry.active_path,
                    reason='lock',
                )
            )
            continue
        current_hash = (
            _sha256_hex(entry.active_path.read_bytes())
            if entry.active_path.exists()
            else None
        )
        if current_hash != entry.parent_hash and not accept_overwrite:
            skipped.append(
                SkippedStagedEntry(
                    active_path=entry.active_path,
                    reason='parent_hash_mismatch',
                    current_hash=current_hash,
                    expected_hash=entry.parent_hash,
                )
            )
            continue
        entry.staged_path.replace(entry.active_path)
        entry.meta_path.unlink(missing_ok=True)
        applied.append(entry.active_path)
    return ApplyStagedOutcome(
        project_root=project_root,
        applied=tuple(applied),
        skipped=tuple(skipped),
    )


__all__ = [
    'ApplyStagedOutcome',
    'SkippedStagedEntry',
    'apply_staged_schematic',
]
