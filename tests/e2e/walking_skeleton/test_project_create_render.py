"""E2E: project create --template запускает schematic render (T025 Phase B)."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path


_skip_no_kicad_cli = pytest.mark.skipif(
    shutil.which('kicad-cli') is None,
    reason='kicad-cli not installed on host',
)


@_skip_no_kicad_cli
def test_project_create_with_template_renders_or_fails_soft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Template materialize → render pipeline.

    Two acceptance branches:
      - rsvg-convert installed → `schematic-render:` stdout строка(и),
        PNG-файл создан в `<project>/.efactory/renders/<TS>/`.
      - rsvg-convert absent → `Warning: schematic render failed`
        в stderr, проект всё равно создан, exit 0 (fail-soft).
    """
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))

    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(
        app,
        [
            'project',
            'create',
            '--name',
            'render-test',
            '--template',
            'op-amp-inverting',
        ],
    )

    assert result.exit_code == 0, result.output
    project_path = projects_root / 'render-test'
    assert project_path.is_dir()
    assert (project_path / 'render-test.kicad_sch').is_file()

    renders_dir = project_path / '.efactory' / 'renders'
    if shutil.which('rsvg-convert') is not None:
        # Happy path.
        assert 'schematic-render:' in result.output
        png_files = list(renders_dir.glob('*/*.png'))
        assert len(png_files) >= 1
        for png in png_files:
            assert png.stat().st_size >= 5000
    else:
        # Fail-soft path (хостовая среда без rsvg-convert).
        assert 'schematic render failed' in result.output
        assert 'rsvg-convert not available' in result.output


def test_project_create_without_template_does_not_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без `--template` нет `.kicad_sch` → render не вызывается."""
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))

    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(
        app,
        ['project', 'create', '--name', 'no-template'],
    )

    assert result.exit_code == 0, result.output
    assert 'schematic-render:' not in result.output
    assert 'schematic render failed' not in result.output
