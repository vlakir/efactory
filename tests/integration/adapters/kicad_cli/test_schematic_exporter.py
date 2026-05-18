"""Integration: KicadCliSchematicExporter (T004).

Unit-level через mocked AppManager (всегда зелёный) + integration с
реальным kicad-cli (skip-if-no-kicad).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from domain.application import ApplicationKind
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
    RunResult,
)
from ports.outbound.schematic_exporter import SchematicExportError

if TYPE_CHECKING:
    pass


class FakeAppManager:
    """Контролируемый AppManager — фиксирует argv, возвращает заданный RunResult."""

    def __init__(
        self,
        *,
        result: RunResult | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[tuple[ApplicationKind, list[str]]] = []

    async def status(self, kind: ApplicationKind):  # noqa: ARG002,ANN201
        raise NotImplementedError

    async def launch(self, kind, args=None):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError

    async def run(
        self,
        kind: ApplicationKind,
        args: list[str] | None = None,
        *,
        timeout_seconds: float | None = None,  # noqa: ARG002
    ) -> RunResult:
        self.calls.append((kind, list(args or [])))
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result

    async def stop(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError

    async def restart(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError


async def test_export_builds_correct_argv(tmp_path: Path) -> None:
    """Adapter формирует `sch export netlist --format spice --output ...`."""
    schematic = tmp_path / 'demo.kicad_sch'
    output = tmp_path / 'demo.cir'
    app_manager = FakeAppManager(result=RunResult(0, '', ''))
    exporter = KicadCliSchematicExporter(app_manager)

    result_path = await exporter.export_spice_netlist(schematic, output)

    assert result_path == output
    assert len(app_manager.calls) == 1
    kind, args = app_manager.calls[0]
    assert kind is ApplicationKind.KICAD_CLI
    assert args == [
        'sch',
        'export',
        'netlist',
        '--format',
        'spice',
        '--output',
        str(output),
        str(schematic),
    ]


async def test_export_raises_when_kicad_not_installed(tmp_path: Path) -> None:
    app_manager = FakeAppManager(
        raises=ApplicationNotInstalledError('no kicad'),
    )
    exporter = KicadCliSchematicExporter(app_manager)

    with pytest.raises(SchematicExportError, match='kicad-cli not available'):
        await exporter.export_spice_netlist(
            tmp_path / 'x.kicad_sch', tmp_path / 'x.cir',
        )


async def test_export_raises_on_non_zero_exit_with_stderr(
    tmp_path: Path,
) -> None:
    app_manager = FakeAppManager(
        result=RunResult(1, '', 'Error: invalid schematic\n'),
    )
    exporter = KicadCliSchematicExporter(app_manager)

    with pytest.raises(SchematicExportError) as exc_info:
        await exporter.export_spice_netlist(
            tmp_path / 'broken.kicad_sch', tmp_path / 'broken.cir',
        )
    assert 'exit 1' in str(exc_info.value)
    assert 'Error: invalid schematic' in str(exc_info.value)


async def test_export_falls_back_to_stdout_when_stderr_empty(
    tmp_path: Path,
) -> None:
    app_manager = FakeAppManager(
        result=RunResult(1, 'Parse error at line 42\n', ''),
    )
    exporter = KicadCliSchematicExporter(app_manager)

    with pytest.raises(SchematicExportError) as exc_info:
        await exporter.export_spice_netlist(
            tmp_path / 'x.kicad_sch', tmp_path / 'x.cir',
        )
    assert 'Parse error at line 42' in str(exc_info.value)


async def test_export_raises_on_app_start_error(tmp_path: Path) -> None:
    app_manager = FakeAppManager(
        raises=ApplicationStartError('cannot start'),
    )
    exporter = KicadCliSchematicExporter(app_manager)

    with pytest.raises(SchematicExportError, match='failed to start'):
        await exporter.export_spice_netlist(
            tmp_path / 'x.kicad_sch', tmp_path / 'x.cir',
        )
