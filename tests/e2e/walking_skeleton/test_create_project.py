"""E2E walking skeleton: CLI → use case → SQLAlchemy + filesystem → domain.Project.

Сквозной сценарий из спеки T085 §4. Проверяет, что hexagonal-слои
стыкуются end-to-end на минимальном use case CreateProject.

Запуск идёт через Typer CliRunner, а SQLite-запись проверяется
независимым sync-драйвером `sqlite3` — это намеренно: e2e не должен
ходить в БД через тестируемый адаптер.
"""

from __future__ import annotations

import sqlite3
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
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )

    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'create', '--name', 'my-amp'])

    assert result.exit_code == 0, result.output
    assert 'my-amp' in result.output

    assert (projects_root / 'my-amp').is_dir()

    with sqlite3.connect(db_file) as cx:
        rows = cx.execute('SELECT name FROM projects').fetchall()
    assert rows == [('my-amp',)]
