"""E2E: `efactory project show --name <name>`.

Третий сквозной use case после T085/T088. Проверяет happy-path
(существующий проект → вывод метаданных) и failure path
(несуществующий проект → exit_code != 0 + сообщение об ошибке).
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


def test_project_show_returns_metadata_of_existing_project(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    created = runner.invoke(app, ['project', 'create', '--name', 'shown-amp'])
    assert created.exit_code == 0, created.output

    result = runner.invoke(app, ['project', 'show', '--name', 'shown-amp'])

    assert result.exit_code == 0, result.output
    assert 'name: shown-amp' in result.output
    assert 'id:' in result.output
    assert 'status: idea' in result.output
    assert 'created_at:' in result.output
    assert 'path:' in result.output
    assert 'phases:' in result.output
    # таблица фаз: все 6 фаз присутствуют, все pending по умолчанию
    for phase_name in (
        'schematic',
        'simulation',
        'pcb',
        'magnetics',
        'enclosure',
        'documentation',
    ):
        assert f'  {phase_name}\tpending\t-\t-' in result.output


def test_project_show_unknown_name_exits_with_error(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'show', '--name', 'ghost-amp'])

    assert result.exit_code == 1
    assert "Project 'ghost-amp' not found" in result.output
