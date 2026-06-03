"""Unit-тесты `StagedMetadata` sidecar I/O (T026 Phase 1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from adapters.outbound.schematic_kicad.staged_metadata import (
    StagedMetadata,
    read_staged_metadata,
    write_staged_metadata,
)

if TYPE_CHECKING:
    from pathlib import Path


def _sample(parent_hash: str | None = 'a' * 64) -> StagedMetadata:
    return StagedMetadata(
        parent_hash=parent_hash,
        staged_at='2026-06-03T01:00:00Z',
        staged_by='efactory-test',
        trigger='/sim-run',
    )


def test_round_trip_preserves_fields(tmp_path: Path) -> None:
    meta = _sample()
    target = tmp_path / 'foo.staged.meta.json'
    write_staged_metadata(target, meta)
    assert read_staged_metadata(target) == meta


def test_parent_hash_none_round_trip(tmp_path: Path) -> None:
    """Active не существовал на момент write staged — parent_hash=None."""
    meta = _sample(parent_hash=None)
    target = tmp_path / 'foo.staged.meta.json'
    write_staged_metadata(target, meta)
    assert read_staged_metadata(target).parent_hash is None


def test_parent_hash_must_be_64_hex(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        StagedMetadata(
            parent_hash='deadbeef',
            staged_at='2026-06-03T01:00:00Z',
            staged_by='efactory-test',
            trigger='/sim-run',
        )


def test_read_corrupted_json_raises(tmp_path: Path) -> None:
    target = tmp_path / 'broken.meta.json'
    target.write_text('{"parent_hash": "not-sha256"}', encoding='utf-8')
    with pytest.raises(ValidationError):
        read_staged_metadata(target)
