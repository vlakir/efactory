"""Unit tests для prune_sim_results use case (T142).

Use case orchestrates retention policy + delegation в SimResultsRepository.
Adapter tests (FS-specifics) — отдельно в integration layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.prune_sim_results import (
    DEFAULT_KEEP_LAST,
    PruneOptionsInvalidError,
    prune_sim_results,
)

if TYPE_CHECKING:
    pass


class FakeRepo:
    """Fake SimResultsRepository — records prune calls, returns заданный count."""

    def __init__(self, deleted_count: int = 0) -> None:
        self._deleted = deleted_count
        self.calls: list[tuple[Path, int | None, int | None]] = []

    async def write(self, *, result, project_root):  # noqa: ARG002, ANN001, ANN201
        raise NotImplementedError

    async def prune(
        self,
        *,
        project_root: Path,
        keep_last: int | None = None,
        keep_days: int | None = None,
    ) -> int:
        self.calls.append((project_root, keep_last, keep_days))
        return self._deleted


# ────────── happy paths ──────────


async def test_prune_default_uses_keep_last_100(tmp_path: Path) -> None:
    repo = FakeRepo(deleted_count=42)

    deleted = await prune_sim_results(project_root=tmp_path, repo=repo)

    assert deleted == 42
    assert len(repo.calls) == 1
    assert repo.calls[0] == (tmp_path, DEFAULT_KEEP_LAST, None)


async def test_prune_explicit_keep_last(tmp_path: Path) -> None:
    repo = FakeRepo(deleted_count=5)

    deleted = await prune_sim_results(
        project_root=tmp_path, repo=repo, keep_last=50,
    )

    assert deleted == 5
    assert repo.calls[0] == (tmp_path, 50, None)


async def test_prune_explicit_keep_days(tmp_path: Path) -> None:
    repo = FakeRepo(deleted_count=10)

    deleted = await prune_sim_results(
        project_root=tmp_path, repo=repo, keep_days=30,
    )

    assert deleted == 10
    assert repo.calls[0] == (tmp_path, None, 30)


async def test_prune_returns_zero_when_nothing_to_delete(tmp_path: Path) -> None:
    repo = FakeRepo(deleted_count=0)

    deleted = await prune_sim_results(project_root=tmp_path, repo=repo)

    assert deleted == 0


# ────────── validation ──────────


async def test_prune_rejects_both_policies(tmp_path: Path) -> None:
    """`--keep-last` и `--keep-days` mutually exclusive."""
    repo = FakeRepo()

    with pytest.raises(PruneOptionsInvalidError, match='mutually exclusive'):
        await prune_sim_results(
            project_root=tmp_path,
            repo=repo,
            keep_last=50,
            keep_days=30,
        )
    assert repo.calls == []


async def test_prune_rejects_negative_keep_last(tmp_path: Path) -> None:
    repo = FakeRepo()
    with pytest.raises(PruneOptionsInvalidError, match='non-negative'):
        await prune_sim_results(
            project_root=tmp_path, repo=repo, keep_last=-1,
        )


async def test_prune_rejects_zero_keep_days(tmp_path: Path) -> None:
    """keep_days=0 = delete everything; вряд ли что-то useful, reject."""
    repo = FakeRepo()
    with pytest.raises(PruneOptionsInvalidError, match='positive'):
        await prune_sim_results(
            project_root=tmp_path, repo=repo, keep_days=0,
        )
