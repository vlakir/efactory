"""Unit-тесты `scan_pending_staged` (T026 Phase 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.outbound.schematic_kicad.scanner import scan_pending_staged
from adapters.outbound.schematic_kicad.staged_metadata import (
    StagedMetadata,
    write_staged_metadata,
)
from adapters.outbound.schematic_kicad.staged_paths import meta_path, staged_path

if TYPE_CHECKING:
    from pathlib import Path


def _write_staged_pair(active: Path, parent_hash: str | None = None) -> None:
    active.parent.mkdir(parents=True, exist_ok=True)
    sp = staged_path(active)
    sp.write_text('(staged ...)', encoding='utf-8')
    meta = StagedMetadata(
        parent_hash=parent_hash,
        staged_at='2026-06-03T01:00:00Z',
        staged_by='efactory-test',
        trigger='/sim-run',
    )
    write_staged_metadata(meta_path(sp), meta)


def test_no_staged_returns_empty(tmp_path: Path) -> None:
    assert scan_pending_staged(tmp_path) == []


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert scan_pending_staged(tmp_path / 'missing') == []


def test_single_staged_pair_returned(tmp_path: Path) -> None:
    active = tmp_path / 'a.kicad_sch'
    _write_staged_pair(active, parent_hash='a' * 64)
    entries = scan_pending_staged(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e.active_path == active
    assert e.staged_path == staged_path(active)
    assert e.parent_hash == 'a' * 64


def test_orphan_staged_without_meta_keeps_parent_hash_none(tmp_path: Path) -> None:
    active = tmp_path / 'b.kicad_sch'
    staged_path(active).write_text('(staged ...)', encoding='utf-8')
    # meta.json deliberately absent
    entries = scan_pending_staged(tmp_path)
    assert len(entries) == 1
    assert entries[0].parent_hash is None


def test_multi_sheet_recursive_scan(tmp_path: Path) -> None:
    root_active = tmp_path / 'root.kicad_sch'
    sub_active = tmp_path / 'subsheets' / 'amp.kicad_sch'
    _write_staged_pair(root_active, parent_hash='1' * 64)
    _write_staged_pair(sub_active, parent_hash='2' * 64)
    entries = scan_pending_staged(tmp_path)
    paths = sorted(e.active_path for e in entries)
    assert paths == sorted([root_active, sub_active])


def test_active_without_staged_ignored(tmp_path: Path) -> None:
    """Файл без staged-двойника не входит в результат."""
    (tmp_path / 'a.kicad_sch').write_text('(active)', encoding='utf-8')
    assert scan_pending_staged(tmp_path) == []
