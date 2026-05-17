"""E2E: `efactory project update / add-phase / skip-phase` (T097)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _set_env(monkeypatch: 'pytest.MonkeyPatch', tmp_path: 'Path') -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )


def _create(runner: CliRunner, app, name: str) -> None:
    result = runner.invoke(app, ['project', 'create', '--name', name])
    assert result.exit_code == 0, result.output


def test_update_renames_existing_project(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    _create(runner, app, 'old-name')

    result = runner.invoke(
        app, ['project', 'update', 'old-name', '--new-name', 'new-name'],
    )

    assert result.exit_code == 0, result.output
    assert 'Updated project new-name' in result.output

    shown = runner.invoke(app, ['project', 'show', '--name', 'new-name'])
    assert shown.exit_code == 0, shown.output
    assert 'name: new-name' in shown.output


def test_update_phase_progresses_status(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    _create(runner, app, 'amp')

    started = runner.invoke(
        app,
        ['project', 'update', 'amp', '--phase', 'schematic', '--status', 'in_progress'],
    )
    assert started.exit_code == 0, started.output

    done = runner.invoke(
        app,
        ['project', 'update', 'amp', '--phase', 'schematic', '--status', 'done'],
    )
    assert done.exit_code == 0, done.output

    shown = runner.invoke(app, ['project', 'show', '--name', 'amp'])
    assert 'status: schematic' in shown.output
    assert '  schematic\tdone\t' in shown.output


def test_full_lifecycle_to_production_ready(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """Acceptance: 6 фаз done подряд → status=production_ready."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'full')

    for phase_name in (
        'schematic',
        'simulation',
        'pcb',
        'magnetics',
        'enclosure',
        'documentation',
    ):
        started = runner.invoke(
            app,
            [
                'project', 'update', 'full',
                '--phase', phase_name, '--status', 'in_progress',
            ],
        )
        assert started.exit_code == 0, started.output
        done = runner.invoke(
            app,
            ['project', 'update', 'full',
             '--phase', phase_name, '--status', 'done'],
        )
        assert done.exit_code == 0, done.output

    shown = runner.invoke(app, ['project', 'show', '--name', 'full'])
    assert 'status: production_ready' in shown.output


def test_flexible_scope_with_skip_phase_shortcut(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """Гибкий скоуп §4.1: skip magnetics + enclosure, остальные done."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'flex')

    for phase_name in ('schematic', 'simulation', 'pcb'):
        runner.invoke(
            app,
            ['project', 'update', 'flex',
             '--phase', phase_name, '--status', 'in_progress'],
        )
        runner.invoke(
            app,
            ['project', 'update', 'flex',
             '--phase', phase_name, '--status', 'done'],
        )

    skipped_mag = runner.invoke(
        app, ['project', 'skip-phase', 'flex', 'magnetics'],
    )
    assert skipped_mag.exit_code == 0, skipped_mag.output

    skipped_enc = runner.invoke(
        app, ['project', 'skip-phase', 'flex', 'enclosure'],
    )
    assert skipped_enc.exit_code == 0, skipped_enc.output

    for action in ('in_progress', 'done'):
        runner.invoke(
            app,
            ['project', 'update', 'flex',
             '--phase', 'documentation', '--status', action],
        )

    shown = runner.invoke(app, ['project', 'show', '--name', 'flex'])
    assert 'status: production_ready' in shown.output


def test_add_phase_unskips(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'unskip-test')

    runner.invoke(
        app, ['project', 'skip-phase', 'unskip-test', 'magnetics'],
    )
    shown_before = runner.invoke(
        app, ['project', 'show', '--name', 'unskip-test'],
    )
    assert '  magnetics\tskipped\t' in shown_before.output

    result = runner.invoke(
        app, ['project', 'add-phase', 'unskip-test', 'magnetics'],
    )
    assert result.exit_code == 0, result.output

    shown_after = runner.invoke(
        app, ['project', 'show', '--name', 'unskip-test'],
    )
    assert '  magnetics\tpending\t-\t-' in shown_after.output


def test_update_forbidden_transition_exits_with_error(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """Прыжок pending -> done через CLI запрещён (Analyze C2)."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'bad-jump')

    result = runner.invoke(
        app,
        ['project', 'update', 'bad-jump',
         '--phase', 'schematic', '--status', 'done'],
    )

    assert result.exit_code == 2
    assert 'Forbidden phase transition' in result.output


def test_update_unknown_name_exits_with_error(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(
        app, ['project', 'update', 'ghost', '--new-name', 'phantom'],
    )

    assert result.exit_code == 1
    assert "Project 'ghost' not found" in result.output


def test_update_rejects_invalid_new_name(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'good')

    result = runner.invoke(
        app, ['project', 'update', 'good', '--new-name', '../etc'],
    )

    assert result.exit_code == 2
    assert 'Invalid project name' in result.output


def test_update_mutex_violation_exits(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """`--new-name` несовместим с `--phase`/`--status` (Resolved #7)."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'mutex')

    result = runner.invoke(
        app,
        ['project', 'update', 'mutex',
         '--new-name', 'other',
         '--phase', 'schematic', '--status', 'in_progress'],
    )

    assert result.exit_code == 2
    assert 'mutually exclusive' in result.output


def test_update_missing_args_exits(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """Ни одной правки в команде → exit code 2."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'empty-cmd')

    result = runner.invoke(app, ['project', 'update', 'empty-cmd'])

    assert result.exit_code == 2
    assert 'Specify either --new-name or both' in result.output


def test_update_partial_phase_args_exits(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """`--phase` без `--status` → exit code 2."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    _create(runner, app, 'partial')

    result = runner.invoke(
        app, ['project', 'update', 'partial', '--phase', 'schematic'],
    )

    assert result.exit_code == 2
    assert '--phase and --status must be used together' in result.output
