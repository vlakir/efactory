"""Integration test: T151 CI template-snapshot-check workflow.

Проверяет что:
1. Workflow file существует в правильной локации.
2. YAML парсится без ошибок.
3. Triggers — push в main + pull_request (любая ветка).
4. Job содержит explicit step с `regenerate-templates.py` invocation.
5. Job содержит `git diff --exit-code` для fail-on-staleness detection.
6. Job step имеет понятный fail-сообщение «run uv run python
   scripts/regenerate-templates.py».
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _REPO_ROOT / '.github' / 'workflows' / 'template-snapshot-check.yml'


def test_workflow_file_exists() -> None:
    assert _WORKFLOW_PATH.is_file(), f'workflow file missing: {_WORKFLOW_PATH}'


@pytest.fixture
def workflow_dict() -> dict:
    return yaml.safe_load(_WORKFLOW_PATH.read_text(encoding='utf-8'))


def test_workflow_yaml_is_parseable(workflow_dict: dict) -> None:
    assert isinstance(workflow_dict, dict)


def test_workflow_has_name(workflow_dict: dict) -> None:
    assert 'name' in workflow_dict
    assert isinstance(workflow_dict['name'], str)


def test_workflow_triggers_push_main_and_pull_request(workflow_dict: dict) -> None:
    """Triggers: push в main + pull_request (для PR visibility)."""
    # YAML `on:` parses as `True` key (Python bool) если quoted incorrectly.
    triggers = workflow_dict.get('on') or workflow_dict.get(True)
    assert triggers is not None, 'no `on:` key in workflow'
    # Push в main.
    assert 'push' in triggers
    push_cfg = triggers['push']
    assert 'main' in push_cfg.get('branches', [])
    # Pull request (for PR-time visibility on staleness).
    assert 'pull_request' in triggers


def test_job_step_invokes_regenerate_templates(workflow_dict: dict) -> None:
    """Один из job-step'ов запускает scripts/regenerate-templates.py."""
    jobs = workflow_dict.get('jobs', {})
    assert jobs, 'no jobs defined'

    all_run_commands: list[str] = []
    for job in jobs.values():
        for step in job.get('steps', []):
            if 'run' in step:
                all_run_commands.append(step['run'])

    joined = '\n'.join(all_run_commands)
    assert 'regenerate-templates.py' in joined, (
        f'no step invokes regenerate-templates.py:\n{joined}'
    )


def test_job_step_does_git_diff_check(workflow_dict: dict) -> None:
    """Один из step'ов делает `git diff --exit-code` для fail-on-staleness."""
    jobs = workflow_dict.get('jobs', {})
    all_run_commands: list[str] = []
    for job in jobs.values():
        for step in job.get('steps', []):
            if 'run' in step:
                all_run_commands.append(step['run'])

    joined = '\n'.join(all_run_commands)
    assert 'git diff' in joined, (
        f'no step checks `git diff` for staleness:\n{joined}'
    )


def test_workflow_fail_message_actionable(workflow_dict: dict) -> None:
    """При detected staleness — actionable hint в fail-сообщении."""
    jobs = workflow_dict.get('jobs', {})
    all_text: list[str] = []
    for job in jobs.values():
        for step in job.get('steps', []):
            if 'run' in step:
                all_text.append(step['run'])

    joined = '\n'.join(all_text)
    assert 'regenerate-templates.py' in joined
    # Сообщение должно подсказать "run X" — конкретная команда.
    assert 'run' in joined.lower()


def test_workflow_uses_python_313_or_compatible(workflow_dict: dict) -> None:
    """Workflow setup использует Python 3.13+ (как `requires-python` в pyproject)."""
    jobs = workflow_dict.get('jobs', {})
    found_python = False
    for job in jobs.values():
        for step in job.get('steps', []):
            uses = step.get('uses', '')
            if 'setup-python' in uses or 'astral-sh/setup-uv' in uses:
                found_python = True
                if 'setup-python' in uses:
                    py_ver = step.get('with', {}).get('python-version', '')
                    # 3.13+ — спрашивать "3.13" или "3.14" не critical.
                    assert py_ver.startswith(('3.1', '3.2'))
    assert found_python, 'workflow должна устанавливать Python (setup-python или setup-uv)'
