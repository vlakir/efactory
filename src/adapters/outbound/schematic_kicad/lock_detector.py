"""
KiCad GUI lock-file detector для T026 staged-модификаций.

Pattern KiCad 10 (verified Phase 0 2026-06-03, KiCad 10.0.3):
  `<dir>/~<filename>.lck` рядом с открытым `.kicad_sch`.

Detector проверяет существование lock-файла (content не парсится в MVP).

Cleanup поведение KiCad 10 (Phase 0 finding):
  - SIGTERM / SIGKILL → lock НЕ удаляется. Stale-lock после crash — норма.
  - Graceful File→Close → lock удаляется.
Поэтому detector reports `True` при наличии lock даже если KiCad убит;
user override через apply-staged `--force` flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.outbound.schematic_kicad.staged_paths import lock_path

if TYPE_CHECKING:
    from pathlib import Path


class KicadLockDetector:
    """Detect KiCad GUI lock-файла рядом с `.kicad_sch` / `.kicad_pro`."""

    def is_held_by_kicad(self, active: Path) -> bool:
        return lock_path(active).exists()


__all__ = ['KicadLockDetector']
