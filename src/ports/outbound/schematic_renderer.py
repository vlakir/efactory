"""SchematicRenderer — outbound port для рендера `.kicad_sch` → PNG/SVG (T025)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path


@dataclass(frozen=True)
class SchematicRender:
    """Артефакт рендера схемы — пути к PNG (+ исходные SVG для T032)."""

    png_paths: tuple[Path, ...]
    svg_paths: tuple[Path, ...]
    created_at: datetime


class SchematicRenderError(Exception):
    """Рендер схемы упал (kicad-cli / rsvg-convert non-zero exit, нет файлов)."""


class SchematicRenderer(Protocol):
    """Рендер `.kicad_sch` → PNG-per-sheet (T025)."""

    async def render(
        self,
        schematic: Path,
        out_root: Path,
    ) -> SchematicRender:
        """
        Отрендерить `schematic` в timestamped subdir под `out_root`.

        Создаёт `out_root/<UTC TS>/` с одним SVG и одним PNG на каждый
        лист схемы. Возвращает `SchematicRender` с отсортированными по
        filename путями (стабильный порядок независимо от kicad-cli
        sheet ordering).

        Бросает `SchematicRenderError` при сбое kicad-cli, rsvg-convert
        или отсутствии output-файлов.
        """
        ...
