"""Unit-тесты `WriterNotifier` (T026 Phase 1)."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.schematic_kicad.notifier import (
    NullWriterNotifier,
    RecordingWriterNotifier,
)


def test_null_notifier_swallows_events() -> None:
    notifier = NullWriterNotifier()
    notifier.staged(Path('/x.staged'))
    notifier.staged_overwrite('a' * 64)


def test_recording_notifier_captures_staged_events() -> None:
    notifier = RecordingWriterNotifier()
    notifier.staged(Path('/x.staged'))
    assert notifier.staged_events == [Path('/x.staged')]


def test_recording_notifier_captures_overwrite_events() -> None:
    notifier = RecordingWriterNotifier()
    notifier.staged_overwrite('b' * 64)
    assert notifier.overwrite_events == ['b' * 64]
