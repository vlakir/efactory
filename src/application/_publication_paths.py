"""
Shared path helpers для T035 publication use cases (Phase 3.1 + 3.2).

`run_export_schematic_publication` и `run_export_sim_report` оба пишут
в `<project.path>/out/publications/<ts>/`, оба резолвят collision-safe
ts (W-4), оба используют один и тот же UTC-`now()`. Вынесено в private
package-module чтобы не дублировать.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


PUBLICATIONS_SUBDIR = 'out/publications'
SCHEMATIC_SUBDIR = 'schematic'
SIM_REPORT_SUBDIR = 'sim-report'


def default_now() -> datetime:
    return datetime.now(UTC)


def resolve_schematic_path(project_path: Path, schematic: Path) -> Path:
    if schematic.is_absolute():
        return schematic
    return project_path / schematic


def resolve_ts_root(publications_root: Path, ts_dirname: str) -> Path:
    """
    Resolve collision-safe `<publications_root>/<ts_dirname>[-N]/` (W-4).

    Если каталог не существует — возвращаем как есть. Если существует
    и пуст — переиспользуем. Если существует и содержит файлы — пробуем
    суффикс `-1`, `-2`, ..., до первого свободного имени.
    """
    candidate = publications_root / ts_dirname
    if not candidate.exists():
        return candidate
    if candidate.is_dir() and not any(candidate.iterdir()):
        return candidate
    suffix = 1
    while True:
        with_suffix = publications_root / f'{ts_dirname}-{suffix}'
        if not with_suffix.exists():
            return with_suffix
        if with_suffix.is_dir() and not any(with_suffix.iterdir()):
            return with_suffix
        suffix += 1


__all__ = [
    'PUBLICATIONS_SUBDIR',
    'SCHEMATIC_SUBDIR',
    'SIM_REPORT_SUBDIR',
    'default_now',
    'resolve_schematic_path',
    'resolve_ts_root',
]
