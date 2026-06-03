"""Unit-тесты staged-path helpers для T026."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.schematic_kicad.staged_paths import (
    lock_path,
    meta_path,
    staged_path,
)


def test_staged_path_appends_staged_suffix() -> None:
    original = Path('/x/y/se_amp.kicad_sch')
    assert staged_path(original) == Path('/x/y/se_amp.kicad_sch.staged')


def test_meta_path_appends_meta_json_suffix() -> None:
    staged = Path('/x/y/se_amp.kicad_sch.staged')
    assert meta_path(staged) == Path('/x/y/se_amp.kicad_sch.staged.meta.json')


def test_lock_path_uses_kicad10_pattern() -> None:
    """KiCad 10 lock pattern verified Phase 0 2026-06-03: `<dir>/~<name>.lck`."""
    original = Path('/projects/demo/se_amp.kicad_sch')
    assert lock_path(original) == Path('/projects/demo/~se_amp.kicad_sch.lck')


def test_lock_path_handles_kicad_pro() -> None:
    original = Path('/projects/demo/se_amp.kicad_pro')
    assert lock_path(original) == Path('/projects/demo/~se_amp.kicad_pro.lck')
