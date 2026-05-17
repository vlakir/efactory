"""E2E: `efactory project delete --name <name>`.

Четвёртый сквозной use case после T085/T088/T089. Удаление чистит обе
стороны — метаданные в SQLite и каталог проекта в FS — и оставляет
систему в консистентном состоянии (последующий `show` → not found,
`list` → пусто).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _set_env(
    monkeypatch: 'pytest.MonkeyPatch',
    tmp_path: 'Path',
) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )


def test_project_delete_removes_metadata_and_filesystem(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    created = runner.invoke(app, ['project', 'create', '--name', 'doomed-amp'])
    assert created.exit_code == 0, created.output
    project_dir = tmp_path / 'projects' / 'doomed-amp'
    assert project_dir.is_dir()

    deleted = runner.invoke(app, ['project', 'delete', '--name', 'doomed-amp'])
    assert deleted.exit_code == 0, deleted.output
    assert 'doomed-amp' in deleted.output

    assert not project_dir.exists()

    shown = runner.invoke(app, ['project', 'show', '--name', 'doomed-amp'])
    assert shown.exit_code == 1
    assert "Project 'doomed-amp' not found" in shown.output

    listed = runner.invoke(app, ['project', 'list'])
    assert listed.exit_code == 0, listed.output
    assert 'No projects found.' in listed.output


def test_project_delete_unknown_name_exits_with_error(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'delete', '--name', 'ghost-amp'])

    assert result.exit_code == 1
    assert "Project 'ghost-amp' not found" in result.output
