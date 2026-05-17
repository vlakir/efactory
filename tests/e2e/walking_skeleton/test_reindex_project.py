"""E2E: efactory project reindex (T098 Phase 3).

Базовый сценарий: создаём проект (manifest + SQL), вызываем reindex —
получаем idempotent indexed=1, no orphans, no failures.

Portability acceptance — отдельный тест test_reindex_portability.py.
Partial-failure scenario — test_reindex_partial_failure.py.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    projects_root = tmp_path / 'projects'
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )
    return projects_root, db_file


def test_reindex_existing_project_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root, _ = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'demo'],
    )
    assert create_result.exit_code == 0, create_result.output

    reindex_result = runner.invoke(build_cli_app(), ['project', 'reindex'])

    assert reindex_result.exit_code == 0, reindex_result.output
    assert 'Reindexed 1 projects.' in reindex_result.output
    assert 'Orphans' not in reindex_result.output
    assert 'Failed' not in reindex_result.output
    assert (projects_root / 'demo' / 'project.yaml').is_file()


def test_reindex_bootstraps_manifest_for_sql_only_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-T098 сценарий: SQL есть, manifest на диске удалён → bootstrap."""
    projects_root, _ = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'legacy'],
    )
    assert create_result.exit_code == 0, create_result.output
    manifest_path = projects_root / 'legacy' / 'project.yaml'
    manifest_path.unlink()  # симулируем pre-T098 state
    assert not manifest_path.is_file()

    reindex_result = runner.invoke(build_cli_app(), ['project', 'reindex'])

    assert reindex_result.exit_code == 0, reindex_result.output
    assert 'Bootstrapped 1 manifests' in reindex_result.output
    assert manifest_path.is_file()


def test_reindex_remove_orphans_drops_sql_rows_without_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--remove-orphans удаляет SQL-строки без manifest на диске."""
    projects_root, db_file = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'orphan'],
    )
    assert create_result.exit_code == 0, create_result.output
    (projects_root / 'orphan' / 'project.yaml').unlink()

    reindex_result = runner.invoke(
        build_cli_app(), ['project', 'reindex', '--remove-orphans'],
    )

    assert reindex_result.exit_code == 0, reindex_result.output
    assert 'Orphans (1, removed): orphan' in reindex_result.output

    with sqlite3.connect(db_file) as cx:
        rows = cx.execute('SELECT name FROM projects').fetchall()
    assert rows == []
