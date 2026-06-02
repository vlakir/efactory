"""Unit: render_and_announce_schematic helper (T025)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from adapters.inbound.cli.app import render_and_announce_schematic
from ports.outbound.schematic_renderer import (
    SchematicRender,
    SchematicRenderError,
)

if TYPE_CHECKING:
    from pathlib import Path


class _StubRenderer:
    def __init__(
        self,
        *,
        result: SchematicRender | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[tuple[Path, Path]] = []

    async def render(
        self,
        schematic: Path,
        out_root: Path,
    ) -> SchematicRender:
        self.calls.append((schematic, out_root))
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


async def test_announce_emits_render_line_per_png(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    schematic = project_root / 'demo.kicad_sch'
    schematic.touch()
    png_a = tmp_path / 'a.png'
    png_b = tmp_path / 'b.png'
    render = SchematicRender(
        png_paths=(png_a, png_b),
        svg_paths=(tmp_path / 'a.svg', tmp_path / 'b.svg'),
        created_at=datetime.now(UTC),
    )
    renderer = _StubRenderer(result=render)

    result = await render_and_announce_schematic(
        renderer, schematic, project_root,
    )

    captured = capsys.readouterr()
    assert result is render
    assert f'schematic-render: {png_a}' in captured.out
    assert f'schematic-render: {png_b}' in captured.out
    assert captured.err == ''


async def test_announce_passes_renders_subdir_to_renderer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],  # noqa: ARG001
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    schematic = project_root / 'demo.kicad_sch'
    schematic.touch()
    render = SchematicRender(
        png_paths=(tmp_path / 'a.png',),
        svg_paths=(tmp_path / 'a.svg',),
        created_at=datetime.now(UTC),
    )
    renderer = _StubRenderer(result=render)

    await render_and_announce_schematic(renderer, schematic, project_root)

    assert len(renderer.calls) == 1
    called_schematic, called_out_root = renderer.calls[0]
    assert called_schematic == schematic
    assert called_out_root == project_root / '.efactory' / 'renders'


async def test_announce_fail_soft_on_render_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    schematic = project_root / 'demo.kicad_sch'
    schematic.touch()
    renderer = _StubRenderer(
        raises=SchematicRenderError('rsvg-convert not available'),
    )

    result = await render_and_announce_schematic(
        renderer, schematic, project_root,
    )

    captured = capsys.readouterr()
    assert result is None
    assert 'schematic-render:' not in captured.out
    assert 'schematic render failed' in captured.err
    assert 'rsvg-convert not available' in captured.err


@pytest.mark.parametrize('error_text', ['kicad-cli not available', 'no SVG files'])
async def test_announce_handles_any_render_error_class(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    error_text: str,
) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    schematic = project_root / 'demo.kicad_sch'
    schematic.touch()
    renderer = _StubRenderer(raises=SchematicRenderError(error_text))

    result = await render_and_announce_schematic(
        renderer, schematic, project_root,
    )

    captured = capsys.readouterr()
    assert result is None
    assert error_text in captured.err
