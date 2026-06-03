"""
Outbound port: T026 staged-модификации `.kicad_sch`.

Содержит:
- `LockDetector` Protocol — «удерживается ли файл сторонним инструментом».
- `PendingStagedEntry` DTO — описание одной pending staged-модификации.
- `PendingStagedScanner` Protocol — find pending staged'и в project root.

Конкретные KiCad-реализации живут в
`adapters/outbound/schematic_kicad/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class LockDetector(Protocol):
    """Абстракция «удерживается ли файл сторонним инструментом»."""

    def is_held_by_kicad(self, active: Path) -> bool: ...


@dataclass(frozen=True)
class PendingStagedEntry:
    """Одна pending staged-модификация для apply-staged."""

    active_path: Path
    staged_path: Path
    meta_path: Path
    parent_hash: str | None  # None если sidecar отсутствует или active не существовал.


class PendingStagedScanner(Protocol):
    """Find pending `<name>.kicad_sch.staged` файлы в project root рекурсивно."""

    def scan(self, project_root: Path) -> list[PendingStagedEntry]: ...


__all__ = ['LockDetector', 'PendingStagedEntry', 'PendingStagedScanner']
