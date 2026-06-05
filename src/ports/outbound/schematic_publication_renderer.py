"""
SchematicPublicationRenderer — outbound port для publication-grade рендера схемы (T035).

В отличие от T025 `SchematicRenderer` (терминальный preview, PNG @ 120 DPI),
publication-renderer:

- генерирует три формата артефактов одной командой: SVG (vector),
  PDF (vector), PNG @ 300 DPI (raster для печати);
- генерирует обе цветовые версии (color KiCad default + bw) в
  одном вызове;
- поддерживает `multi_sheet_mode` (`PER_SHEET` / `COMBINED`) —
  combined-PDF создаётся дополнительно к per-sheet артефактам.

Порт `render(...)` — единственный entry point; возвращает frozen
`SchematicPublicationArtifacts` (T035 Phase 1 VO).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.publication import MultiSheetMode, SchematicPublicationArtifacts


class SchematicPublicationRenderError(Exception):
    """Publication-рендер упал (kicad-cli / rsvg-convert non-zero, нет файлов)."""


class SchematicPublicationRenderer(Protocol):
    """Publication-grade рендер `.kicad_sch` (T035)."""

    async def render(
        self,
        schematic: Path,
        out_dir: Path,
        *,
        multi_sheet_mode: MultiSheetMode,
    ) -> SchematicPublicationArtifacts:
        """
        Render schematic в `out_dir` с publication-grade artefacts.

        Создаёт `out_dir/color/per-sheet/` + `out_dir/bw/per-sheet/`,
        каждый с тройкой `<sheet>.svg` + `<sheet>.pdf` + `<sheet>.png`
        (последний — 300 DPI raster). При `multi_sheet_mode=COMBINED`
        дополнительно создаёт `out_dir/{color,bw}/combined/<project>.pdf`
        (multi-page PDF со всеми листами).

        Args:
            schematic: путь к корневому `.kicad_sch` (multi-sheet
                проекты — root schematic, kicad-cli сам обходит
                дочерние листы).
            out_dir: каталог, в котором будут созданы подкаталоги
                `color/`, `bw/`. Уже должен существовать.
            multi_sheet_mode: `PER_SHEET` (default по spec) или
                `COMBINED`.

        Returns:
            `SchematicPublicationArtifacts` с отсортированными по
            имени листа путями.

        Raises:
            SchematicPublicationRenderError: kicad-cli / rsvg-convert
                non-zero exit, отсутствие SVG/PDF/PNG output'а.

        """
        ...


__all__ = [
    'SchematicPublicationRenderError',
    'SchematicPublicationRenderer',
]
