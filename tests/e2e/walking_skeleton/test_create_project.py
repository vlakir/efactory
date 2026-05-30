"""E2E walking skeleton: CLI → use case → manifest YAML + filesystem (T157)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_create_project_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))

    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'create', '--name', 'my-amp'])

    assert result.exit_code == 0, result.output
    assert 'my-amp' in result.output

    # T157: directory + manifest YAML are source of truth (no SQL).
    assert (projects_root / 'my-amp').is_dir()
    assert (projects_root / 'my-amp' / 'project.yaml').is_file()


def test_create_with_path_traversal_name_exits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad name → понятная ошибка вместо python-traceback (T092)."""
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))

    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'create', '--name', '../../etc'])

    assert result.exit_code == 2
    assert 'Invalid project name' in result.output
    assert 'Traceback' not in result.output
