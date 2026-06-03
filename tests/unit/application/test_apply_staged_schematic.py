"""Unit-тесты `apply_staged_schematic` use case (T026 Phase 2)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.schematic_kicad.scanner import KicadPendingStagedScanner
from adapters.outbound.schematic_kicad.staged_metadata import (
    StagedMetadata,
    write_staged_metadata,
)
from adapters.outbound.schematic_kicad.staged_paths import (
    lock_path,
    meta_path,
    staged_path,
)
from application.apply_staged_schematic import apply_staged_schematic
from application.get_project import ProjectNotFoundError

if TYPE_CHECKING:
    pass


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _setup_pair(active: Path, active_content: bytes, staged_content: str) -> str:
    """Создаёт active + staged + meta.json в active.parent."""
    active.parent.mkdir(parents=True, exist_ok=True)
    if active_content:
        active.write_bytes(active_content)
    sp = staged_path(active)
    sp.write_text(staged_content, encoding='utf-8')
    parent_hash = _sha256_hex(active_content) if active_content else None
    meta = StagedMetadata(
        parent_hash=parent_hash,
        staged_at='2026-06-03T01:00:00Z',
        staged_by='efactory-test',
        trigger='/sim-run',
    )
    write_staged_metadata(meta_path(sp), meta)
    return parent_hash if parent_hash else ''


class _NeverHeld:
    def is_held_by_kicad(self, _active: Path) -> bool:
        return False


class _AlwaysHeld:
    def is_held_by_kicad(self, _active: Path) -> bool:
        return True


@pytest.mark.asyncio
async def test_missing_project_raises(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        await apply_staged_schematic(
            name='missing',
            projects_root=tmp_path,
            lock_detector=_NeverHeld(),
            scanner=KicadPendingStagedScanner(),
        )


@pytest.mark.asyncio
async def test_no_pending_returns_empty(tmp_path: Path) -> None:
    (tmp_path / 'demo').mkdir()
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == ()
    assert out.skipped == ()


@pytest.mark.asyncio
async def test_happy_path_applies_and_removes_meta(tmp_path: Path) -> None:
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == (active,)
    assert active.read_text(encoding='utf-8') == 'NEW'
    assert not staged_path(active).exists()
    assert not meta_path(staged_path(active)).exists()


@pytest.mark.asyncio
async def test_lock_held_skips_without_force(tmp_path: Path) -> None:
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_AlwaysHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == ()
    assert len(out.skipped) == 1
    assert out.skipped[0].reason == 'lock'
    assert active.read_text() == 'OLD'  # untouched
    assert staged_path(active).exists()


@pytest.mark.asyncio
async def test_lock_held_applies_with_force(tmp_path: Path) -> None:
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        force=True,
        lock_detector=_AlwaysHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == (active,)
    assert active.read_text() == 'NEW'


@pytest.mark.asyncio
async def test_parent_hash_mismatch_skips_without_accept_overwrite(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    # User modified active in KiCad GUI between staged-write and apply.
    active.write_bytes(b'DIVERGED')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == ()
    assert len(out.skipped) == 1
    skipped = out.skipped[0]
    assert skipped.reason == 'parent_hash_mismatch'
    assert skipped.current_hash == _sha256_hex(b'DIVERGED')
    assert skipped.expected_hash == _sha256_hex(b'OLD')
    assert active.read_bytes() == b'DIVERGED'  # untouched


@pytest.mark.asyncio
async def test_parent_hash_mismatch_overwrites_with_accept_overwrite(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    active.write_bytes(b'DIVERGED')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        accept_overwrite=True,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == (active,)
    assert active.read_text() == 'NEW'


@pytest.mark.asyncio
async def test_force_alone_does_not_bypass_parent_hash_check(tmp_path: Path) -> None:
    """W1 (c) semantic: --force bypasses lock only, not parent-hash mismatch."""
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    active.write_bytes(b'DIVERGED')
    # Lock пресенчирован чтобы оба check'а имели причину сработать.
    lock_path(active).write_text('{}', encoding='utf-8')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        force=True,  # bypass lock only
        lock_detector=_AlwaysHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == ()
    assert len(out.skipped) == 1
    assert out.skipped[0].reason == 'parent_hash_mismatch'


@pytest.mark.asyncio
async def test_both_flags_apply_through(tmp_path: Path) -> None:
    project_root = tmp_path / 'demo'
    active = project_root / 'foo.kicad_sch'
    _setup_pair(active, b'OLD', 'NEW')
    active.write_bytes(b'DIVERGED')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        force=True,
        accept_overwrite=True,
        lock_detector=_AlwaysHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == (active,)
    assert active.read_text() == 'NEW'


@pytest.mark.asyncio
async def test_multi_sheet_partial(tmp_path: Path) -> None:
    project_root = tmp_path / 'demo'
    a1 = project_root / 'root.kicad_sch'
    a2 = project_root / 'sub' / 'sub.kicad_sch'
    _setup_pair(a1, b'A1OLD', 'A1NEW')
    _setup_pair(a2, b'A2OLD', 'A2NEW')
    # Поломать parent_hash для второго (a2 был изменён в GUI).
    a2.write_bytes(b'A2DIVERGED')
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert a1 in out.applied
    assert any(s.active_path == a2 for s in out.skipped)
    assert a1.read_text() == 'A1NEW'
    assert a2.read_bytes() == b'A2DIVERGED'


@pytest.mark.asyncio
async def test_fresh_active_none_parent_hash_applies_cleanly(tmp_path: Path) -> None:
    """Active не существовал на момент staged write (parent_hash=None)."""
    project_root = tmp_path / 'demo'
    project_root.mkdir()
    active = project_root / 'fresh.kicad_sch'
    sp = staged_path(active)
    sp.write_text('FRESH', encoding='utf-8')
    meta = StagedMetadata(
        parent_hash=None,
        staged_at='2026-06-03T01:00:00Z',
        staged_by='efactory-test',
        trigger='/project-create',
    )
    write_staged_metadata(meta_path(sp), meta)
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == (active,)
    assert active.read_text() == 'FRESH'


@pytest.mark.asyncio
async def test_orphan_staged_without_meta_requires_accept_overwrite(
    tmp_path: Path,
) -> None:
    """Sidecar отсутствует → parent_hash unknown → reject без accept_overwrite."""
    project_root = tmp_path / 'demo'
    project_root.mkdir()
    active = project_root / 'foo.kicad_sch'
    active.write_bytes(b'CURRENT')
    staged_path(active).write_text('NEW', encoding='utf-8')
    # meta.json deliberately absent
    out = await apply_staged_schematic(
        name='demo',
        projects_root=tmp_path,
        lock_detector=_NeverHeld(),
        scanner=KicadPendingStagedScanner(),
    )
    assert out.applied == ()
    assert len(out.skipped) == 1
    assert out.skipped[0].reason == 'parent_hash_mismatch'
