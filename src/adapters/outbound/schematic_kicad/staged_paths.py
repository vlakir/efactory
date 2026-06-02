"""
Path helpers для T026 staged-модификаций.

KiCad 10 lock-pattern verified Phase 0 (2026-06-03 на KiCad 10.0.3):
  `<dir>/~<filename>.lck` рядом с открытым `.kicad_sch`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


_STAGED_SUFFIX = '.staged'
_META_SUFFIX = '.meta.json'
_LOCK_PREFIX = '~'
_LOCK_SUFFIX = '.lck'


def staged_path(active: Path) -> Path:
    """`<dir>/se_amp.kicad_sch` → `<dir>/se_amp.kicad_sch.staged`."""
    return active.with_name(active.name + _STAGED_SUFFIX)


def meta_path(staged: Path) -> Path:
    """`<dir>/se_amp.kicad_sch.staged` → `<dir>/se_amp.kicad_sch.staged.meta.json`."""
    return staged.with_name(staged.name + _META_SUFFIX)


def lock_path(active: Path) -> Path:
    """`<dir>/se_amp.kicad_sch` → `<dir>/~se_amp.kicad_sch.lck`."""
    return active.with_name(_LOCK_PREFIX + active.name + _LOCK_SUFFIX)


__all__ = ['lock_path', 'meta_path', 'staged_path']
