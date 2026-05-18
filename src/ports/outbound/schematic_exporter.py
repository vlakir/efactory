"""SchematicExporter — outbound port для экспорта `.kicad_sch` → SPICE (T004)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class SchematicExportError(Exception):
    """Экспортировщик не смог получить SPICE netlist из schematic."""


class SchematicExporter(Protocol):
    """Конвертация KiCad schematic в SPICE netlist (T004 split-scope)."""

    async def export_spice_netlist(
        self,
        schematic: Path,
        output: Path,
    ) -> Path:
        """
        Экспорт `<schematic>.kicad_sch` → `<output>.cir`.

        Возвращает фактический путь `output` для chain-вызова.
        Бросает `SchematicExportError` при ненулевом exit code
        внешнего инструмента или I/O сбое.
        """
        ...
