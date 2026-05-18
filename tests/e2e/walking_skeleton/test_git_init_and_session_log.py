"""E2E: git init при `project create` + session log JSONL (T010)."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path


_GIT_AVAILABLE = shutil.which('git') is not None
needs_git = pytest.mark.skipif(
    not _GIT_AVAILABLE,
    reason='git CLI not installed',
)


def _setup_env(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_id: str = '20260518-100000-aabbcc',
) -> tuple['Path', 'Path']:
    projects_root = tmp_path / 'projects'
    db_file = tmp_path / 'efactory.sqlite'
    session_root = tmp_path / 'sessions'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(session_root))
    monkeypatch.setenv('EFACTORY_SESSION_ID', session_id)
    return projects_root, session_root


def _read_log(session_root: 'Path', session_id: str) -> list[dict]:
    log = session_root / session_id / 'log.jsonl'
    text = log.read_text(encoding='utf-8')
    return [json.loads(line) for line in text.strip().split('\n') if line]


@needs_git
def test_create_initializes_git_repo_with_project_yaml(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root, _ = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'demo'],
    )

    assert result.exit_code == 0, result.output
    git_dir = projects_root / 'demo' / '.git'
    assert git_dir.is_dir()

    log = subprocess.run(
        ['git', '-C', str(projects_root / 'demo'), 'log', '--oneline'],
        capture_output=True, text=True, check=True,
    )
    assert 'efactory: create project demo' in log.stdout

    files = subprocess.run(
        ['git', '-C', str(projects_root / 'demo'), 'ls-files'],
        capture_output=True, text=True, check=True,
    )
    assert 'project.yaml' in files.stdout


def test_create_writes_session_log_with_ok_event(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, session_root = _setup_env(
        tmp_path, monkeypatch, session_id='create-session',
    )
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'demo'],
    )
    assert result.exit_code == 0, result.output

    records = _read_log(session_root, 'create-session')
    create_events = [r for r in records if r['event'] == 'project.create']
    assert len(create_events) == 1
    assert create_events[0]['status'] == 'ok'
    assert create_events[0]['project'] == 'demo'
    assert create_events[0]['payload'] == {'name': 'demo'}


def test_decision_add_to_missing_project_writes_error_event(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, session_root = _setup_env(tmp_path, monkeypatch, session_id='err-session')
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
    assert result.exit_code == 1, result.output

    records = _read_log(session_root, 'err-session')
    add_events = [r for r in records if r['event'] == 'decision.add']
    assert len(add_events) == 1
    assert add_events[0]['status'] == 'error'
    assert add_events[0]['project'] == 'ghost'
    assert 'ProjectNotFoundError' in add_events[0]['error']


def test_session_id_env_override_is_respected(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T010 Resolved #3: EFACTORY_SESSION_ID переопределяет генератор."""
    _, session_root = _setup_env(tmp_path, monkeypatch, session_id='my-fixed-id')
    runner = CliRunner()

    runner.invoke(build_cli_app(), ['project', 'list'])

    assert (session_root / 'my-fixed-id' / 'log.jsonl').is_file()


def test_session_id_env_groups_multiple_commands_into_one_log(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Несколько CLI вызовов с тем же session_id → одна папка / один log."""
    _, session_root = _setup_env(tmp_path, monkeypatch, session_id='grouped')
    runner = CliRunner()

    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'a'])
    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'b'])
    runner.invoke(build_cli_app(), ['project', 'list'])

    records = _read_log(session_root, 'grouped')
    events = [r['event'] for r in records]
    assert events.count('project.create') == 2
    assert events.count('project.list') == 1


def test_create_when_git_missing_succeeds_and_logs_git_error(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance: git нет → create OK, в session log запись git.init error."""
    projects_root, session_root = _setup_env(
        tmp_path, monkeypatch, session_id='no-git',
    )
    # Подменяем shutil.which везде, где adapter его зовёт.
    monkeypatch.setattr(
        'adapters.outbound.git_subprocess.git_repository.shutil.which',
        lambda _: None,
    )
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'no-vcs'],
    )

    assert result.exit_code == 0, result.output
    assert not (projects_root / 'no-vcs' / '.git').exists()

    records = _read_log(session_root, 'no-git')
    create_events = [r for r in records if r['event'] == 'project.create']
    git_events = [r for r in records if r['event'] == 'git.init']
    assert create_events[0]['status'] == 'ok'
    assert len(git_events) == 1
    assert git_events[0]['status'] == 'error'
    assert 'git not found' in git_events[0]['error']
