"""Hatchling custom build hook: auto-install pre-commit pre-push hook (T095)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = 'custom'

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        del version, build_data
        root = Path(self.root)
        if not (root / '.git').exists():
            return

        uv_path = shutil.which('uv')
        if uv_path is None:
            sys.stderr.write(
                '[hatch_build] uv not on PATH — skipping pre-push hook auto-install\n',
            )
            return

        env = os.environ.copy()
        env.pop('VIRTUAL_ENV', None)

        result = subprocess.run(
            [
                uv_path,
                'run',
                '--no-sync',
                'pre-commit',
                'install',
                '--hook-type',
                'pre-push',
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            sys.stderr.write(
                '[hatch_build] pre-push hook installed via pre-commit\n',
            )
        else:
            sys.stderr.write(
                '[hatch_build] pre-push hook auto-install skipped '
                f'(rc={result.returncode}): '
                f'{result.stderr.strip() or "no stderr"}\n',
            )
