"""E2E: `efactory project list` после создания нескольких проектов.

Проверяет, что вторая команда CLI стыкуется со всем hexagonal-стеком
(CLI → use case → SQLAlchemy adapter → SQLite) end-to-end и что
порядок вывода — `created_at DESC` (новые сверху).

Запуск идёт через Typer CliRunner; БД и каталог проектов в `tmp_path`
через env override `EFACTORY_*`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_project_list_returns_created_projects_newest_first(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    projects_root = tmp_path / 'projects'
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )

    runner = CliRunner()
    app = build_cli_app()

    for name in ('first-amp', 'second-amp', 'third-amp'):
        result = runner.invoke(app, ['project', 'create', '--name', name])
        assert result.exit_code == 0, result.output

    result = runner.invoke(app, ['project', 'list'])

    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 3
    names_in_order = [line.split('\t')[0] for line in lines]
    assert names_in_order == ['third-amp', 'second-amp', 'first-amp']


def test_project_list_on_empty_db_says_no_projects(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    projects_root = tmp_path / 'projects'
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )

    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'list'])

    assert result.exit_code == 0, result.output
    assert 'No projects found.' in result.output
