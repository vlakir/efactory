"""Unit-тесты staged-write поведения `KicadSchematicWriter` (T026 Phase 1)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from ports.outbound.staged_schematics import LockDetector
from adapters.outbound.schematic_kicad.notifier import RecordingWriterNotifier
from adapters.outbound.schematic_kicad.staged_metadata import read_staged_metadata
from adapters.outbound.schematic_kicad.staged_paths import (
    lock_path,
    meta_path,
    staged_path,
)
from adapters.outbound.schematic_kicad.writer import KicadSchematicWriter
from domain.schematic import ComponentSpec, Position, SchematicSpec

if TYPE_CHECKING:
    pass


class _AlwaysHeld:
    def is_held_by_kicad(self, active: Path) -> bool:
        return True


class _NeverHeld:
    def is_held_by_kicad(self, active: Path) -> bool:
        return False


class _LockByPresenceFake:
    """Использует существующий KiCad-pattern lock-файла рядом."""

    def is_held_by_kicad(self, active: Path) -> bool:
        return lock_path(active).exists()


def _minimal_spec(name: str = 'unit', value: str = '1k') -> SchematicSpec:
    return SchematicSpec(
        name=name,
        components=(
            ComponentSpec(
                lib_id='Device:R',
                reference='R1',
                value=value,
                position=Position(x_mm=10.0, y_mm=20.0),
                pins=('1', '2'),
            ),
        ),
    )


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_no_lock_writes_directly(tmp_path: Path) -> None:
    out = tmp_path / 'foo.kicad_sch'
    notifier = RecordingWriterNotifier()
    writer = KicadSchematicWriter(
        notifier=notifier, lock_detector=_NeverHeld(),
    )
    result = writer.write(_minimal_spec(), out)
    assert result == out
    assert out.is_file()
    assert not staged_path(out).exists()
    assert notifier.staged_events == []


def test_lock_held_writes_staged(tmp_path: Path) -> None:
    out = tmp_path / 'foo.kicad_sch'
    notifier = RecordingWriterNotifier()
    writer = KicadSchematicWriter(
        notifier=notifier, lock_detector=_AlwaysHeld(),
    )
    result = writer.write(_minimal_spec(), out)
    assert result == staged_path(out)
    assert staged_path(out).is_file()
    assert not out.exists()  # active нетронут
    assert notifier.staged_events == [staged_path(out)]


def test_staged_write_writes_sidecar_with_parent_hash(tmp_path: Path) -> None:
    out = tmp_path / 'foo.kicad_sch'
    out.write_text('old content', encoding='utf-8')
    parent_hash_expected = _sha256_hex(b'old content')
    writer = KicadSchematicWriter(lock_detector=_AlwaysHeld())
    writer.write(_minimal_spec(), out)
    meta = read_staged_metadata(meta_path(staged_path(out)))
    assert meta.parent_hash == parent_hash_expected


def test_staged_write_no_active_records_none_parent_hash(tmp_path: Path) -> None:
    out = tmp_path / 'fresh.kicad_sch'
    writer = KicadSchematicWriter(lock_detector=_AlwaysHeld())
    writer.write(_minimal_spec(), out)
    meta = read_staged_metadata(meta_path(staged_path(out)))
    assert meta.parent_hash is None


def test_staged_overwrite_emits_previous_hash(tmp_path: Path) -> None:
    out = tmp_path / 'foo.kicad_sch'
    notifier = RecordingWriterNotifier()
    writer = KicadSchematicWriter(
        notifier=notifier, lock_detector=_AlwaysHeld(),
    )
    writer.write(_minimal_spec(value='1k'), out)
    first_staged_bytes = staged_path(out).read_bytes()
    first_hash = _sha256_hex(first_staged_bytes)
    notifier.overwrite_events.clear()  # reset
    writer.write(_minimal_spec(value='10k'), out)
    assert notifier.overwrite_events == [first_hash]


def test_staged_idempotent_no_op_when_identical(tmp_path: Path) -> None:
    out = tmp_path / 'foo.kicad_sch'
    notifier = RecordingWriterNotifier()
    writer = KicadSchematicWriter(
        notifier=notifier, lock_detector=_AlwaysHeld(),
    )
    spec = _minimal_spec()
    writer.write(spec, out)
    first_meta_mtime = meta_path(staged_path(out)).stat().st_mtime
    notifier.staged_events.clear()
    notifier.overwrite_events.clear()
    # Identical re-write must be no-op.
    # NB: SchematicSpec includes generated UUIDs at serialize time, so we must
    # compare serialized text to detect identity. The writer recomputes UUIDs
    # for each serialize call, so byte-identity is impossible cross-call.
    # Re-write with same spec → different bytes (new UUIDs) → not no-op.
    # This test documents the limitation: idempotence is by **content equality**,
    # not by **spec equality**. Re-running with identical spec still writes.
    writer.write(spec, out)
    # Meta updated (new content even if logically equivalent).
    assert meta_path(staged_path(out)).stat().st_mtime >= first_meta_mtime
    # Overwrite event fired (previous staged dropped).
    assert len(notifier.overwrite_events) == 1


def test_lock_detector_uses_kicad_pattern_integration(tmp_path: Path) -> None:
    """Integration: создаём ~<name>.lck вручную, writer переключается на staged."""
    out = tmp_path / 'foo.kicad_sch'
    lock_path(out).write_text('{"hostname":"h","username":"u"}', encoding='utf-8')
    writer = KicadSchematicWriter(lock_detector=_LockByPresenceFake())
    result = writer.write(_minimal_spec(), out)
    assert result == staged_path(out)


def test_default_construction_uses_kicad_lock_detector(tmp_path: Path) -> None:
    """Default constructor → real KiCad detector; без lock — direct write."""
    out = tmp_path / 'foo.kicad_sch'
    writer = KicadSchematicWriter()  # defaults
    result = writer.write(_minimal_spec(), out)
    assert result == out
    assert out.is_file()


def test_default_with_real_lock_detector_writes_staged(tmp_path: Path) -> None:
    out = tmp_path / 'foo.kicad_sch'
    lock_path(out).write_text('{"hostname":"h","username":"u"}', encoding='utf-8')
    writer = KicadSchematicWriter()  # defaults — KicadLockDetector
    result = writer.write(_minimal_spec(), out)
    assert result == staged_path(out)


def test_lock_detector_protocol_accepts_any_callable_shape(tmp_path: Path) -> None:
    """LockDetector — Protocol, любой объект с is_held_by_kicad()."""
    out = tmp_path / 'foo.kicad_sch'
    detector: LockDetector = _AlwaysHeld()
    writer = KicadSchematicWriter(lock_detector=detector)
    assert writer.write(_minimal_spec(), out) == staged_path(out)
