"""Integration-тест composition root: build_cli_app без env.

Проверяет, что Walking Skeleton CLI собирается и работает из чистого
окружения (без EFACTORY_* / .secrets) — composition root применяет
Settings-default'ы и автоматически создаёт storage-каталоги до запуска
Alembic-миграций (T087).
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_EFACTORY_ENV_VARS = ('EFACTORY_PROJECTS_ROOT', 'EFACTORY_DATABASE_URL')


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
        'composition root должен создать каталог хранилища до миграций'
    )
    assert (expected_root / 'projects').is_dir()
    assert (expected_root / 'efactory.db').is_file(), (
        'Alembic должен создать SQLite-файл при первом старте'
    )

    runner = CliRunner()
    result = runner.invoke(app, ['project', 'create', '--name', 'smoke'])

    assert result.exit_code == 0, result.output
    assert (expected_root / 'projects' / 'smoke').is_dir()

    with sqlite3.connect(expected_root / 'efactory.db') as cx:
        rows = cx.execute('SELECT name FROM projects').fetchall()
    assert rows == [('smoke',)]
