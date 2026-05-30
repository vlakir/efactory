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

    async def prune(
        self,
        *,
        project_root: Path,
        keep_last: int | None = None,
        keep_days: int | None = None,
    ) -> int:
        """
        Retention/cleanup: удалить старые sim-results файлы (T142).

        - `keep_last=N`: оставить N последних (sorted by filename
          ascending — timestamp-prefix даёт chronological order).
        - `keep_days=D`: удалить файлы старше D дней (по filename-
          timestamp если parsable, иначе по `mtime`).
        - Mutually exclusive: только одна policy за вызов.
        - Без options — no-op (return 0).

        Returns:
            Количество удалённых файлов.

        Raises:
            ValueError: при `keep_last` и `keep_days` одновременно.

        """
