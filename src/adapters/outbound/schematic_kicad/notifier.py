"""
Notifier abstraction для T026 staged-write events.

`SchematicWriter` сам решает, направить запись в `active` или `staged`
(по результату `LockDetector`), и сигналит наблюдателю о двух событиях:
  - `staged(path)` — был выбран staged-режим, файл записан в `<x>.staged`;
  - `staged_overwrite(prev_hash)` — staged уже существовал, перезаписан;
    `prev_hash` — sha256 hex (full) ранее записанного staged content.

CLI-инкарнация преобразует события в `schematic-staged: <abs>` /
`schematic-staged-overwrite: previous <prefix> dropped` строки stdout
(паттерн T025 `schematic-render:`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class WriterNotifier(Protocol):
    """Наблюдатель staged-write событий."""

    def staged(self, staged_path: Path) -> None: ...

    def staged_overwrite(self, previous_hash: str) -> None: ...


class NullWriterNotifier:
    """Default: события игнорируются (например, batch-сценарий без UI)."""

    def staged(self, _staged_path: Path) -> None:
        return None

    def staged_overwrite(self, _previous_hash: str) -> None:
        return None


class RecordingWriterNotifier:
    """Тестовый notifier — накапливает события для assertion."""

    def __init__(self) -> None:
        self.staged_events: list[Path] = []
        self.overwrite_events: list[str] = []

    def staged(self, staged_path: Path) -> None:
        self.staged_events.append(staged_path)

    def staged_overwrite(self, previous_hash: str) -> None:
        self.overwrite_events.append(previous_hash)


__all__ = ['NullWriterNotifier', 'RecordingWriterNotifier', 'WriterNotifier']
