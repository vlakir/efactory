"""Integration smoke: session_start_hook.py через subprocess (T016 Phase A).

Запускаем hook через `/usr/bin/python3` (как Claude Code будет запускать
его внутри `efactory:linux` контейнера) с подменой workspace через
переменную окружения. Покрывает: shebang валиден, system Python (stdlib
only) исполняет скрипт без editable venv, JSON output читается.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


SYSTEM_PYTHON = Path('/usr/bin/python3')
HOOK_SCRIPT = Path(__file__).resolve().parent.parent.parent / 'scripts' / 'session_start_hook.py'

pytestmark = pytest.mark.skipif(
    not SYSTEM_PYTHON.exists() or not HOOK_SCRIPT.exists(),
    reason='requires /usr/bin/python3 and scripts/session_start_hook.py',
)


def _run_hook(cwd: Path, workspace: Path) -> dict[str, object]:
    """Run hook with given cwd; redirect WORKSPACE_ROOT via env override.

    Hook hard-codes ``WORKSPACE_ROOT = Path('/workspace')``; для integration
    smoke на хосте подменяем через мини-wrapper, который импортирует hook
    как module и патчит атрибут. Это согласовано с unit-тестами,
    использующими тот же приём.
    """
    wrapper = (
        'import sys, runpy, pathlib;'
        f'sys.path.insert(0, {str(HOOK_SCRIPT.parent)!r});'
        'import session_start_hook as h;'
        f'h.WORKSPACE_ROOT = pathlib.Path({str(workspace)!r});'
        'sys.exit(h.main())'
    )
    env = {**os.environ, 'CLAUDE_PROJECT_DIR': str(cwd)}
    result = subprocess.run(
        [str(SYSTEM_PYTHON), '-c', wrapper],
        check=True,
        input='',
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    return json.loads(result.stdout)


def test_subprocess_emits_session_start_envelope(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    project = workspace / 'demo'
    project.mkdir(parents=True)
    (project / 'demo.kicad_sch').touch()

    payload = _run_hook(project, workspace)

    assert 'hookSpecificOutput' in payload
    hso = payload['hookSpecificOutput']
    assert isinstance(hso, dict)
    assert hso['hookEventName'] == 'SessionStart'
    context = hso['additionalContext']
    assert isinstance(context, str)
    assert 'demo' in context
    assert 'demo.kicad_sch' in context


def test_subprocess_no_active_project(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'alpha').mkdir()
    (workspace / 'beta').mkdir()

    payload = _run_hook(workspace, workspace)

    context = payload['hookSpecificOutput']['additionalContext']  # type: ignore[index]
    assert 'No active project' in context
    assert 'alpha' in context
    assert 'beta' in context
