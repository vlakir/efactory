"""
KicadCliSchematicRenderer — `kicad-cli sch export svg` + `rsvg-convert` (T025).

Pipeline:
  1. `kicad-cli sch export svg --output <ts_dir> <schematic>` —
     KiCad создаёт по одному SVG на лист (multi-sheet поддержан, Q10).
  2. Для каждого SVG: `rsvg-convert <svg> -o <png>` (librsvg2-bin,
     добавлен в `Dockerfile` Stage 1, Analyze C-1 fix (b)).

Использует T009 `AppManager` для kicad-cli (consistent с
`KicadCliSchematicExporter`); `rsvg-convert` — generic OS tool,
вызывается через `asyncio.create_subprocess_exec` напрямую.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.application import ApplicationKind
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
)
from ports.outbound.schematic_renderer import (
    SchematicRender,
    SchematicRenderError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.app_manager import AppManager


_TS_FORMAT = '%Y%m%dT%H%M%SZ'


class KicadCliSchematicRenderer:
    """SchematicRenderer на kicad-cli + rsvg-convert."""

    def __init__(self, app_manager: AppManager) -> None:
        self._app_manager = app_manager

    async def render(
        self,
        schematic: Path,
        out_root: Path,
    ) -> SchematicRender:
        created_at = datetime.now(UTC)
        ts_dir = out_root / created_at.strftime(_TS_FORMAT)
        await asyncio.to_thread(ts_dir.mkdir, parents=True, exist_ok=True)

        await self._export_svgs(schematic, ts_dir)

        svg_paths = tuple(sorted(ts_dir.glob('*.svg')))
        if not svg_paths:
            msg = (
                f'kicad-cli sch export svg created no SVG files in '
                f'{ts_dir} for schematic {schematic}.'
            )
            raise SchematicRenderError(msg)

        png_paths = tuple(svg.with_suffix('.png') for svg in svg_paths)
        for svg, png in zip(svg_paths, png_paths, strict=True):
            await self._rsvg_convert(svg, png)

        return SchematicRender(
            png_paths=png_paths,
            svg_paths=svg_paths,
            created_at=created_at,
        )

    async def _export_svgs(self, schematic: Path, out_dir: Path) -> None:
        args = [
            'sch',
            'export',
            'svg',
            '--output',
            str(out_dir),
            str(schematic),
        ]
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
            raise SchematicRenderError(msg) from exc
        except ApplicationStartError as exc:
            msg = f'kicad-cli failed to start: {exc}'
            raise SchematicRenderError(msg) from exc

        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            msg = (
                f'kicad-cli sch export svg exit {result.returncode} on '
                f'{schematic}: {details}'
            )
            raise SchematicRenderError(msg)

    async def _rsvg_convert(self, svg: Path, png: Path) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                'rsvg-convert',
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
            raise SchematicRenderError(msg) from exc

        _, stderr = await process.communicate()
        if process.returncode != 0:
            details = stderr.decode('utf-8', errors='replace').strip()
            msg = f'rsvg-convert exit {process.returncode} on {svg}: {details}'
            raise SchematicRenderError(msg)


__all__ = ['KicadCliSchematicRenderer']
