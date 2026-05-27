"""Unit tests для `scripts/merge_claude_settings.py` (T149).

Helper для `efactory-up bootstrap_claude_state`: merge `hooks` секции
из embedded template в **существующий** host settings.json **только
если у host нет своего `hooks` ключа** (preserve user prefs `theme` /
`skipDangerousModePermissionPrompt` / etc.).

Используется через subprocess из bash-скрипта. Здесь — direct функции
вызов через sys.path-инъекцию (тот же pattern что
test_session_start_hook.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Direct import — модуль появится после Phase Red→Green.
import merge_claude_settings as helper  # noqa: E402


_TEMPLATE = {
    'hooks': {
        'SessionStart': [
            {
                'matcher': 'startup|resume|clear|compact',
                'hooks': [
                    {
                        'type': 'command',
                        'command': '/usr/bin/python3 /opt/efactory/scripts/session_start_hook.py',
                        'timeout': 10,
                    },
                ],
            },
        ],
    },
}


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


# ────────── happy paths ──────────


def test_merge_when_user_has_no_hooks(tmp_path: Path) -> None:
    """User has theme but no hooks → merge."""
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    _write_json(user_path, {'theme': 'dark', 'skipPrompts': True})
    _write_json(template_path, _TEMPLATE)

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_MERGED
    merged = json.loads(user_path.read_text())
    # User keys preserved.
    assert merged['theme'] == 'dark'
    assert merged['skipPrompts'] is True
    # Hooks added from template.
    assert 'hooks' in merged
    assert merged['hooks'] == _TEMPLATE['hooks']


def test_noop_when_user_already_has_hooks(tmp_path: Path) -> None:
    """User already has hooks (even custom) → no-op."""
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    pre_existing = {
        'theme': 'light',
        'hooks': {
            'SessionStart': [
                {'matcher': 'startup', 'hooks': [{'type': 'command', 'command': 'echo custom'}]},
            ],
        },
    }
    _write_json(user_path, pre_existing)
    _write_json(template_path, _TEMPLATE)

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_SKIPPED
    # Файл не изменён.
    assert json.loads(user_path.read_text()) == pre_existing


def test_merge_preserves_unrelated_nested_user_keys(tmp_path: Path) -> None:
    """Nested user config (e.g. mcpServers) preserved exactly."""
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    user_data = {
        'theme': 'dark',
        'mcpServers': {
            'custom': {'command': 'mcp-server', 'args': ['--port', '8080']},
        },
        'experimental': {'flag': 'value'},
    }
    _write_json(user_path, user_data)
    _write_json(template_path, _TEMPLATE)

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_MERGED
    merged = json.loads(user_path.read_text())
    assert merged['mcpServers'] == user_data['mcpServers']
    assert merged['experimental'] == user_data['experimental']


def test_merge_is_idempotent_after_first_run(tmp_path: Path) -> None:
    """Second invocation на already-merged settings → no-op."""
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    _write_json(user_path, {'theme': 'dark'})
    _write_json(template_path, _TEMPLATE)

    rc1 = helper.merge_settings(user_path, template_path)
    snapshot1 = user_path.read_text()
    rc2 = helper.merge_settings(user_path, template_path)
    snapshot2 = user_path.read_text()

    assert rc1 == helper.RC_MERGED
    assert rc2 == helper.RC_SKIPPED
    assert snapshot1 == snapshot2


# ────────── unhappy paths ──────────


def test_invalid_user_json_returns_error(tmp_path: Path) -> None:
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    user_path.write_text('not valid json {', encoding='utf-8')
    _write_json(template_path, _TEMPLATE)

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_ERROR


def test_missing_user_settings_returns_error(tmp_path: Path) -> None:
    """User file missing — caller should bootstrap from scratch, not call merge."""
    user_path = tmp_path / 'nonexistent.json'
    template_path = tmp_path / 'template.json'
    _write_json(template_path, _TEMPLATE)

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_ERROR


def test_invalid_template_returns_error(tmp_path: Path) -> None:
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    _write_json(user_path, {'theme': 'dark'})
    template_path.write_text('{', encoding='utf-8')

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_ERROR


def test_template_without_hooks_key_returns_error(tmp_path: Path) -> None:
    """Template должен содержать `hooks`-ключ; иначе caller misconfigured."""
    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    _write_json(user_path, {'theme': 'dark'})
    _write_json(template_path, {'other': 'data'})

    rc = helper.merge_settings(user_path, template_path)

    assert rc == helper.RC_ERROR


# ────────── CLI entry-point ──────────


def test_cli_subprocess_exit_code_for_merged(tmp_path: Path) -> None:
    """Через subprocess (как efactory-up will call) — verify exit code."""
    import subprocess  # noqa: PLC0415 — local import OK in test

    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    _write_json(user_path, {'theme': 'dark'})
    _write_json(template_path, _TEMPLATE)

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / 'merge_claude_settings.py'),
         str(user_path), str(template_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == helper.RC_MERGED


def test_cli_subprocess_exit_code_for_skipped(tmp_path: Path) -> None:
    import subprocess  # noqa: PLC0415

    user_path = tmp_path / 'settings.json'
    template_path = tmp_path / 'template.json'
    _write_json(user_path, {'theme': 'dark', 'hooks': {}})
    _write_json(template_path, _TEMPLATE)

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / 'merge_claude_settings.py'),
         str(user_path), str(template_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == helper.RC_SKIPPED


def test_cli_subprocess_wrong_args_returns_error() -> None:
    import subprocess  # noqa: PLC0415

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / 'merge_claude_settings.py')],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
