"""Integration: KicadCliSchematicPublicationRenderer (T035 Phase 2.1).

Hybrid тестирование (R16):
- Unit-level: mocked `AppManager` (FakeAppManager) + monkeypatched
  `asyncio.create_subprocess_exec` (для `rsvg-convert`). Все
  тесты зелёные без реальных kicad-cli / rsvg-convert.
- Integration: реальный kicad-cli + rsvg-convert (skip if absent).
  На host'е Vladimir-а rsvg-convert отсутствует (`librsvg2-bin` —
  только в `efactory:linux` контейнере, см. spec W-1); тесты
  skip-ятся, но в CI/контейнере прогоняются.

Адаптер реализует publication-grade рендер `.kicad_sch` →
{color,bw} × {per-sheet:{SVG,PDF,PNG@300DPI}, optional combined PDF}.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.kicad_cli.schematic_publication_renderer import (
    KicadCliSchematicPublicationRenderer,
)
from domain.application import ApplicationKind
from domain.publication import MultiSheetMode
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
    RunResult,
)
from ports.outbound.schematic_publication_renderer import (
    SchematicPublicationRenderError,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------


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
            png_path.parent.mkdir(parents=True, exist_ok=True)
            png_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 6000)
        return _FakeProcess(returncode=returncode, stderr=stderr)

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_exec)
    return calls


def _kicad_side_effect(
    sheet_names: tuple[str, ...],
) -> Callable[[list[str]], None]:
    """Side-effect: симулирует kicad-cli sch export svg|pdf, создавая файлы.

    SVG export (`argv[2] == 'svg'`) — `--output` каталог, kicad
    кладёт `<sheet>.svg` для каждого имени.

    PDF export (`argv[2] == 'pdf'`) — `--output` файл, kicad пишет
    один PDF.
    """

    def side_effect(argv: list[str]) -> None:
        out_idx = argv.index('--output')
        out_path = Path(argv[out_idx + 1])
        export_kind = argv[2]
        if export_kind == 'svg':
            out_path.mkdir(parents=True, exist_ok=True)
            for name in sheet_names:
                (out_path / f'{name}.svg').write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg"/>',
                )
        elif export_kind == 'pdf':
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b'%PDF-1.4\n%fake pdf\n')
        else:
            msg = f'_kicad_side_effect: unknown export kind {export_kind!r}'
            raise ValueError(msg)

    return side_effect


def _make_schematic(tmp_path: Path, name: str = 'demo') -> Path:
    sch = tmp_path / f'{name}.kicad_sch'
    sch.touch()
    return sch


def _make_out_dir(tmp_path: Path) -> Path:
    out_dir = tmp_path / 'publication' / 'schematic'
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# ---------------------------------------------------------------------
# Unit tests (mocked toolchain)
# ---------------------------------------------------------------------


async def test_render_creates_color_and_bw_directory_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    assert (out_dir / 'color' / 'per-sheet').is_dir()
    assert (out_dir / 'bw' / 'per-sheet').is_dir()
    # PER_SHEET mode — no combined subdir
    assert not (out_dir / 'color' / 'combined').exists()
    assert not (out_dir / 'bw' / 'combined').exists()


async def test_render_combined_mode_creates_combined_subdirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.COMBINED,
    )

    assert (out_dir / 'color' / 'combined').is_dir()
    assert (out_dir / 'bw' / 'combined').is_dir()


async def test_render_svg_export_called_per_color(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    svg_calls = [
        argv for (_, argv) in app_manager.calls
        if argv[:3] == ['sch', 'export', 'svg']
    ]
    assert len(svg_calls) == 2
    bw_svg = [a for a in svg_calls if '--black-and-white' in a]
    color_svg = [a for a in svg_calls if '--black-and-white' not in a]
    assert len(bw_svg) == 1
    assert len(color_svg) == 1


async def test_render_color_svg_writes_into_color_per_sheet_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    svg_calls = [
        argv for (_, argv) in app_manager.calls
        if argv[:3] == ['sch', 'export', 'svg']
    ]
    color_svg = next(a for a in svg_calls if '--black-and-white' not in a)
    out_idx = color_svg.index('--output')
    color_out_dir = Path(color_svg[out_idx + 1])
    assert color_out_dir == out_dir / 'color' / 'per-sheet'

    bw_svg = next(a for a in svg_calls if '--black-and-white' in a)
    bw_out_dir = Path(bw_svg[bw_svg.index('--output') + 1])
    assert bw_out_dir == out_dir / 'bw' / 'per-sheet'


async def test_render_rsvg_uses_dpi_300_per_svg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    rsvg_calls = _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    # 1 sheet × 2 colors = 2 rsvg calls.
    assert len(rsvg_calls) == 2
    for argv in rsvg_calls:
        assert argv[0] == 'rsvg-convert'
        assert '--dpi-x' in argv
        assert argv[argv.index('--dpi-x') + 1] == '300'
        assert '--dpi-y' in argv
        assert argv[argv.index('--dpi-y') + 1] == '300'
        assert '-o' in argv


async def test_render_per_sheet_pdf_call_per_sheet_per_color(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    # 3 sheets to verify per-sheet PDF cycling.
    sheet_names = ('a-root', 'b-power', 'c-aux')
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(sheet_names),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    pdf_calls = [
        argv for (_, argv) in app_manager.calls
        if argv[:3] == ['sch', 'export', 'pdf']
    ]
    # 3 sheets × 2 colors = 6 per-sheet PDF calls in PER_SHEET mode.
    assert len(pdf_calls) == 6
    for argv in pdf_calls:
        # PER_SHEET mode → every PDF call has --pages with one page.
        assert '--pages' in argv
        page_arg = argv[argv.index('--pages') + 1]
        assert page_arg in {'1', '2', '3'}


async def test_render_combined_mode_extra_pdf_call_no_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('a-root', 'b-power')),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.COMBINED,
    )

    pdf_calls = [
        argv for (_, argv) in app_manager.calls
        if argv[:3] == ['sch', 'export', 'pdf']
    ]
    # 2 sheets × 2 colors per-sheet + 2 combined = 6 calls total.
    assert len(pdf_calls) == 6
    no_pages = [a for a in pdf_calls if '--pages' not in a]
    assert len(no_pages) == 2  # one combined PDF per color
    # Combined PDFs go into combined/ dir with project name (schematic.stem).
    for argv in no_pages:
        out_path = Path(argv[argv.index('--output') + 1])
        assert out_path.name == 'demo.pdf'
        assert out_path.parent.name == 'combined'


async def test_render_returns_artifacts_with_matching_color_bw_lengths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('a', 'b')),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    artifacts = await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    assert len(artifacts.color_per_sheet) == 2
    assert len(artifacts.bw_per_sheet) == 2
    assert artifacts.color_combined is None
    assert artifacts.bw_combined is None
    # Sorted by sheet name.
    color_names = [s.sheet_name for s in artifacts.color_per_sheet]
    assert color_names == sorted(color_names)
    # All three formats per sheet.
    for sheet in artifacts.color_per_sheet:
        assert sheet.svg.suffix == '.svg'
        assert sheet.pdf.suffix == '.pdf'
        assert sheet.png.suffix == '.png'


async def test_render_returns_combined_paths_when_combined_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path, name='se-amp')
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('se-amp',)),
    )
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    artifacts = await renderer.render(
        sch,
        out_dir,
        multi_sheet_mode=MultiSheetMode.COMBINED,
    )

    assert artifacts.color_combined is not None
    assert artifacts.bw_combined is not None
    assert artifacts.color_combined.name == 'se-amp.pdf'
    assert artifacts.bw_combined.name == 'se-amp.pdf'
    assert artifacts.color_combined.parent.name == 'combined'


async def test_render_raises_when_kicad_not_installed(tmp_path: Path) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        raises=ApplicationNotInstalledError('no kicad'),
    )

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    with pytest.raises(
        SchematicPublicationRenderError,
        match='kicad-cli not available',
    ):
        await renderer.render(
            sch,
            out_dir,
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
        )


async def test_render_raises_when_kicad_start_fails(tmp_path: Path) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        raises=ApplicationStartError('cannot start'),
    )

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    with pytest.raises(
        SchematicPublicationRenderError,
        match='failed to start',
    ):
        await renderer.render(
            sch,
            out_dir,
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
        )


async def test_render_raises_on_kicad_non_zero_exit(tmp_path: Path) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(1, '', 'Error: invalid schematic\n'),
    )

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    with pytest.raises(SchematicPublicationRenderError) as exc_info:
        await renderer.render(
            sch,
            out_dir,
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
        )
    assert 'exit 1' in str(exc_info.value)
    assert 'Error: invalid schematic' in str(exc_info.value)


async def test_render_raises_when_no_svg_produced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    # kicad "succeeds" но ничего не пишет.
    app_manager = FakeAppManager(result=RunResult(0, '', ''))
    _patch_rsvg(monkeypatch)

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    with pytest.raises(SchematicPublicationRenderError, match='no SVG files'):
        await renderer.render(
            sch,
            out_dir,
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
        )


async def test_render_raises_when_rsvg_not_installed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    _patch_rsvg(monkeypatch, raises=FileNotFoundError('rsvg-convert'))

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    with pytest.raises(
        SchematicPublicationRenderError,
        match='rsvg-convert not available',
    ):
        await renderer.render(
            sch,
            out_dir,
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
        )


async def test_render_raises_on_rsvg_non_zero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sch = _make_schematic(tmp_path)
    out_dir = _make_out_dir(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        on_run=_kicad_side_effect(('demo',)),
    )
    _patch_rsvg(monkeypatch, returncode=2, stderr=b'Error: parse svg\n')

    renderer = KicadCliSchematicPublicationRenderer(app_manager)
    with pytest.raises(SchematicPublicationRenderError) as exc_info:
        await renderer.render(
            sch,
            out_dir,
            multi_sheet_mode=MultiSheetMode.PER_SHEET,
        )
    assert 'exit 2' in str(exc_info.value)
    assert 'parse svg' in str(exc_info.value)


# ---------------------------------------------------------------------
# Integration (real kicad-cli + rsvg-convert, skip on host w/o them)
# ---------------------------------------------------------------------


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
async def test_render_real_rc_filter_per_sheet(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """End-to-end: kicad-cli + rsvg-convert на синтетическом RC-фильтре (PER_SHEET)."""
    from PIL import Image  # noqa: PLC0415  -- Pillow только для integration check

    out_dir = tmp_path / 'publication' / 'schematic'
    out_dir.mkdir(parents=True, exist_ok=True)

    renderer = KicadCliSchematicPublicationRenderer(_RealAppManager())
    artifacts = await renderer.render(
        rc_filter_schematic_path,
        out_dir,
        multi_sheet_mode=MultiSheetMode.PER_SHEET,
    )

    assert len(artifacts.color_per_sheet) >= 1
    assert len(artifacts.bw_per_sheet) == len(artifacts.color_per_sheet)
    assert artifacts.color_combined is None
    assert artifacts.bw_combined is None

    # Check files exist and PNG dpi=300 (SC-4 acceptance for adapter level).
    for sheet in artifacts.color_per_sheet + artifacts.bw_per_sheet:
        assert sheet.svg.is_file()
        assert sheet.pdf.is_file()
        assert sheet.png.is_file()
        with Image.open(sheet.png) as img:
            assert img.info.get('dpi') == (300.0, 300.0)


@_skip_no_kicad_cli
@_skip_no_rsvg
async def test_render_real_rc_filter_combined(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """End-to-end COMBINED mode: combined PDF создаётся дополнительно к per-sheet."""
    out_dir = tmp_path / 'publication' / 'schematic'
    out_dir.mkdir(parents=True, exist_ok=True)

    renderer = KicadCliSchematicPublicationRenderer(_RealAppManager())
    artifacts = await renderer.render(
        rc_filter_schematic_path,
        out_dir,
        multi_sheet_mode=MultiSheetMode.COMBINED,
    )

    assert artifacts.color_combined is not None
    assert artifacts.bw_combined is not None
    assert artifacts.color_combined.is_file()
    assert artifacts.bw_combined.is_file()
    assert artifacts.color_combined.name == 'rc_filter.pdf'
