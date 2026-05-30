#!/usr/bin/env python3
"""Merge `hooks` секции из embedded template в host settings.json (T149).

Используется `efactory-up bootstrap_claude_state`: при существующем
host settings.json (например, с user-prefs `theme` /
`skipDangerousModePermissionPrompt`) **не затирать** файл, а **только
добавить** `hooks` ключ если его нет.

Acceptance (T149):
- User has `hooks` (даже кастомный) → no-op, return RC_SKIPPED.
- User не имеет `hooks` → merge embedded `hooks` в user JSON,
  сохранив остальные user-keys; return RC_MERGED.
- Любая ошибка (parse / missing / template без `hooks`) → RC_ERROR.

Использование CLI:
    python3 merge_claude_settings.py <host_settings.json> <template.json>

stdlib-only (без pyyaml / jq) — runtime helper, не часть efactory venv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RC_MERGED = 0
RC_SKIPPED = 1
RC_ERROR = 2


def merge_settings(user_path: Path, template_path: Path) -> int:
    """Inject `hooks` section from template if user has none.

    Returns:
        RC_MERGED: hooks added (user JSON rewritten).
        RC_SKIPPED: user already has `hooks` key (no change).
        RC_ERROR: parse failure / missing file / template без `hooks`.

    """
    if not user_path.is_file():
        sys.stderr.write(f'error: user settings not found: {user_path}\n')
        return RC_ERROR
    if not template_path.is_file():
        sys.stderr.write(f'error: template not found: {template_path}\n')
        return RC_ERROR
    try:
        user = json.loads(user_path.read_text(encoding='utf-8'))
        template = json.loads(template_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f'error: invalid JSON: {exc}\n')
        return RC_ERROR
    if not isinstance(user, dict) or not isinstance(template, dict):
        sys.stderr.write('error: settings must be JSON object at top level\n')
        return RC_ERROR
    if 'hooks' not in template:
        sys.stderr.write(
            f'error: template {template_path} missing required "hooks" key\n',
        )
        return RC_ERROR
    if 'hooks' in user:
        sys.stdout.write(
            f'{user_path}: has "hooks" key — skipping merge '
            '(use --reset-claude-state to overwrite)\n',
        )
        return RC_SKIPPED
    user['hooks'] = template['hooks']
    user_path.write_text(
        json.dumps(user, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    sys.stdout.write(
        f'{user_path}: merged "hooks" from {template_path}\n',
    )
    return RC_MERGED


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write(
            'usage: merge_claude_settings.py <user_settings.json> <template.json>\n',
        )
        return RC_ERROR
    return merge_settings(Path(argv[1]), Path(argv[2]))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
