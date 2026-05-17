"""E2E: efactory decision add/list/show (T099 Phase 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    projects_root = tmp_path / 'projects'
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )
    return projects_root


def test_decision_add_list_show_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'amp'])

    add_result = runner.invoke(
        build_cli_app(),
        [
            'decision', 'add',
            '--project', 'amp',
            '--title', 'Choose SE topology',
            '--summary', 'SE для наушников',
            '--rationale', 'Меньше искажений, достаточная мощность',
        ],
    )
    assert add_result.exit_code == 0, add_result.output
    assert 'Added D001' in add_result.output

    decision_file = projects_root / 'amp' / 'decisions' / 'D001_choose-se-topology.md'
    assert decision_file.is_file()
    assert '## Summary\nSE для наушников' in decision_file.read_text(encoding='utf-8')

    list_result = runner.invoke(
        build_cli_app(), ['decision', 'list', '--project', 'amp'],
    )
    assert list_result.exit_code == 0, list_result.output
    assert 'D001' in list_result.output
    assert 'accepted' in list_result.output

    show_result = runner.invoke(
        build_cli_app(), ['decision', 'show', '--project', 'amp', '--id', 'D001'],
    )
    assert show_result.exit_code == 0, show_result.output
    assert 'Choose SE topology' in show_result.output
    assert 'Меньше искажений' in show_result.output


def test_decision_list_empty_when_no_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'fresh'])

    result = runner.invoke(
        build_cli_app(), ['decision', 'list', '--project', 'fresh'],
    )

    assert result.exit_code == 0, result.output
    assert 'No decisions found' in result.output


def test_decision_show_missing_id_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'p'])

    result = runner.invoke(
        build_cli_app(), ['decision', 'show', '--project', 'p', '--id', 'D999'],
    )

    assert result.exit_code == 1
    assert 'D999' in result.output


def test_decision_add_unknown_project_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'decision', 'add',
            '--project', 'ghost',
            '--title', 't',
            '--summary', 's',
            '--rationale', 'r',
        ],
    )

    assert result.exit_code == 1
    assert 'ghost' in result.output


def test_decision_add_auto_increments_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'p'])

    for i in range(3):
        runner.invoke(
            build_cli_app(),
            [
                'decision', 'add',
                '--project', 'p',
                '--title', f'decision-{i}',
                '--summary', 's',
                '--rationale', 'r',
            ],
        )

    result = runner.invoke(
        build_cli_app(), ['decision', 'list', '--project', 'p'],
    )
    assert result.exit_code == 0
    assert 'D001' in result.output
    assert 'D002' in result.output
    assert 'D003' in result.output


def test_reindex_pulls_decisions_added_to_filesystem_manually(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T099 acceptance: вручную добавленный D###_*.md → reindex → виден через list."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'manual'])

    decisions_dir = projects_root / 'manual' / 'decisions'
    decisions_dir.mkdir()
    (decisions_dir / 'D001_manual-entry.md').write_text(
        '# D001: Manual entry\n\n'
        '**Дата:** 2026-05-17\n'
        '**Статус:** proposed\n\n'
        '## Summary\nManual\n\n'
        '## Rationale\nWritten by hand\n',
        encoding='utf-8',
    )

    reindex_result = runner.invoke(build_cli_app(), ['project', 'reindex'])
    assert reindex_result.exit_code == 0, reindex_result.output

    list_result = runner.invoke(
        build_cli_app(), ['decision', 'list', '--project', 'manual'],
    )
    assert list_result.exit_code == 0
    assert 'D001' in list_result.output
    assert 'Manual' in list_result.output
