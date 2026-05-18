"""
KicadCliSchematicExporter — `kicad-cli sch export netlist --format spice` (T004).

Использует T009 `AppManager.run(ApplicationKind.KICAD_CLI, args)` для
вызова kicad-cli как dependency-inverted subprocess. Поддерживает
sharun multi-call AppImage (T009 C2: `kicad.AppImage kicad-cli ...`)
через PlatformLayer resolution.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from domain.application import ApplicationKind
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
)
from ports.outbound.schematic_exporter import SchematicExportError

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.app_manager import AppManager


class KicadCliSchematicExporter:
    def __init__(self, app_manager: AppManager) -> None:
        self._app_manager = app_manager

    async def export_spice_netlist(
        self,
        schematic: Path,
        output: Path,
    ) -> Path:
        args = [
            'sch',
            'export',
            'netlist',
            '--format',
            'spice',
            '--output',
            str(output),
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
            raise SchematicExportError(msg) from exc
        except ApplicationStartError as exc:
            msg = f'kicad-cli failed to start: {exc}'
            raise SchematicExportError(msg) from exc

        # KiCad возвращает exit 2 для warnings типа "missing sim model"
        # — для split-scope T004 (без реальной симуляции) это OK,
        # лишь бы netlist реально создан. Real fail: returncode != 0
        # И output отсутствует/пуст.
        netlist_created = await asyncio.to_thread(
            lambda: output.is_file() and output.stat().st_size > 0,
        )
        if result.returncode != 0 and not netlist_created:
            details = result.stderr.strip() or result.stdout.strip()
            msg = (
                f'kicad-cli exit {result.returncode} on schematic '
                f'{schematic}: {details}'
            )
            raise SchematicExportError(msg)

        return output


__all__ = ['KicadCliSchematicExporter']
