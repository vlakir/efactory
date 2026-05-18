"""SpiceModel — generic VO для SPICE-моделей компонентов efactory (T006, T007)."""

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


class ComponentCategory(StrEnum):
    """Класс электронного компонента (T007 generalization, T101 диоды)."""

    TUBE = 'tube'
    TRANSFORMER = 'transformer'
    LOAD = 'load'
    DIODE = 'diode'


class TubeType(StrEnum):
    """Подкатегория для category=TUBE."""

    TRIODE = 'triode'
    TETRODE = 'tetrode'
    PENTODE = 'pentode'
    DUAL_TRIODE = 'dual_triode'
    RECTIFIER = 'rectifier'


class TransformerKind(StrEnum):
    """Подкатегория для category=TRANSFORMER."""

    OPT = 'opt'  # output transformer
    # будущее: PT (power), IT (interstage), CHOKE


class LoadKind(StrEnum):
    """Подкатегория для category=LOAD."""

    SPEAKER = 'speaker'
    RESISTIVE = 'resistive'  # dummy load


class DiodeKind(StrEnum):
    """Подкатегория для category=DIODE (T101)."""

    RECTIFIER = 'rectifier'  # general-purpose / power (1N4007, ...)
    SIGNAL = 'signal'  # small-signal / switching (1N4148, ...)
    SCHOTTKY = 'schottky'  # Schottky (BAT85, 1N5817, ...)
    ZENER = 'zener'  # voltage reference
    LED = 'led'  # light-emitting


class ModelSource(StrEnum):
    """
    Источник параметров / vendor.

    Для tubes: koren/ayumi/duncan/custom (T006).
    Для transformers/loads: generic (typical класс), либо vendor name
    (`hammond`, `tango`, `custom`) в будущем.
    """

    KOREN = 'koren'
    AYUMI = 'ayumi'
    DUNCAN = 'duncan'
    CUSTOM = 'custom'
    GENERIC = 'generic'  # T007: typical-class fit без vendor specificity


class SpiceModel(BaseModel):
    """Generic SPICE-модель компонента (tube / transformer / load)."""

    model_config = ConfigDict(frozen=True, extra='ignore')

    id: SpiceModelId
    name: str
    category: ComponentCategory
    # TubeType / TransformerKind / LoadKind value (str для extensibility).
    subcategory: str
    source: ModelSource
    file_path: Path
    subckt_pins: tuple[str, ...]
    is_user: bool = False  # True если модель из user overlay (T006 fix-up)

    @property
    def tube_type(self) -> TubeType:
        """Typed accessor для category=TUBE; raises иначе."""
        if self.category is not ComponentCategory.TUBE:
            msg = f'tube_type accessor invalid for category={self.category.value}'
            raise ValueError(msg)
        return TubeType(self.subcategory)

    @property
    def transformer_kind(self) -> TransformerKind:
        """Typed accessor для category=TRANSFORMER; raises иначе."""
        if self.category is not ComponentCategory.TRANSFORMER:
            msg = (
                f'transformer_kind accessor invalid for category={self.category.value}'
            )
            raise ValueError(msg)
        return TransformerKind(self.subcategory)

    @property
    def load_kind(self) -> LoadKind:
        """Typed accessor для category=LOAD; raises иначе."""
        if self.category is not ComponentCategory.LOAD:
            msg = f'load_kind accessor invalid for category={self.category.value}'
            raise ValueError(msg)
        return LoadKind(self.subcategory)

    @property
    def diode_kind(self) -> DiodeKind:
        """Typed accessor для category=DIODE; raises иначе."""
        if self.category is not ComponentCategory.DIODE:
            msg = f'diode_kind accessor invalid for category={self.category.value}'
            raise ValueError(msg)
        return DiodeKind(self.subcategory)
