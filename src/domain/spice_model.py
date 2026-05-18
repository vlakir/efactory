"""SpiceModel — VO для tube SPICE model library (T006)."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

_ID_RE = re.compile(r'^[A-Z0-9][A-Z0-9_]+$')


def _validate_id(value: str) -> str:
    if not _ID_RE.match(value):
        msg = (
            f'SpiceModelId must match {_ID_RE.pattern} '
            f"(uppercase letters/digits/underscore, ≥2 chars, no leading '_'), "
            f"got '{value}'"
        )
        raise ValueError(msg)
    return value


SpiceModelId = Annotated[str, AfterValidator(_validate_id)]


class TubeType(StrEnum):
    TRIODE = 'triode'
    TETRODE = 'tetrode'
    PENTODE = 'pentode'
    DUAL_TRIODE = 'dual_triode'


class ModelSource(StrEnum):
    KOREN = 'koren'
    AYUMI = 'ayumi'
    DUNCAN = 'duncan'
    CUSTOM = 'custom'


class SpiceModel(BaseModel):
    """
    Метаданные SPICE-модели одной лампы.

    `id` уникален в библиотеке (= uppercase filename stem). `name` —
    `.SUBCKT <name>` из самого файла (то, что пишется в ngspice
    нетлисте). `subckt_pins` — порядок пинов из той же `.SUBCKT`
    строки, используется для будущей валидации `model_assign` (T005).
    """

    model_config = ConfigDict(frozen=True, extra='ignore')

    id: SpiceModelId
    name: str
    tube_type: TubeType
    source: ModelSource
    file_path: Path
    subckt_pins: tuple[str, ...]
