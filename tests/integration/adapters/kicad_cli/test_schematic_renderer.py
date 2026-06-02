"""Integration: KicadCliSchematicRenderer (T025).

Unit-level через mocked AppManager + monkeypatched `asyncio.
create_subprocess_exec` (всегда зелёный, без реальных kicad-cli /
rsvg-convert) + integration с реальным toolchain (skip if no
kicad-cli / no rsvg-convert).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.kicad_cli.schematic_renderer import (
    KicadCliSchematicRenderer,
)
from domain.application import ApplicationKind
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
    RunResult,
)
from ports.outbound.schematic_renderer import SchematicRenderError

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeAppManager:
    """AppManager-stub: фиксирует argv, выполняет side-effect, возвращает RunResult."""

    def __init__(
        self,
        *,
        result: RunResult | None = None,
        raises: Exception | None = None,
        on_run: Callable[[list[str]], None] | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self._on_run = on_run
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
        argv = list(args or [])
        self.calls.append((kind, argv))
        if self._raises is not None:
            raise self._raises
        if self._on_run is not None:
            self._on_run(argv)
        assert self._result is not None
        return self._result

    async def stop(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError

    async def restart(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError


class _FakeProcess:
    def __init__(self, *, returncode: int, stderr: bytes) -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b'', self._stderr


def _patch_rsvg(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stderr: bytes = b'',
    raises: Exception | None = None,
) -> list[tuple[str, ...]]:
    """Monkeypatch asyncio.create_subprocess_exec → fake rsvg.

    Возвращает list, в который пишутся argv каждого вызова.
    PNG-файл создаётся автоматически (fake PNG signature), если
    returncode=0 и не raises.
    """
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*argv, **_kwargs):  # noqa: ANN002,ANN003,ANN202
        calls.append(tuple(str(a) for a in argv))
        if raises is not None:
            raise raises
        argv_str = [str(a) for a in argv]
        if returncode == 0 and '-o' in argv_str:
            png_path = Path(argv_str[argv_str.index('-o') + 1])
            png_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 6000)
        return _FakeProcess(returncode=returncode, stderr=stderr)

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_exec)
    return calls


def _kicad_creates_svgs(
    sheet_filenames: tuple[str, ...],
) -> Callable[[list[str]], None]:
    """Side-effect: симулирует kicad-cli sch export svg, создавая SVG-файлы."""

    def side_effect(argv: list[str]) -> None:
        out_dir = Path(argv[argv.index('--output') + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in sheet_filenames:
            (out_dir / name).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"/>',
            )

    return side_effect


# =====================================================================
# Unit-level (mocked toolchain)
# =====================================================================


async def test_render_builds_correct_kicad_cli_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_creates_svgs(('demo.svg',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicRenderer(app_manager)
    await renderer.render(schematic, out_root)

    assert len(app_manager.calls) == 1
    kind, argv = app_manager.calls[0]
    assert kind is ApplicationKind.KICAD_CLI
    assert argv[:3] == ['sch', 'export', 'svg']
    assert '--output' in argv
    assert argv[-1] == str(schematic)


async def test_render_returns_sorted_paths_for_multi_sheet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    # Намеренно "обратный" порядок sheet_filenames — adapter должен
    # вернуть пути отсортированными независимо от kicad-cli ordering.
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_creates_svgs(('z-aux.svg', 'a-root.svg', 'm-mid.svg')),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicRenderer(app_manager)
    result = await renderer.render(schematic, out_root)

    assert len(result.svg_paths) == 3
    assert len(result.png_paths) == 3
    assert list(result.svg_paths) == sorted(result.svg_paths)
    assert list(result.png_paths) == sorted(result.png_paths)
    for png in result.png_paths:
        assert png.is_file()
        assert png.suffix == '.png'


async def test_render_creates_timestamped_subdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_creates_svgs(('demo.svg',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicRenderer(app_manager)
    result = await renderer.render(schematic, out_root)

    subdirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(subdirs) == 1
    ts_dir = subdirs[0]
    # UTC timestamp formatted as YYYYmmddTHHMMSSZ.
    assert ts_dir.name.endswith('Z')
    assert all(p.parent == ts_dir for p in result.png_paths)


async def test_render_rsvg_invoked_per_svg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_creates_svgs(('a.svg', 'b.svg')),
    )
    rsvg_calls = _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicRenderer(app_manager)
    await renderer.render(schematic, out_root)

    assert len(rsvg_calls) == 2
    for argv in rsvg_calls:
        assert argv[0] == 'rsvg-convert'
        assert '-o' in argv


async def test_render_raises_when_kicad_not_installed(tmp_path: Path) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        raises=ApplicationNotInstalledError('no kicad'),
    )
    renderer = KicadCliSchematicRenderer(app_manager)

    with pytest.raises(SchematicRenderError, match='kicad-cli not available'):
        await renderer.render(schematic, out_root)


async def test_render_raises_when_kicad_start_fails(tmp_path: Path) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        raises=ApplicationStartError('cannot start'),
    )
    renderer = KicadCliSchematicRenderer(app_manager)

    with pytest.raises(SchematicRenderError, match='failed to start'):
        await renderer.render(schematic, out_root)


async def test_render_raises_on_kicad_non_zero_exit(tmp_path: Path) -> None:
    schematic = tmp_path / 'broken.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        result=RunResult(1, '', 'Error: invalid schematic\n'),
    )
    renderer = KicadCliSchematicRenderer(app_manager)

    with pytest.raises(SchematicRenderError) as exc_info:
        await renderer.render(schematic, out_root)
    assert 'exit 1' in str(exc_info.value)
    assert 'Error: invalid schematic' in str(exc_info.value)


async def test_render_raises_when_no_svg_produced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    # kicad-cli "успешен" но ничего не создал.
    app_manager = FakeAppManager(result=RunResult(0, '', ''))
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicRenderer(app_manager)
    with pytest.raises(SchematicRenderError, match='no SVG files'):
        await renderer.render(schematic, out_root)


async def test_render_raises_when_rsvg_not_installed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_creates_svgs(('demo.svg',)),
    )
    _patch_rsvg(
        monkeypatch,
        raises=FileNotFoundError('rsvg-convert'),
    )

    renderer = KicadCliSchematicRenderer(app_manager)
    with pytest.raises(SchematicRenderError, match='rsvg-convert not available'):
        await renderer.render(schematic, out_root)


async def test_render_raises_on_rsvg_non_zero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schematic = tmp_path / 'demo.kicad_sch'
    schematic.touch()
    out_root = tmp_path / 'renders'

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_creates_svgs(('demo.svg',)),
    )
    _patch_rsvg(
        monkeypatch,
        returncode=2,
        stderr=b'Error: parse svg\n',
    )

    renderer = KicadCliSchematicRenderer(app_manager)
    with pytest.raises(SchematicRenderError) as exc_info:
        await renderer.render(schematic, out_root)
    assert 'exit 2' in str(exc_info.value)
    assert 'parse svg' in str(exc_info.value)


# =====================================================================
# Integration (real kicad-cli + rsvg-convert, skip if absent)
# =====================================================================


_skip_no_kicad_cli = pytest.mark.skipif(
    shutil.which('kicad-cli') is None,
    reason='kicad-cli not installed on host',
)
_skip_no_rsvg = pytest.mark.skipif(
    shutil.which('rsvg-convert') is None,
    reason='rsvg-convert not installed on host (apt install librsvg2-bin)',
)


class _RealAppManager:
    """Минимальный AppManager: запускает локальный kicad-cli напрямую."""

    async def status(self, kind):  # noqa: ARG002,ANN001,ANN201
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
        assert kind is ApplicationKind.KICAD_CLI
        process = await asyncio.create_subprocess_exec(
            'kicad-cli',
            *(args or []),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return RunResult(
            returncode=process.returncode or 0,
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace'),
        )

    async def stop(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError

    async def restart(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError


@_skip_no_kicad_cli
@_skip_no_rsvg
async def test_render_real_rc_filter(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """End-to-end: kicad-cli sch export svg + rsvg-convert на синтетическом RC-фильтре."""
    out_root = tmp_path / 'renders'
    renderer = KicadCliSchematicRenderer(_RealAppManager())

    result = await renderer.render(rc_filter_schematic_path, out_root)

    assert len(result.png_paths) >= 1
    assert len(result.svg_paths) >= 1
    for png in result.png_paths:
        assert png.is_file()
        assert png.stat().st_size >= 5000
        # PNG signature check (\x89PNG\r\n\x1a\n).
        with png.open('rb') as fh:
            assert fh.read(8) == b'\x89PNG\r\n\x1a\n'
