"""
KicadCliSchematicPublicationRenderer (T035 Phase 2.1).

Publication-grade рендер `.kicad_sch` → {color, bw} × {per-sheet PDF/SVG/PNG@300,
optional combined PDF}.

Pipeline на один color (повторяется дважды — для `color` и `bw`):

1. `kicad-cli sch export svg --output <out_dir>/<color>/per-sheet/
   [--black-and-white] <schematic>` — KiCad создаёт по одному SVG
   на лист (sheet ordering — alphabetical после glob).
2. Для каждого SVG: `rsvg-convert --dpi-x 300 --dpi-y 300 <svg> -o
   <png>` (300 DPI raster для печатного качества).
3. Для каждого SVG (`i = 1..N`):
   `kicad-cli sch export pdf --pages <i> --output <stem>.pdf
   [--black-and-white] <schematic>` — vector PDF per sheet.
4. (При `multi_sheet_mode=COMBINED`)
   `kicad-cli sch export pdf --output <combined>/<project>.pdf
   [--black-and-white] <schematic>` — single multi-page PDF.

Использует T009 `AppManager` для kicad-cli; rsvg-convert — generic
binary через `asyncio.create_subprocess_exec`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from domain.application import ApplicationKind
from domain.publication import (
    MultiSheetMode,
    SchematicPublicationArtifacts,
    SheetArtifactSet,
)
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
)
from ports.outbound.schematic_publication_renderer import (
    SchematicPublicationRenderError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.app_manager import AppManager


_PUBLICATION_DPI = '300'


class KicadCliSchematicPublicationRenderer:
    """SchematicPublicationRenderer на kicad-cli + rsvg-convert (T035)."""

    def __init__(self, app_manager: AppManager) -> None:
        self._app_manager = app_manager

    async def render(
        self,
        schematic: Path,
        out_dir: Path,
        *,
        multi_sheet_mode: MultiSheetMode,
    ) -> SchematicPublicationArtifacts:
        await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)

        color_per_sheet, color_combined = await self._render_color(
            schematic,
            out_dir / 'color',
            black_and_white=False,
            multi_sheet_mode=multi_sheet_mode,
        )
        bw_per_sheet, bw_combined = await self._render_color(
            schematic,
            out_dir / 'bw',
            black_and_white=True,
            multi_sheet_mode=multi_sheet_mode,
        )

        return SchematicPublicationArtifacts(
            color_per_sheet=color_per_sheet,
            bw_per_sheet=bw_per_sheet,
            color_combined=color_combined,
            bw_combined=bw_combined,
        )

    async def _render_color(
        self,
        schematic: Path,
        color_root: Path,
        *,
        black_and_white: bool,
        multi_sheet_mode: MultiSheetMode,
    ) -> tuple[tuple[SheetArtifactSet, ...], Path | None]:
        per_sheet_dir = color_root / 'per-sheet'
        await asyncio.to_thread(
            per_sheet_dir.mkdir,
            parents=True,
            exist_ok=True,
        )

        # Step 1: SVG export — kicad-cli создаёт по SVG на лист.
        await self._kicad_export_svg(
            schematic,
            per_sheet_dir,
            black_and_white=black_and_white,
        )

        svg_paths = tuple(sorted(per_sheet_dir.glob('*.svg')))
        if not svg_paths:
            msg = (
                f'kicad-cli sch export svg created no SVG files in '
                f'{per_sheet_dir} for schematic {schematic}.'
            )
            raise SchematicPublicationRenderError(msg)

        # Step 2: rsvg-convert SVG → PNG @ 300 DPI per sheet.
        png_paths = tuple(svg.with_suffix('.png') for svg in svg_paths)
        for svg, png in zip(svg_paths, png_paths, strict=True):
            await self._rsvg_convert_to_png_300(svg, png)

        # Step 3: per-sheet PDF — N вызовов kicad-cli с --pages.
        pdf_paths = tuple(svg.with_suffix('.pdf') for svg in svg_paths)
        for page_index, pdf_path in enumerate(pdf_paths, start=1):
            await self._kicad_export_pdf_page(
                schematic,
                pdf_path,
                page=page_index,
                black_and_white=black_and_white,
            )

        per_sheet_sets = tuple(
            SheetArtifactSet(
                sheet_name=svg.stem,
                svg=svg,
                pdf=pdf,
                png=png,
            )
            for svg, pdf, png in zip(svg_paths, pdf_paths, png_paths, strict=True)
        )

        # Step 4: combined PDF (optional).
        combined_path: Path | None = None
        if multi_sheet_mode is MultiSheetMode.COMBINED:
            combined_dir = color_root / 'combined'
            await asyncio.to_thread(
                combined_dir.mkdir,
                parents=True,
                exist_ok=True,
            )
            combined_path = combined_dir / f'{schematic.stem}.pdf'
            await self._kicad_export_pdf_combined(
                schematic,
                combined_path,
                black_and_white=black_and_white,
            )

        return per_sheet_sets, combined_path

    async def _kicad_export_svg(
        self,
        schematic: Path,
        out_dir: Path,
        *,
        black_and_white: bool,
    ) -> None:
        args = ['sch', 'export', 'svg', '--output', str(out_dir)]
        if black_and_white:
            args.append('--black-and-white')
        args.append(str(schematic))
        await self._run_kicad(args, schematic)

    async def _kicad_export_pdf_page(
        self,
        schematic: Path,
        output_pdf: Path,
        *,
        page: int,
        black_and_white: bool,
    ) -> None:
        args = [
            'sch',
            'export',
            'pdf',
            '--pages',
            str(page),
            '--output',
            str(output_pdf),
        ]
        if black_and_white:
            args.append('--black-and-white')
        args.append(str(schematic))
        await self._run_kicad(args, schematic)

    async def _kicad_export_pdf_combined(
        self,
        schematic: Path,
        output_pdf: Path,
        *,
        black_and_white: bool,
    ) -> None:
        args = [
            'sch',
            'export',
            'pdf',
            '--output',
            str(output_pdf),
        ]
        if black_and_white:
            args.append('--black-and-white')
        args.append(str(schematic))
        await self._run_kicad(args, schematic)

    async def _run_kicad(self, args: list[str], schematic: Path) -> None:
        try:
            result = await self._app_manager.run(
                ApplicationKind.KICAD_CLI,
                args,
            )
        except ApplicationNotInstalledError as exc:
            msg = (
                f'kicad-cli not available: {exc}. Install KiCad or set '
                f'EFACTORY_KICAD_PATH / EFACTORY_KICAD_CLI_PATH.'
            )
            raise SchematicPublicationRenderError(msg) from exc
        except ApplicationStartError as exc:
            msg = f'kicad-cli failed to start: {exc}'
            raise SchematicPublicationRenderError(msg) from exc

        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            msg = f'kicad-cli exit {result.returncode} on {schematic}: {details}'
            raise SchematicPublicationRenderError(msg)

    async def _rsvg_convert_to_png_300(self, svg: Path, png: Path) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                'rsvg-convert',
                '--dpi-x',
                _PUBLICATION_DPI,
                '--dpi-y',
                _PUBLICATION_DPI,
                str(svg),
                '-o',
                str(png),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            msg = (
                'rsvg-convert not available. Install librsvg2-bin '
                '(`apt-get install librsvg2-bin`).'
            )
            raise SchematicPublicationRenderError(msg) from exc

        _, stderr = await process.communicate()
        if process.returncode != 0:
            details = stderr.decode('utf-8', errors='replace').strip()
            msg = f'rsvg-convert exit {process.returncode} on {svg}: {details}'
            raise SchematicPublicationRenderError(msg)


__all__ = ['KicadCliSchematicPublicationRenderer']
