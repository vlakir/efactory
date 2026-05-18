"""SchematicWriter — outbound port для записи `.kicad_sch` (T100 facade)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.schematic import SchematicSpec


class SchematicWriteError(Exception):
    """Адаптер не смог записать .kicad_sch (I/O, неизвестный lib_id и т.п.)."""


class SchematicWriter(Protocol):
    """Сериализатор `SchematicSpec` → файл `.kicad_sch` на диск."""

    def write(self, spec: SchematicSpec, path: Path) -> Path:
        """
        Атомарно записать schematic в `path` (создаёт parent dir).

        Возвращает `path` для chain-вызова. Бросает `SchematicWriteError`
        при ошибке (неизвестный lib_id, неудачный I/O).
        """
        ...
