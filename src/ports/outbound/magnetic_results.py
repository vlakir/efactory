"""
MagneticResultsRepository — outbound port для persist mag-summary (T189).

Adapter'ы persist'ят `MagneticsSummary` JSON sidecar для downstream
`/export-sim-report` (T035) M-thin секции «Магнитные компоненты».
Канонический FS adapter — `FileSystemMagneticResults` (см. `adapters/
outbound/magnetic_results_filesystem/`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.magnetic_summary import MagneticsSummary


class MagneticResultsWriteFailedError(Exception):
    """Запись magnetics summary завершилась ошибкой (FS error / schema)."""


class MagneticResultsRepository(Protocol):
    """Outbound port: persist `MagneticsSummary` в проект."""

    async def write(
        self,
        *,
        summary: MagneticsSummary,
        project_root: Path,
    ) -> Path:
        """
        Persist `summary` в каталог проекта; вернуть абсолютный path JSON.

        Бросает `MagneticResultsWriteFailedError` при FS / schema-ошибке.
        """

    def find_latest(self, *, project_root: Path) -> Path | None:
        """
        Найти latest summary.json (или вернуть None если каталог пуст).

        Sync API — без IO-heavy операций, простой directory listing.
        """


__all__ = [
    'MagneticResultsRepository',
    'MagneticResultsWriteFailedError',
]
