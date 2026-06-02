"""
Sidecar `.meta.json` для T026 staged-модификаций.

Хранит `parent_hash` (sha256 hex active content на момент write staged) +
diagnostic поля (`staged_at`, `staged_by`, `trigger`). При apply-staged
use case сравнивает `current_active_hash` против `parent_hash` —
mismatch → reject без `--accept-overwrite` (защита от silent data loss).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path


_HEX64 = r'^[0-9a-f]{64}$'


class StagedMetadata(BaseModel):
    """Sidecar `<staged>.meta.json` структура."""

    model_config = ConfigDict(frozen=True, extra='forbid')

    parent_hash: str | None = Field(
        default=None,
        description=(
            'sha256 hex active content до write staged; '
            'None если active не существовал.'
        ),
        pattern=_HEX64,
    )
    staged_at: str = Field(description='ISO8601 UTC timestamp staged write.')
    staged_by: str = Field(description='efactory version identifier.')
    trigger: str = Field(
        description='Operation который триггернул staged-write (e.g. /sim-run).',
    )


def write_staged_metadata(target: Path, meta: StagedMetadata) -> None:
    target.write_text(meta.model_dump_json(indent=2), encoding='utf-8')


def read_staged_metadata(source: Path) -> StagedMetadata:
    return StagedMetadata.model_validate_json(source.read_text(encoding='utf-8'))


__all__ = ['StagedMetadata', 'read_staged_metadata', 'write_staged_metadata']
