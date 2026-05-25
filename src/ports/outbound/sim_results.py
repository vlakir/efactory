"""
SimResultsRepository — outbound port для записи sim-результатов (T016).

Adapter'ы по этому port'у persist'ят `SimResult` в проект. Канонический
file-system adapter — `FileSystemSimResults` (см. `adapters/outbound/
sim_results_filesystem/`); альтернативные backend'ы (например, sqlite
или удалённый бэкенд) могут появиться позже как отдельные adapter'ы
без изменений в use cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.sim_results import SimResult


class SimResultsWriteFailedError(Exception):
    """Запись sim-результата завершилась ошибкой (нет project_root, FS error)."""


class SimResultsRepository(Protocol):
    """Outbound port: persist одного `SimResult` в контекст проекта."""

    async def write(
        self,
        *,
        result: SimResult,
        project_root: Path,
    ) -> Path:
        """
        Persist `result` в каталог проекта; вернуть абсолютный path JSON.

        Бросает `SimResultsWriteFailedError` если `project_root` не
        существует или FS не позволяет записать.
        """
