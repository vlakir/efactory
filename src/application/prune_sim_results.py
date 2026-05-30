"""
prune_sim_results — retention policy для `.efactory/sim-results/` (T142).

Use case orchestrates input validation + delegates в SimResultsRepository.
Adapter-side actual file deletion — `FileSystemSimResults.prune`.

Policies (mutually exclusive):
- `keep_last`: оставить N последних (sorted by filename ascending —
  timestamp-prefix даёт chronological order).
- `keep_days`: удалить файлы старше D дней.

Default: `keep_last=100` если ни один параметр не указан.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.sim_results import SimResultsRepository


DEFAULT_KEEP_LAST = 100


class PruneOptionsInvalidError(ValueError):
    """Invalid options для prune (both/negative/zero)."""


async def prune_sim_results(
    *,
    project_root: Path,
    repo: SimResultsRepository,
    keep_last: int | None = None,
    keep_days: int | None = None,
) -> int:
    """
    Apply retention policy to project sim-results.

    Args:
        project_root: Path to project root (где находится
            `.efactory/sim-results/`).
        repo: outbound port.
        keep_last: keep N newest файлов (mutually exclusive с keep_days).
        keep_days: keep файлы новее D дней (mutually exclusive с keep_last).
            Если ни один не указан — default `keep_last=DEFAULT_KEEP_LAST`.

    Returns:
        Количество удалённых файлов.

    Raises:
        PruneOptionsInvalidError: при invalid combinations или values.

    """
    if keep_last is not None and keep_days is not None:
        msg = '--keep-last и --keep-days mutually exclusive'
        raise PruneOptionsInvalidError(msg)
    if keep_last is not None and keep_last < 0:
        msg = f'keep_last должен быть non-negative, получено {keep_last}'
        raise PruneOptionsInvalidError(msg)
    if keep_days is not None and keep_days <= 0:
        msg = f'keep_days должен быть positive, получено {keep_days}'
        raise PruneOptionsInvalidError(msg)

    # Default policy: keep_last = DEFAULT_KEEP_LAST.
    if keep_last is None and keep_days is None:
        keep_last = DEFAULT_KEEP_LAST

    return await repo.prune(
        project_root=project_root,
        keep_last=keep_last,
        keep_days=keep_days,
    )


__all__ = [
    'DEFAULT_KEEP_LAST',
    'PruneOptionsInvalidError',
    'prune_sim_results',
]
