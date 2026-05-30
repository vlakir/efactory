"""Integration-тест composition root: build_cli_app без env (T157)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_EFACTORY_ENV_VARS = ('EFACTORY_PROJECTS_ROOT',)


def test_build_cli_app_works_without_env_and_creates_storage_dirs(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    for var in (*_EFACTORY_ENV_VARS, 'XDG_DATA_HOME'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.chdir(tmp_path)

    app = build_cli_app()

    expected_root = tmp_path / '.local' / 'share' / 'efactory'
    assert expected_root.is_dir(), (
        'composition root должен создать каталог хранилища'
    )
    assert (expected_root / 'projects').is_dir()

    runner = CliRunner()
    result = runner.invoke(app, ['project', 'create', '--name', 'smoke'])

    assert result.exit_code == 0, result.output
    # T157: directory + manifest YAML are source of truth (no SQL).
    assert (expected_root / 'projects' / 'smoke').is_dir()
    assert (expected_root / 'projects' / 'smoke' / 'project.yaml').is_file()
